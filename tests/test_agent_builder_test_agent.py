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
        result = test_agent(
            stack=mock_stack,
            agent_path=tmpdir,
            test_prompt="Hello",
        )

        # Should fail because no configs found
        assert isinstance(result, ToolResponse)
        assert result.is_error is True
        assert "No configs found" in result.content["error"]


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
