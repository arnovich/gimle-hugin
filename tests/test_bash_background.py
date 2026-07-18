"""Background bash execution: the executor, the tool surface, and the resume.

The gated ``FakeSandbox`` (its ``exec`` blocks until a test releases an Event) is
what makes the parked→resume path testable — a normal FakeSandbox returns
instantly, so the deferral would never be exercised. These tests pin: the
executor's job lifecycle and *guarded* collect (a worker exception must not
raise — that would wedge the stack); the tool surface (``background=true``
returns a job_id, ``bash_output`` parks then collects, a slow command
auto-defers); and a full-loop drive proving the resumed result is a real
``tool_result`` bound to the model's original ``tool_call_id`` (not an orphaned
``tool_use``).
"""

import threading
from types import SimpleNamespace

import gimle.hugin.tools  # noqa: F401  (registers bash + bash_output)
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.bash_waiting import BashWaiting
from gimle.hugin.sandbox.background import BackgroundExecutor, result_content
from gimle.hugin.sandbox.fake import FakeSandbox
from gimle.hugin.sandbox.manager import SandboxManager
from gimle.hugin.sandbox.policy import Policy
from gimle.hugin.sandbox.sandbox import ExecResult, SandboxSpec
from gimle.hugin.storage.local import LocalStorage
from gimle.hugin.tools.builtins import bash as bash_mod
from gimle.hugin.tools.builtins.bash import bash
from gimle.hugin.tools.builtins.bash_output import bash_output

from .conftest import ScriptedToolModel

LOCAL = SandboxSpec(backend="local")


def _manager(fake: FakeSandbox) -> SandboxManager:
    """Return a manager wrapping ``fake`` (its audit is the completion sink)."""
    return SandboxManager(LOCAL, "session-1", sandbox=fake)


def _submit(executor, manager, command="build", **over):
    """Submit ``command`` on ``manager``'s sandbox with sane defaults."""
    kwargs = dict(
        sandbox=manager.get(),
        manager=manager,
        session_id="session-1",
        agent_id="agent-a",
        command=command,
        cwd="/workspace",
        policy=Policy(),
        timeout_s=15,
        max_output_bytes=16_000,
    )
    kwargs.update(over)
    return executor.submit(**kwargs)


class TestBackgroundExecutor:
    """The worker pool + job registry lifecycle."""

    def test_gated_job_is_not_done_until_released(self):
        """A held command reads as running; releasing it flips is_done."""
        gate = threading.Event()
        executor = BackgroundExecutor()
        manager = _manager(FakeSandbox(gate=gate))
        try:
            job = _submit(executor, manager)
            assert executor.is_done(job.job_id) is False
            gate.set()
            assert executor.wait(job.job_id, timeout=2) is True
            assert executor.is_done(job.job_id) is True
        finally:
            gate.set()
            executor.shutdown()

    def test_collect_returns_the_result_content(self):
        """A finished job collects to the same content shape as a sync run."""
        executor = BackgroundExecutor()
        result = ExecResult(
            exit_code=0, stdout="done", stderr="", duration_s=0.0
        )
        manager = _manager(FakeSandbox(result))
        try:
            job = _submit(executor, manager)
            executor.wait(job.job_id, timeout=2)
            content, is_error = executor.collect(job.job_id)
            assert is_error is False
            assert content == result_content("build", result)
        finally:
            executor.shutdown()

    def test_collect_of_a_raising_worker_is_guarded(self):
        """A worker exception collects as infra_error, never raises (no wedge)."""
        executor = BackgroundExecutor()
        manager = _manager(FakeSandbox(raises=RuntimeError("daemon died")))
        try:
            job = _submit(executor, manager)
            executor.wait(job.job_id, timeout=2)
            content, is_error = executor.collect(job.job_id)  # must not raise
            assert is_error is True
            assert "daemon died" in content["infra_error"]
        finally:
            executor.shutdown()

    def test_unknown_job_collects_as_error_not_keyerror(self):
        """An unknown job_id (e.g. lost to a reload) is terminal, not a KeyError."""
        executor = BackgroundExecutor()
        try:
            assert executor.is_done("nope") is True
            content, is_error = executor.collect("nope")
            assert is_error is True
            assert "not found" in content["infra_error"]
        finally:
            executor.shutdown()

    def test_cross_agent_collect_is_refused(self):
        """A job_id is scoped to its owning agent."""
        executor = BackgroundExecutor()
        manager = _manager(FakeSandbox())
        try:
            job = _submit(executor, manager, agent_id="agent-a")
            executor.wait(job.job_id, timeout=2)
            content, is_error = executor.collect(job.job_id, agent_id="agent-b")
            assert is_error is True
            assert "unknown or already-collected" in content["error"]
        finally:
            executor.shutdown()

    def test_completion_is_audited_exactly_once(self):
        """A run is counted once whether the callback or the collect records it."""
        executor = BackgroundExecutor()
        manager = _manager(FakeSandbox())
        try:
            job = _submit(executor, manager)
            executor.wait(job.job_id, timeout=2)
            executor.collect(job.job_id)
            executor.collect(job.job_id)  # a second collect must not re-count
            assert manager.audit.counters["run"] == 1
        finally:
            executor.shutdown()

    def test_fire_and_forget_is_audited_without_collect(self):
        """A job never explicitly collected is still audited (the callback)."""
        executor = BackgroundExecutor()
        manager = _manager(FakeSandbox())
        try:
            job = _submit(executor, manager)
            executor.wait(job.job_id, timeout=2)
            # Give the worker done-callback a moment to run.
            deadline = threading.Event()
            for _ in range(200):
                if manager.audit.counters["run"] == 1:
                    break
                deadline.wait(0.01)
            assert manager.audit.counters["run"] == 1
        finally:
            executor.shutdown()


