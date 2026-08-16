"""Tests for agent builder test_agent tool."""

import tempfile
from pathlib import Path

from gimle.hugin.interaction.agent_call import AgentCall
from gimle.hugin.tools.tool import ToolResponse


def test_test_agent_with_nonexistent_path(mock_stack):
    """Test that test_agent returns error for non-existent path."""
    from gimle.hugin.apps.agent_builder.tools.test_agent import test_agent

    result = test_agent(
        stack=mock_stack,
        agent_path="/nonexistent/path",
        test_prompt="Hello",
    )

    assert isinstance(result, ToolResponse)
    assert result.is_error is True
    assert "does not exist" in result.content["error"]


def test_test_agent_with_empty_directory(mock_stack):
    """Test that test_agent returns error for empty directory."""
    from gimle.hugin.apps.agent_builder.tools.test_agent import test_agent

    with tempfile.TemporaryDirectory() as tmpdir:
        cache = Path(tmpdir) / "package" / "__pycache__"
        cache.mkdir(parents=True)
        bytecode = cache / "valuable.cpython-312.pyc"
        bytecode.write_bytes(b"unrelated")
        result = test_agent(
            stack=mock_stack,
            agent_path=tmpdir,
            test_prompt="Hello",
        )

        # Should fail because no configs found
        assert isinstance(result, ToolResponse)
        assert result.is_error is True
        assert "No configs found" in result.content["error"]
        assert bytecode.read_bytes() == b"unrelated"


def test_test_agent_with_config_but_no_tasks(mock_stack):
    """Test that test_agent returns error when configs exist but no tasks."""
    from gimle.hugin.apps.agent_builder.tools.test_agent import test_agent

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a config file
        config_dir = Path(tmpdir) / "configs"
        config_dir.mkdir()
        config_file = config_dir / "test_agent.yaml"
        config_file.write_text(
            """
name: test_agent
description: A test agent
system_template: system
llm_model: test-model
tools:
  - builtins.finish:finish
"""
        )

        result = test_agent(
            stack=mock_stack,
            agent_path=tmpdir,
            test_prompt="Hello",
        )

        # Should fail because no tasks found
        assert isinstance(result, ToolResponse)
        assert result.is_error is True
        assert "No tasks found" in result.content["error"]


def test_test_agent_with_valid_agent_returns_agent_call(mock_stack):
    """Test that test_agent returns AgentCall for a valid agent."""
    from gimle.hugin.apps.agent_builder.tools.test_agent import test_agent

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create minimal agent structure
        config_dir = Path(tmpdir) / "configs"
        config_dir.mkdir()
        task_dir = Path(tmpdir) / "tasks"
        task_dir.mkdir()
        template_dir = Path(tmpdir) / "templates"
        template_dir.mkdir()

        # Config file
        config_file = config_dir / "test_agent.yaml"
        config_file.write_text(
            """
name: test_agent
description: A test agent
system_template: system
llm_model: test-model
tools:
  - builtins.finish:finish
"""
        )

        # Task file
        task_file = task_dir / "main.yaml"
        task_file.write_text(
            """
name: main
description: Main task
parameters: {}
prompt: |
  Do something and call finish.
"""
        )

        # Template file
        template_file = template_dir / "system.yaml"
        template_file.write_text(
            """
name: system
template: |
  You are a test agent.
"""
        )

        result = test_agent(
            stack=mock_stack,
            agent_path=tmpdir,
            test_prompt="Say hello",
        )

        # Should return an AgentCall to spawn the test agent
        assert isinstance(result, AgentCall)
        assert result.config is not None
        assert result.config.name == "test_test_agent"
        assert result.task is not None
        assert result.task.prompt == "Say hello"


