"""Full-loop drive of the bash tool on every backend, through a real Session.

``test_sandbox_contract.py`` proves the *sandbox* behaves the same on each
backend; this proves the whole path around it does too. A real ``Session`` /
``Agent`` runs a scripted (no-API) model that calls ``bash`` and then ``finish``,
so tool injection (``execute_tool``), per-spec ownership (``session.sandboxes``),
and ``Session.close`` teardown are exercised end to end against each runtime —
not the sandbox in isolation.

Gating mirrors the contract suite: ``local`` always runs; ``docker``/``ssh`` are
``slow`` and skip when their runtime is absent.
"""

import copy
from typing import Any, Dict, List

import pytest

import gimle.hugin.tools  # noqa: F401  (registers builtins.bash + finish)
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.interaction.tool_result import ToolResult
from gimle.hugin.llm.models.model_registry import get_model_registry
from gimle.hugin.storage.local import LocalStorage

from .conftest import ScriptedToolModel
from .sandbox_backends import ALL_BACKENDS, opts_for

# Every test here drives a real Session against a real runtime (local always;
# docker/ssh when present), so the whole module is integration, not unit.
pytestmark = pytest.mark.integration

EXAMPLE = "examples/bash_agent"


def _finish() -> Dict[str, Any]:
    """Return a scripted ``finish`` call ending the loop."""
    return {
        "tool": "finish",
        "input": {
            "finish_type": "success",
            "result": "done",
            "reason": "task complete",
        },
    }


def _bash_results(agent) -> List[Dict[str, Any]]:
    """Return the content dicts of every ``bash`` ToolResult on the agent's stack."""
    results = []
    for interaction in agent.stack.interactions:
        if (
            isinstance(interaction, ToolResult)
            and interaction.tool_name == "bash"
            and interaction.result
        ):
            results.append(interaction.result)
    return results


def _drive(agent, steps: int = 12) -> None:
    """Step the agent's loop to completion (bounded)."""
    for _ in range(steps):
        if not agent.step():
            break


@pytest.mark.parametrize("backend_name", ALL_BACKENDS)
def test_bash_loop_runs_on_backend(backend_name, tmp_path):
    """The whole loop runs on this backend: bash writes, then reads it back.

    The read-back marker travels command -> sandbox -> ToolResult, proving the
    backend is wired through the real tool path, not just callable in isolation.
    """
    opts = opts_for(backend_name)  # skips if the runtime is unavailable
    storage = LocalStorage(base_path=str(tmp_path / "storage"))
    env = Environment.load(EXAMPLE, storage=storage)
    marker = f"e2e-{backend_name}-marker"
    model_name = f"scripted-e2e-{backend_name}"

    registry = get_model_registry()
    registry.register_model(
        model_name,
        ScriptedToolModel(
            model_name,
            [
                {
                    "tool": "bash",
                    "input": {"command": f"echo {marker} > m.txt"},
                },
                {"tool": "bash", "input": {"command": "cat m.txt"}},
                _finish(),
            ],
        ),
    )
    try:
        with Session(environment=env) as session:
            config = env.config_registry.get("bash_agent")
            config.options["bash"] = opts  # route bash to the chosen backend
            config.llm_model = model_name  # no real LLM
            task = env.task_registry.get("explore")
            session.create_agent_from_task(config, task)
            agent = session.agents[0]
            _drive(agent)

            stdouts = [r.get("stdout", "") for r in _bash_results(agent)]
            assert any(
                marker in s for s in stdouts
            ), f"marker not read back on {backend_name}: {stdouts}"
    finally:
        registry.models.pop(model_name, None)