def _bg_stack(fake: FakeSandbox, executor: BackgroundExecutor):
    """Build a minimal stack whose session owns ``fake`` and ``executor``."""
    manager = SandboxManager(LOCAL, "session-1", sandbox=fake)
    session = SimpleNamespace(
        id="session-1",
        sandboxes={LOCAL: manager},
        background=executor,
    )
    config = SimpleNamespace(options={"bash": {"backend": "local"}})
    agent = SimpleNamespace(
        id="agent-a",
        config=config,
        session=session,
        environment=SimpleNamespace(env_vars={}),
    )
    return SimpleNamespace(agent=agent)


class TestToolSurface:
    """bash(background=true) and bash_output, driven with a gated FakeSandbox."""

    def test_background_true_returns_a_job_id_immediately(self):
        """A backgrounded command returns a running handle without blocking."""
        gate = threading.Event()
        executor = BackgroundExecutor()
        stack = _bg_stack(FakeSandbox(gate=gate), executor)
        try:
            response = bash("build", stack=stack, background=True)
            assert response.is_error is False
            assert response.content["status"] == "running"
            assert "job_id" in response.content
            assert response.response_interaction is None  # fire-and-forget
        finally:
            gate.set()
            executor.shutdown()

    def test_bash_output_parks_while_running_then_collects(self):
        """bash_output returns a BashWaiting while running, the result once done."""
        gate = threading.Event()
        executor = BackgroundExecutor()
        stack = _bg_stack(FakeSandbox(gate=gate), executor)
        try:
            started = bash("build", stack=stack, background=True)
            job_id = started.content["job_id"]

            waiting = bash_output(job_id, stack=stack)
            assert isinstance(waiting.response_interaction, BashWaiting)
            assert waiting.response_interaction.job_id == job_id

            gate.set()
            executor.wait(job_id, timeout=2)
            done = bash_output(job_id, stack=stack)
            assert done.response_interaction is None
            assert done.content["exit_code"] == 0
            assert done.content["stdout"] == "ok"
        finally:
            gate.set()
            executor.shutdown()

    def test_slow_command_auto_defers(self, monkeypatch):
        """A command still running after the grace returns a parked BashWaiting."""
        monkeypatch.setattr(bash_mod, "DEFAULT_DEFER_AFTER_S", 0.05)
        gate = threading.Event()
        executor = BackgroundExecutor()
        stack = _bg_stack(FakeSandbox(gate=gate), executor)
        try:
            response = bash("build", stack=stack)  # no background flag
            assert isinstance(response.response_interaction, BashWaiting)
        finally:
            gate.set()
            executor.shutdown()

    def test_fast_command_returns_inline(self):
        """A command that finishes within the grace returns inline (no waiting)."""
        executor = BackgroundExecutor()
        stack = _bg_stack(FakeSandbox(), executor)
        try:
            response = bash("echo hi", stack=stack)
            assert response.response_interaction is None
            assert response.content["exit_code"] == 0
        finally:
            executor.shutdown()


