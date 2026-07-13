"""End-to-end drive of the examples/bash_agent example through the real loop.

Loads the shipped example directory (validating its YAML, tool references, and
config), then runs a real Session with a scripted no-API model that calls
``bash`` and then ``finish``. This proves the whole path works together: the
example loads, the ``builtins.bash:bash`` alias resolves in a real run, the
step loop executes the tool against a real LocalSandbox, and a real file lands
in the agent's workspace.
"""

import os
from typing import Any, Dict, List

import pytest

import gimle.hugin.tools  # noqa: F401  (registers builtins.bash)
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.llm.models.model import Model, ModelResponse
from gimle.hugin.llm.models.model_registry import get_model_registry
from gimle.hugin.sandbox import LocalSandbox, SandboxManager, SandboxSpec
from gimle.hugin.storage.local import LocalStorage

pytestmark = pytest.mark.integration

EXAMPLE = "examples/bash_agent"
MODEL_NAME = "scripted-bash-e2e"
SPEC = SandboxSpec(backend="local")


class _ScriptedModel(Model):
    """A model that replays a fixed sequence of tool calls (no network)."""

    def __init__(self, script: List[Dict[str, Any]]):
        """Replay ``script`` entries (``{tool, input}``) one call at a time."""
        super().__init__(
            {
                "model": MODEL_NAME,
                "temperature": 0,
                "max_tokens": 100,
                "tool_choice": {"type": "any"},
            }
        )
        self._script = script
        self._i = 0

    def chat_completion(self, system_prompt, messages, tools=None):
        """Return the next scripted tool call as a ModelResponse."""
        entry = self._script[min(self._i, len(self._script) - 1)]
        self._i += 1
        return ModelResponse(
            role="assistant",
            content=entry["input"],
            tool_call=entry["tool"],
            tool_call_id=f"call-{self._i}",
            input_tokens=1,
            output_tokens=1,
        )


def test_bash_example_loads_and_runs(tmp_path):
    """The example loads, runs the loop, and bash creates a real file."""
    storage = LocalStorage(base_path=str(tmp_path / "storage"))
    env = Environment.load(EXAMPLE, storage=storage)
    session = Session(environment=env)

    # Real LocalSandbox rooted under tmp so the run doesn't touch repo storage.
    sandbox = LocalSandbox(
        SPEC, session.id, workspace_root=str(tmp_path / "sb")
    )
    env.env_vars["sandbox"] = SandboxManager(SPEC, session.id, sandbox=sandbox)

    # Scripted model: write a file with bash, then finish.
    registry = get_model_registry()
    registry.register_model(
        MODEL_NAME,
        _ScriptedModel(
            [
                {
                    "tool": "bash",
                    "input": {"command": "echo hello-from-bash > marker.txt"},
                },
                {
                    "tool": "finish",
                    "input": {
                        "finish_type": "success",
                        "result": "wrote marker.txt",
                        "reason": "task complete",
                    },
                },
            ]
        ),
    )
    try:
        config = env.config_registry.get("bash_agent")
        task = env.task_registry.get("explore")
        session.create_agent_from_task(config, task)
        agent = session.agents[0]
        agent.config.llm_model = MODEL_NAME  # avoid a real LLM call

        for _ in range(10):
            if not agent.step():
                break

        markers = list((tmp_path / "sb").rglob("marker.txt"))
        assert markers, "bash did not create the expected file in the workspace"
        assert markers[0].read_text().strip() == "hello-from-bash"
    finally:
        registry.models.pop(MODEL_NAME, None)


def test_example_config_wires_the_bash_tool(tmp_path):
    """Loading the example exposes the bash tool with the sandbox config."""
    storage = LocalStorage(base_path=str(tmp_path / "storage"))
    env = Environment.load(EXAMPLE, storage=storage)
    config = env.config_registry.get("bash_agent")
    assert "builtins.bash:bash" in config.tools
    assert config.options["bash"]["backend"] == "local"
    assert os.path.isdir(EXAMPLE)