def test_test_agent_with_syntax_error_in_tool(mock_stack):
    """Test that test_agent catches syntax errors in tools."""
    from gimle.hugin.apps.agent_builder.tools.test_agent import test_agent

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create minimal agent structure with a broken tool
        config_dir = Path(tmpdir) / "configs"
        config_dir.mkdir()
        task_dir = Path(tmpdir) / "tasks"
        task_dir.mkdir()
        template_dir = Path(tmpdir) / "templates"
        template_dir.mkdir()
        tool_dir = Path(tmpdir) / "tools"
        tool_dir.mkdir()

        # Config file
        config_file = config_dir / "test_agent.yaml"
        config_file.write_text(
            """
name: test_agent
description: A test agent
system_template: system
llm_model: test-model
tools:
  - broken_tool
  - builtins.finish:finish
"""
        )

        # Task file
        task_file = task_dir / "main.yaml"
        task_file.write_text(
            """
name: main
description: Main task
parameters: {}
prompt: |
  Test the broken tool.
"""
        )

        # Template file
        template_file = template_dir / "system.yaml"
        template_file.write_text(
            """
name: system
template: |
  You are a test agent.
"""
        )

        # Tool YAML file
        tool_yaml = tool_dir / "broken_tool.yaml"
        tool_yaml.write_text(
            """
name: broken_tool
description: A broken tool
parameters: {}
implementation_path: broken_tool:broken_tool
"""
        )

        # Tool Python file with syntax error
        tool_py = tool_dir / "broken_tool.py"
        tool_py.write_text(
            """
# This has a syntax error
def broken_tool(
    this is not valid python
"""
        )

        result = test_agent(
            stack=mock_stack,
            agent_path=tmpdir,
            test_prompt="Test",
        )

        # Should report syntax error
        assert isinstance(result, ToolResponse)
        assert result.is_error is True
        assert "Syntax error" in result.content["error"]


def _write_agent_with_tool(root, agent_name, tool_name, module_name, value):
    """Write a minimal valid agent with one custom tool."""
    root = Path(root)
    for folder in ("configs", "tasks", "templates", "tools"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / "configs" / f"{agent_name}.yaml").write_text(
        f"name: {agent_name}\n"
        "description: test agent\n"
        "system_template: system\n"
        "tools:\n"
        f"  - {tool_name}\n"
        "  - builtins.finish:finish\n"
    )
    (root / "tasks" / "main.yaml").write_text(
        "name: main\ndescription: main\nparameters: {}\n"
        "prompt: Run the custom tool.\n"
    )
    (root / "templates" / "system.yaml").write_text(
        "name: system\ntemplate: You are a test agent.\n"
    )
    (root / "tools" / f"{module_name}.yaml").write_text(
        f"name: {tool_name}\n"
        "description: custom tool\nparameters: {}\n"
        f"implementation_path: {module_name}:implementation\n"
    )
    (root / "tools" / f"{module_name}.py").write_text(
        f"def implementation():\n    return {value!r}\n"
    )


def test_two_agents_with_the_same_module_name_load_their_own_code(
    mock_stack, tmp_path, monkeypatch
):
    """A bare module cached for agent A must not become agent B's code."""
    import sys

    from gimle.hugin.apps.agent_builder.tools.test_agent import test_agent
    from gimle.hugin.tools.tool import Tool
    from gimle.hugin.utils.registry import Registry

    monkeypatch.setattr(Tool, "registry", Registry())
    first = tmp_path / "first"
    second = tmp_path / "second"
    module = "pr97_shared_implementation"
    _write_agent_with_tool(first, "first", "pr97_first_tool", module, "first")
    _write_agent_with_tool(
        second, "second", "pr97_second_tool", module, "second"
    )
    original_path = list(sys.path)
    try:
        assert isinstance(test_agent(mock_stack, str(first), "test"), AgentCall)
        assert isinstance(
            test_agent(mock_stack, str(second), "test"), AgentCall
        )

        assert Tool.registry.get("pr97_second_tool").func() == "second"
    finally:
        sys.path[:] = original_path
        sys.modules.pop(module, None)


def test_generated_tool_registry_collision_is_refused(
    mock_stack, tmp_path, monkeypatch
):
    """Loading generated code must opt into strict global registration."""
    import sys

    from gimle.hugin.apps.agent_builder.tools.test_agent import test_agent
    from gimle.hugin.tools.tool import Tool
    from gimle.hugin.utils.registry import Registry

    monkeypatch.setattr(Tool, "registry", Registry())
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_agent_with_tool(
        first, "first", "pr97_collision", "pr97_first_impl", "first"
    )
    _write_agent_with_tool(
        second, "second", "pr97_collision", "pr97_second_impl", "second"
    )
    original_path = list(sys.path)
    try:
        assert isinstance(test_agent(mock_stack, str(first), "test"), AgentCall)

        result = test_agent(mock_stack, str(second), "test")

        assert isinstance(result, ToolResponse)
        assert result.is_error
        assert "already registered" in result.content["error"]
        assert Tool.registry.get("pr97_collision").func() == "first"
    finally:
        sys.path[:] = original_path
        sys.modules.pop("pr97_first_impl", None)
        sys.modules.pop("pr97_second_impl", None)


