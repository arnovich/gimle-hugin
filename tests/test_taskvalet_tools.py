"""Native bindings must not let one Hugin agent use another participant identity."""

from dataclasses import replace

import pytest

from gimle.hugin.tools.tool import Tool


def test_agent_bound_aliases_isolate_identity_and_close(taskvalet_agents):
    """Keep identities separate and revoke closed references."""
    from gimle.hugin.integrations.taskvalet import bind_taskvalet_tools

    f = taskvalet_agents
    with (
        bind_taskvalet_tools(f.agents[0], f.providers[0]) as first,
        bind_taskvalet_tools(f.agents[1], f.providers[1]) as second,
    ):
        assert first != second
        f.agents[0].config = replace(f.agents[0].config, tools=first)
        f.agents[1].config = replace(f.agents[1].config, tools=second)
        tools = [agent.stack.get_tools()[0] for agent in f.agents]
        assert tools[0].name == tools[1].name == "taskvalet_checkpoint"
        assert all(
            tool.options.include_only_in_context_window for tool in tools
        )
        assert all(tool.options.context_window == 2 for tool in tools)
        assert all(tool.options.context_group == "taskvalet" for tool in tools)
        for index, tool in enumerate(tools):
            result = Tool.execute_tool(
                tool,
                f.agents[index].stack,
                None,
                task="001-test",
                text="checkpoint",
            )
            assert not result.is_error and result.content["actor"] == str(index)
        stolen = Tool.execute_tool(
            tools[0],
            f.agents[1].stack,
            None,
            task="001-test",
            text="wrong identity",
        )
        assert stolen.is_error and len(f.providers[0].calls) == 1
        with pytest.raises(ValueError, match="already bound"):
            with bind_taskvalet_tools(f.agents[0], f.providers[1]):
                pass
    assert Tool.execute_tool(
        tools[0], f.agents[0].stack, None, task="001-test", text="closed"
    ).is_error
    assert all(
        Tool.get_tool(name, throw_error=False) is None
        for name in first + second
    )


def test_binding_preserves_schema_and_unknown_failures_are_sanitized(
    taskvalet_agents,
):
    """Preserve schemas while hiding unexpected exception contents."""
    from gimle.hugin.integrations.taskvalet import bind_taskvalet_tools

    f = taskvalet_agents
    provider = f.providers[0]

    def broken(name, arguments):
        raise RuntimeError("secret credential and private candidate text")

    provider.invoke_result = broken
    with bind_taskvalet_tools(f.agents[0], provider) as names:
        tool = Tool.get_tool(names[0])
        assert tool.input_schema == provider.definitions()[0]["input_schema"]
        result = Tool.execute_tool(
            tool, f.agents[0].stack, None, task="001-test", text="checkpoint"
        )
        assert result.is_error and "secret" not in str(result.content)


def test_native_tool_call_uses_bound_provider(taskvalet_agents):
    """The ordinary interaction path resolves aliases and emits a ToolResult."""
    from gimle.hugin.integrations.taskvalet import bind_taskvalet_tools
    from gimle.hugin.interaction.tool_call import ToolCall
    from gimle.hugin.interaction.tool_result import ToolResult

    f = taskvalet_agents
    agent = f.agents[0]
    with bind_taskvalet_tools(agent, f.providers[0]) as names:
        agent.config = replace(agent.config, tools=names)
        interaction = ToolCall(
            stack=agent.stack,
            tool="taskvalet_checkpoint",
            args={"task": "001-test", "text": "Continue work"},
        )
        assert interaction.step()
        result = agent.stack.interactions[-1]
        assert isinstance(result, ToolResult)
        assert not result.is_error and result.result["actor"] == "0"


def test_registration_failure_rolls_back_and_allows_rebinding(taskvalet_agents):
    """Undo partially installed tools without retaining agent authority."""
    from gimle.hugin.integrations.taskvalet import bind_taskvalet_tools

    f = taskvalet_agents
    provider = f.providers[0]
    definitions = provider.definitions
    valid = definitions()[0]
    provider.definitions = lambda: [
        valid,
        {
            **valid,
            "name": "taskvalet_invalid",
            "input_schema": {"type": "array"},
        },
    ]
    before = set(Tool.registry.registered())
    with pytest.raises(ValueError, match="object"):
        with bind_taskvalet_tools(f.agents[0], provider):
            pass
    assert set(Tool.registry.registered()) == before
    provider.definitions = definitions
    with bind_taskvalet_tools(f.agents[0], provider) as names:
        assert len(names) == 1
