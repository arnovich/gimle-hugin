"""Pytest configuration and fixtures."""

from pathlib import Path
from typing import Any, Dict, List

import pytest

# Import tools package to ensure finish tool is registered
import gimle.hugin.tools  # noqa: F401
from gimle.hugin.agent.config import Config
from gimle.hugin.llm.models.model import Model, ModelResponse
from gimle.hugin.llm.models.model_registry import ModelRegistry
from gimle.hugin.storage.local import LocalStorage

# Import mock dependencies first
from .mock_dependencies import MockTool


@pytest.fixture
def extension_trust_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Any:
    """Provide stored sessions and real extensions that record their imports."""
    import json
    import sys
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from gimle.hugin.agent.environment import Environment
    from gimle.hugin.agent.session import Session
    from gimle.hugin.agent.task import Task
    from gimle.hugin.cli import monitor_agents

    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.setattr(Environment, "_loaded_extensions", set())
    storage_path = tmp_path / "storage"
    storage = LocalStorage(base_path=str(storage_path))
    session = Session(environment=Environment(storage=storage))
    agent = session.create_agent_from_task(
        Config(name="probe", description="Probe", system_template="Probe"),
        Task(name="probe", description="Probe", prompt="Probe"),
    )
    storage.save_session(session)
    paths = {}
    for name in ("attacker", "trusted"):
        package = tmp_path / f"extension_trust_{name}"
        extensions = package / "artifact_types"
        extensions.mkdir(parents=True)
        marker = tmp_path / f"{name}_imported"
        (extensions / "probe.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('imported')\n"
        )
        paths[name] = package
        paths[f"{name}_marker"] = marker
    (storage_path / ".hugin_metadata.json").write_text(
        json.dumps({"package_paths": [str(paths["attacker"])]})
    )
    server = MagicMock()
    server.serve_forever.side_effect = KeyboardInterrupt
    monkeypatch.setattr(
        monitor_agents, "ThreadingHTTPServer", lambda *a: server
    )
    monkeypatch.setattr(
        monitor_agents, "_watch_storage_directory", lambda *a: None
    )
    handler = monitor_agents.AgentMonitorHTTPRequestHandler
    monkeypatch.setattr(handler, "_storage_path", str(storage_path))
    monkeypatch.setattr(handler, "_config_path", None)
    try:
        yield SimpleNamespace(
            storage_path=storage_path,
            storage=storage,
            session=session,
            agent=agent,
            **paths,
        )
    finally:
        session.close()
        for name in list(sys.modules):
            if name.startswith("extension_trust_"):
                del sys.modules[name]


class MockModel(Model):
    """Mock model for testing without actual LLM calls."""

    def __init__(
        self, config: Dict[str, Any], mock_response: Dict[str, Any] = None
    ):
        """Initialize the mock model."""
        super().__init__(config)
        self.mock_response = mock_response or {
            "role": "assistant",
            "content": "This is a mock response",
            "input_tokens": 10,
            "output_tokens": 5,
        }
        self.call_count = 0

    def chat_completion(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Any] = None,
    ) -> ModelResponse:
        """Mock implementation that returns a predefined response."""
        self.call_count += 1
        # Simulate some processing time
        import time

        time.sleep(0.001)

        return ModelResponse(
            role=self.mock_response["role"],
            content=self.mock_response["content"],
            input_tokens=self.mock_response.get("input_tokens"),
            output_tokens=self.mock_response.get("output_tokens"),
            extra_content={
                "call_count": self.call_count,
                "system_prompt": system_prompt,
                "message_count": len(messages),
                "tool_count": len(tools) if tools else 0,
            },
        )


class ScriptedToolModel(Model):
    """A model that replays a fixed sequence of tool calls (no network).

    Each script entry is a ``{"tool": name, "input": {...}}`` dict, returned one
    per ``chat_completion`` call; the last entry repeats once the script is
    exhausted. Shared by the bash full-loop suites so the scripted-drive pattern
    lives in exactly one place.
    """

    def __init__(self, name: str, script: List[Dict[str, Any]]):
        """Replay ``script`` entries under model id ``name``."""
        super().__init__(
            {
                "model": name,
                "temperature": 0,
                "max_tokens": 100,
                "tool_choice": {"type": "any"},
            }
        )
        self._script = script
        self._i = 0

    def chat_completion(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Any] = None,
    ) -> ModelResponse:
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


@pytest.fixture
def mock_model_config():
    """Return standard configuration for mock models."""
    return {
        "model": "test-model",
        "temperature": 0.7,
        "max_tokens": 1000,
        "tool_choice": {"type": "auto"},
    }


@pytest.fixture
def mock_model(mock_model_config):
    """Create a mock model instance."""
    return MockModel(mock_model_config)


@pytest.fixture
def mock_model_with_custom_response(mock_model_config):
    """Create a mock model with custom response."""
    custom_response = {
        "role": "assistant",
        "content": "Custom mock response",
        "input_tokens": 20,
        "output_tokens": 10,
    }
    return MockModel(mock_model_config, custom_response)