def test_two_specs_in_one_session_get_separate_sandboxes(tmp_path):
    """Two agents with different bash profiles each get their own backend.

    Per-spec ownership: the session keys one sandbox per distinct SandboxSpec, so
    two agents that ask for different isolation profiles do not share a backend
    (here two ``local`` specs that differ only by ``network`` — enough to be
    distinct specs while both running locally). Runs on ``local`` alone so it
    needs no extra runtime.
    """
    storage = LocalStorage(base_path=str(tmp_path / "storage"))
    env = Environment.load(EXAMPLE, storage=storage)
    profiles = [
        {"backend": "local"},
        {"backend": "local", "network": True},
    ]
    registry = get_model_registry()
    model_names: List[str] = []
    try:
        with Session(environment=env) as session:
            base_config = env.config_registry.get("bash_agent")
            for idx, opts in enumerate(profiles):
                marker = f"agent{idx}-secret"
                model_name = f"scripted-two-{idx}"
                model_names.append(model_name)
                registry.register_model(
                    model_name,
                    ScriptedToolModel(
                        model_name,
                        [
                            {
                                "tool": "bash",
                                "input": {
                                    "command": f"echo {marker} > mine.txt"
                                },
                            },
                            {
                                "tool": "bash",
                                "input": {"command": "cat mine.txt"},
                            },
                            _finish(),
                        ],
                    ),
                )
                config = copy.deepcopy(base_config)
                config.options["bash"] = opts
                config.llm_model = model_name
                task = env.task_registry.get("explore")
                session.create_agent_from_task(config, task)

            for agent in session.agents:
                _drive(agent)

            # The load-bearing spec-separation check: two distinct specs key two
            # distinct backend objects (a bug collapsing them to one fails on the
            # count; the deepcopy keeps each config's options independent).
            assert len(session.sandboxes) == 2
            specs = list(session.sandboxes.keys())
            assert specs[0] != specs[1]
            managers = list(session.sandboxes.values())
            assert managers[0].get() is not managers[1].get()
            # Each agent, driven through the real loop, read back only its own
            # marker. (For local this rides on the per-*agent* workspace, not the
            # per-spec split above — together they show both dimensions of
            # isolation hold end to end.)
            for idx, agent in enumerate(session.agents):
                stdouts = [r.get("stdout", "") for r in _bash_results(agent)]
                mine = f"agent{idx}-secret"
                other = f"agent{1 - idx}-secret"
                assert any(mine in s for s in stdouts), stdouts
                assert not any(other in s for s in stdouts), stdouts
    finally:
        for name in model_names:
            registry.models.pop(name, None)


def test_backend_startup_failure_surfaces_as_infra_error(tmp_path):
    """A backend that can't start comes back to the model as a clean infra_error.

    Regression guard for the docker/ssh panel findings: bringing a backend up can
    fail (daemon down, host unreachable), and that must reach the model as a
    non-retryable ``infra_error`` tool result — never an unhandled exception that
    crashes the loop, nor an invitation to retry a command whose fate is unknown.
    """
    from gimle.hugin.sandbox import sandbox as sandbox_mod
    from gimle.hugin.sandbox.sandbox import register_backend

    class _Boom:
        """A backend whose start() always fails."""

        def __init__(self, spec, session_id, workspace_root):
            """Accept the standard backend constructor args."""

        def start(self):
            """Fail to start, like an unreachable daemon/host."""
            raise RuntimeError("backend cannot start")

    registry = get_model_registry()
    model_name = "scripted-boom"
    try:
        register_backend("boomtest", lambda: _Boom)
        registry.register_model(
            model_name,
            ScriptedToolModel(
                model_name,
                [
                    {"tool": "bash", "input": {"command": "echo hi"}},
                    _finish(),
                ],
            ),
        )
        storage = LocalStorage(base_path=str(tmp_path / "storage"))
        env = Environment.load(EXAMPLE, storage=storage)
        with Session(environment=env) as session:
            config = env.config_registry.get("bash_agent")
            config.options["bash"] = {"backend": "boomtest"}
            config.llm_model = model_name
            task = env.task_registry.get("explore")
            session.create_agent_from_task(config, task)
            agent = session.agents[0]
            _drive(agent)

            # Find the bash ToolResult interaction (not just its content) so we
            # can assert the is_error flag that actually drives model behaviour.
            bash_hits = [
                i
                for i in agent.stack.interactions
                if isinstance(i, ToolResult) and i.tool_name == "bash"
            ]
            assert bash_hits, "bash produced no tool result"
            hit = bash_hits[0]
            assert hit.is_error is True
            content = hit.result or {}
            assert "infra_error" in content
            # Assert the *intent* (non-retryable, needs an operator), not the
            # exact wording, so a reworded note doesn't falsely break this.
            note = content.get("note", "").lower()
            assert "not" in note and "retr" in note
            assert "operator" in note
    finally:
        registry.models.pop(model_name, None)
        sandbox_mod._BACKENDS.pop("boomtest", None)