class TestResumeFullLoop:
    """A real Session/Agent proves the deferred result is a proper tool_result."""

    def test_auto_deferred_command_resolves_to_a_bound_tool_result(
        self, tmp_path, monkeypatch
    ):
        """A parked command resumes into a tool_result bound to the bash call id.

        This is the H1 regression guard: the resume must recover the model's
        original ``tool_call_id`` (like AgentResult), not chain a new id-less
        tool call (which renders as text → an orphaned tool_use → API 400).
        """
        monkeypatch.setattr(bash_mod, "DEFAULT_DEFER_AFTER_S", 0.05)
        gate = threading.Event()
        storage = LocalStorage(base_path=str(tmp_path / "storage"))
        env = Environment.load("examples/bash_agent", storage=storage)
        model_name = "scripted-bg-resume"

        from gimle.hugin.llm.models.model_registry import get_model_registry

        registry = get_model_registry()
        registry.register_model(
            model_name,
            ScriptedToolModel(
                model_name,
                [
                    {"tool": "bash", "input": {"command": "long-build"}},
                    {
                        "tool": "finish",
                        "input": {
                            "finish_type": "success",
                            "result": "built",
                            "reason": "done",
                        },
                    },
                ],
            ),
        )
        try:
            with Session(environment=env) as session:
                config = env.config_registry.get("bash_agent")
                # A gated sandbox so the command is still running at the grace.
                fake = FakeSandbox(
                    ExecResult(
                        exit_code=0,
                        stdout="BUILD-OK",
                        stderr="",
                        duration_s=0.0,
                    ),
                    gate=gate,
                )
                session.sandboxes[LOCAL] = SandboxManager(
                    LOCAL, session.id, sandbox=fake
                )
                config.options["bash"] = {"backend": "local"}
                config.llm_model = model_name
                task = env.task_registry.get("explore")
                session.create_agent_from_task(config, task)
                agent = session.agents[0]

                # Step until the command has parked (BashWaiting on the branch).
                for _ in range(6):
                    agent.step()
                    if _has_bash_waiting(agent):
                        break
                assert _has_bash_waiting(agent), "command did not auto-defer"
                parked = next(
                    i
                    for i in agent.stack.interactions
                    if isinstance(i, BashWaiting)
                )

                # Release the command and let the worker finish before stepping,
                # then the parked branch resolves on its next visit.
                gate.set()
                assert session.background.wait(parked.job_id, timeout=2)
                for _ in range(8):
                    agent.step()

                tool_result = _resolved_tool_result(agent)
                assert tool_result is not None, "no resolved tool_result found"
                # Bound to a real bash tool_call_id — never an id-less text render.
                assert tool_result.prompt.tool_use_id is not None
                assert tool_result.template_inputs.get("stdout") == "BUILD-OK"
        finally:
            registry.models.pop(model_name, None)
            gate.set()


def _has_bash_waiting(agent) -> bool:
    """Whether the agent's stack currently has a parked BashWaiting."""
    return any(isinstance(i, BashWaiting) for i in agent.stack.interactions)


def _resolved_tool_result(agent):
    """Return the AskOracle carrying the resumed bash tool_result, if present."""
    for interaction in agent.stack.interactions:
        if (
            isinstance(interaction, AskOracle)
            and interaction.prompt is not None
            and getattr(interaction.prompt, "type", None) == "tool_result"
            and "stdout" in (interaction.template_inputs or {})
        ):
            return interaction
    return None