@pytest.fixture
def model_registry():
    """Create a fresh model registry for testing."""
    return ModelRegistry()


@pytest.fixture
def sample_messages():
    """Sample messages for testing."""
    return [
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I'm doing well, thank you!"},
        {"role": "user", "content": "What's the weather like?"},
    ]


@pytest.fixture
def sample_tools():
    """Sample tools for testing."""
    tool1 = MockTool(
        name="get_weather",
        description="Get current weather information",
        parameters={
            "location": {
                "type": "string",
                "description": "City name",
                "required": True,
            }
        },
    )

    tool2 = MockTool(
        name="calculate",
        description="Perform mathematical calculations",
        parameters={
            "expression": {
                "type": "string",
                "description": "Math expression",
                "required": True,
            }
        },
    )

    return [tool1, tool2]


@pytest.fixture
def sample_system_prompt():
    """Sample system prompt for testing."""
    return "You are a helpful AI assistant. Please respond to user queries."


@pytest.fixture
def mock_session():
    """Create a mock session for testing."""
    from gimle.hugin.agent.environment import Environment
    from gimle.hugin.agent.session import Session

    environment = Environment(storage=LocalStorage())
    return Session(environment=environment)


@pytest.fixture
def mock_agent(mock_session):
    """Create a mock agent with stack for testing."""
    from unittest.mock import Mock

    from gimle.hugin.agent.agent import Agent

    agent_config = Config(
        llm_model="test-model",
        system_template="system",
        name="test-agent",
        description="Test agent",
    )
    agent = Agent(session=mock_session, config=agent_config)
    # Add agent_type for renderer compatibility
    agent.agent_type = "default"
    # Add agent_registry to session for renderer compatibility
    if not hasattr(mock_session, "agent_registry"):
        mock_session.agent_registry = {
            "default": {"system": "You are a helpful AI assistant."}
        }
    # Environment is already set up with template_registry
    # Add agent_dwh for renderer compatibility
    if not hasattr(mock_session, "agent_dwh"):
        mock_agent_dwh = Mock()
        mock_agent_dwh.dialect = "default"
        mock_session.agent_dwh = mock_agent_dwh
    return agent


@pytest.fixture
def mock_stack(mock_agent):
    """Create a mock stack for testing."""
    return mock_agent.stack


@pytest.fixture
def sample_prompt():
    """Create a sample Prompt object for testing."""
    from gimle.hugin.llm.prompt.prompt import Prompt

    return Prompt(type="text", text="Test prompt")