def test_failed_tool_import_does_not_poison_the_registry(
    mock_stack, tmp_path, monkeypatch
):
    """A repair can retry after an implementation fails to import."""
    import sys

    from gimle.hugin.apps.agent_builder.tools.test_agent import test_agent
    from gimle.hugin.tools.tool import Tool
    from gimle.hugin.utils.registry import Registry

    monkeypatch.setattr(Tool, "registry", Registry())
    agent = tmp_path / "agent"
    module = "pr97_broken_import"
    tool_name = "pr97_import_repair"
    _write_agent_with_tool(agent, "demo", tool_name, module, "unused")
    (agent / "tools" / f"{module}.py").write_text(
        "import pr97_dependency_that_does_not_exist\n\n"
        "def implementation():\n    return 'unused'\n"
    )
    original_path = list(sys.path)
    try:
        result = test_agent(mock_stack, str(agent), "test")

        assert isinstance(result, ToolResponse)
        assert result.is_error
        assert tool_name not in Tool.registry.registered()
    finally:
        sys.path[:] = original_path
        sys.modules.pop(module, None)


def test_retesting_one_agent_replaces_its_own_tool(
    mock_stack, tmp_path, monkeypatch
):
    """Strict collision checks must still permit a repair of the same agent."""
    import sys

    from gimle.hugin.apps.agent_builder.tools.test_agent import test_agent
    from gimle.hugin.tools.tool import Tool
    from gimle.hugin.utils.registry import Registry

    monkeypatch.setattr(Tool, "registry", Registry())
    agent = tmp_path / "agent"
    module = "pr97_repaired_impl"
    _write_agent_with_tool(agent, "demo", "pr97_repaired", module, "first")
    original_path = list(sys.path)
    try:
        assert isinstance(test_agent(mock_stack, str(agent), "test"), AgentCall)
        (agent / "tools" / f"{module}.py").write_text(
            "def implementation():\n    return 'other'\n"
        )

        assert isinstance(test_agent(mock_stack, str(agent), "test"), AgentCall)
        assert Tool.registry.get("pr97_repaired").func() == "other"
    finally:
        sys.path[:] = original_path
        sys.modules.pop(module, None)


def test_explicit_jinja_system_template_is_inlined(mock_stack, tmp_path):
    """Removing template-registry copying must preserve explicit references."""
    from gimle.hugin.apps.agent_builder.tools.test_agent import test_agent

    config = tmp_path / "configs"
    task = tmp_path / "tasks"
    template = tmp_path / "templates"
    config.mkdir()
    task.mkdir()
    template.mkdir()
    (config / "demo.yaml").write_text(
        "name: demo\ndescription: demo\n"
        'system_template: "{{ demo_system.template }}"\n'
        "tools:\n  - builtins.finish:finish\n"
    )
    (task / "main.yaml").write_text(
        "name: main\ndescription: main\nparameters: {}\nprompt: Finish.\n"
    )
    (template / "system.yaml").write_text(
        "name: demo_system\ntemplate: The actual system prompt.\n"
    )

    result = test_agent(mock_stack, str(tmp_path), "test")

    assert isinstance(result, AgentCall)
    assert result.config.system_template == "The actual system prompt."


def test_multiple_definitions_require_and_honor_explicit_names(
    mock_stack, tmp_path
):
    """Selection must not silently depend on filesystem iteration order."""
    from gimle.hugin.apps.agent_builder.tools.test_agent import test_agent

    for folder in ("configs", "tasks", "templates"):
        (tmp_path / folder).mkdir()
    (tmp_path / "templates" / "system.yaml").write_text(
        "name: system\ntemplate: system prompt\n"
    )
    for name in ("one", "two"):
        (tmp_path / "configs" / f"{name}.yaml").write_text(
            f"name: {name}\ndescription: {name}\nsystem_template: system\n"
            "tools:\n  - builtins.finish:finish\n"
        )
        (tmp_path / "tasks" / f"{name}.yaml").write_text(
            f"name: {name}\ndescription: {name}\nparameters: {{}}\n"
            f"prompt: Run {name}.\n"
        )

    ambiguous = test_agent(mock_stack, str(tmp_path), "test")
    selected = test_agent(
        mock_stack,
        str(tmp_path),
        "test",
        config_name="two",
        task_name="two",
    )

    assert isinstance(ambiguous, ToolResponse)
    assert "specify config_name" in ambiguous.content["error"]
    assert isinstance(selected, AgentCall)
    assert selected.config.name == "test_two"
    assert selected.task.name == "test_two"


def test_tool_schema_exposes_definition_selectors():
    """The model can only pass parameters declared by the YAML tool schema."""
    import yaml

    definition = yaml.safe_load(
        Path(
            "src/gimle/hugin/apps/agent_builder/tools/test_agent.yaml"
        ).read_text()
    )

    assert {"config_name", "task_name"} <= set(definition["parameters"])
