"""Tests for agent builder generate config tool."""

import yaml


def test_agent_builder_generate_config_always_includes_save_tools(mock_stack):
    """Test that generate_config always includes required save tools."""
    from gimle.hugin.apps.agent_builder.tools.generate_config import (
        generate_config,
    )

    resp = generate_config(
        agent_name="my_agent",
        description="desc",
        system_template="sys",
        llm_model="test-model",
        tools=[],
        stack=mock_stack,
    )
    assert resp.is_error is False

    content = resp.content["content"]
    data = yaml.safe_load(content)
    tools = data["tools"]
    assert "builtins.save_text:save_text" in tools
    assert "builtins.save_file:save_file" in tools
    assert "builtins.finish:finish" in tools