@pytest.fixture
def builder_cli_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Script a real four-stage builder run, recording its session and loop."""
    import sys
    from copy import deepcopy
    from types import SimpleNamespace

    from gimle.hugin.cli import create_agent, improve_agent, ui
    from gimle.hugin.llm.models.model_registry import get_model_registry

    output = tmp_path / "generated"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.setattr(
        create_agent,
        "setup_file_logging",
        lambda log_dir, log_level: tmp_path / "builder.log",
    )
    monkeypatch.delenv("HUGIN_CTRLRTN", raising=False)
    monkeypatch.setattr(ui.AnimatedSpinner, "start", lambda self: None)
    monkeypatch.setattr(ui.AnimatedSpinner, "stop", lambda *a, **kw: None)

    def finish(result: str) -> Dict[str, Any]:
        """Build a scripted successful finish call."""
        return {
            "tool": "finish",
            "input": {"finish_type": "success", "result": result},
        }

    builder_script = [
        {
            "tool": "generate_config",
            "input": {
                "agent_name": "demo",
                "description": "Say hello",
                "system_template": "demo_system",
                "llm_model": "haiku-latest",
                "tools": ["builtins.finish:finish"],
            },
        },
        {
            "tool": "generate_template",
            "input": {
                "template_name": "demo_system",
                "template_content": "Say hello and finish.",
            },
        },
        {
            "tool": "generate_task",
            "input": {
                "task_name": "hello",
                "description": "Say hello",
                "prompt": "Say hello and finish.",
            },
        },
        finish("Preview ready"),
        finish("APPROVED"),
        {"tool": "write_and_finish", "input": {"result": "Agent written"}},
        {
            "tool": "test_agent",
            "input": {"agent_path": str(output), "test_prompt": "Say hello"},
        },
        finish("Child test reviewed"),
    ]
    child_script = [finish("Hello from the generated child")]
    builder = ScriptedToolModel("sonnet-latest", builder_script)
    child = ScriptedToolModel("haiku-latest", child_script)
    registry = get_model_registry()
    monkeypatch.setitem(registry.models, "sonnet-latest", builder)
    monkeypatch.setitem(registry.models, "haiku-latest", child)

    observed = SimpleNamespace(
        output=output,
        builder_script=builder_script,
        child_script=child_script,
        child=child,
        messages=[],
        session=None,
        steps=None,
        error=None,
        closed=False,
    )
    completion = builder.chat_completion

    def record_completion(
        system_prompt: str, messages: List[Dict[str, Any]], tools: Any = None
    ) -> ModelResponse:
        """Keep the actual model context, including returned child results."""
        observed.messages.append(deepcopy(messages))
        return completion(system_prompt, messages, tools)

    monkeypatch.setattr(builder, "chat_completion", record_completion)
    run_loop = ui.run_steps_with_spinner
    close_session = create_agent.Session.close

    def record_loop(**kwargs: Any) -> tuple[int, Exception | None]:
        """Observe the production CLI loop without replacing its behavior."""
        observed.session = kwargs["session"]
        observed.steps, observed.error = run_loop(**kwargs)
        return observed.steps, observed.error

    def record_close(session: Any) -> None:
        """Keep cleanup observable while releasing real session resources."""
        observed.closed = True
        close_session(session)

    monkeypatch.setattr(create_agent, "run_steps_with_spinner", record_loop)
    monkeypatch.setattr(improve_agent, "run_steps_with_spinner", record_loop)
    monkeypatch.setattr(create_agent.Session, "close", record_close)
    observed.args = [
        "--yes",
        "--name",
        "demo",
        "--description",
        "Say hello",
        "--output",
        str(output),
    ]
    return observed


@pytest.fixture
def improve_cli_run(
    builder_cli_run: Any, monkeypatch: pytest.MonkeyPatch
) -> Any:
    """Allow delegation in the improve task to exercise its session driver."""
    from gimle.hugin.cli import improve_agent

    run = builder_cli_run
    for directory in ("configs", "tasks"):
        (run.output / directory).mkdir(parents=True)
    (run.output / "configs" / "demo.yaml").write_text(
        "name: demo\ndescription: Say hello\n"
        "system_template: Say hello and finish.\n"
        "llm_model: haiku-latest\ntools: [builtins.finish:finish]\n"
    )
    (run.output / "tasks" / "hello.yaml").write_text(
        "name: hello\ndescription: Say hello\nprompt: Say hello.\n"
    )
    run.builder_script[:] = run.builder_script[-2:]
    load_environment = improve_agent.Environment.load

    def load_with_delegation(*args: Any, **kwargs: Any) -> Any:
        """Model a future improve tool that launches a child agent."""
        env = load_environment(*args, **kwargs)
        # The shipped improve task has no delegating tools today.
        if "improve_agent" in env.task_registry.registered():
            env.task_registry.get("improve_agent").tools.append("test_agent")
        return env

    monkeypatch.setattr(improve_agent.Environment, "load", load_with_delegation)
    run.args = [str(run.output), "--storage-path", str(run.output)]
    return run


@pytest.fixture
def versioned_release_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Any:
    """Run the golden release pipeline with a model that cannot guess its input."""
    from copy import deepcopy
    from types import SimpleNamespace

    from gimle.hugin.agent.environment import Environment
    from gimle.hugin.agent.session import Session
    from gimle.hugin.agent.task import Task
    from gimle.hugin.llm.models.model_registry import get_model_registry
    from tests.evals.golden_set import by_name

    case = by_name("versioned_release_pipeline")
    version = {
        "type": "string",
        "description": "Release version",
        "required": True,
    }
    first = Task(
        name="classify",
        description=case.description,
        prompt="Classify the titles for {{ version.value }}.",
        parameters={"version": deepcopy(version)},
        task_sequence=["write"],
        pass_result_as="classified_titles",
    )
    second = Task(
        name="write",
        description="Write release notes",
        prompt="Release version: {{ version.value }}\nTitles: {{ classified_titles.value }}",
        parameters={"version": deepcopy(version)},
    )
    model = ScriptedToolModel(
        "scripted-version-pipeline",
        [
            {
                "tool": "finish",
                "input": {
                    "finish_type": "success",
                    "result": "Features: faster loading",
                },
            },
            {
                "tool": "finish",
                "input": {
                    "finish_type": "success",
                    "result": "Release written",
                },
            },
        ],
    )
    observed = []
    complete = model.chat_completion

    def record(
        system_prompt: str, messages: List[Dict[str, Any]], tools: Any = None
    ) -> ModelResponse:
        """Record the exact stage prompt rather than the combined history."""
        observed.append(deepcopy(messages[-1]))
        return complete(system_prompt, messages, tools)

    monkeypatch.setattr(model, "chat_completion", record)
    monkeypatch.setitem(
        get_model_registry().models, "scripted-version-pipeline", model
    )
    monkeypatch.delenv("HUGIN_CTRLRTN", raising=False)
    env = Environment(storage=LocalStorage(base_path=str(tmp_path)))
    for task in (first, second):
        env.task_registry.register(task, name=task.name)
    session = Session(environment=env)
    config = Config(
        name=case.name,
        description=case.description,
        system_template="Finish each stage.",
        llm_model="scripted-version-pipeline",
        tools=["builtins.finish:finish"],
    )
    session.create_agent_from_task(
        config, first.set_input_parameters({"version": "0.3.0"})
    )
    try:
        yield SimpleNamespace(case=case, session=session, prompts=observed)
    finally:
        session.close()
