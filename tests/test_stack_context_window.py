"""Context-window capping must actually cap.

``ToolConfig.include_only_in_context_window`` / ``context_window`` have existed
since the first commit, and never once took effect: the render loop gated the
whole branch on ``tool_call in self.get_tools()``, which compares a ``str``
tool name against a ``List[Tool]`` of dataclasses and is therefore always
False. Every tool result accumulated in the stack forever.

These tests pin the behaviour rather than the option values, so a regression in
the gate is caught instead of a YAML edit.
"""

import pytest

from gimle.hugin.agent.task import Task
from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.stack import Stack
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.llm.prompt.prompt import Prompt
from gimle.hugin.tools.tool import Tool, ToolConfig


@pytest.fixture
def capped_tool():
    """Register a tool that keeps only its most recent result."""
    name = "spy_capped_tool"
    tool = Tool(
        name=name,
        description="A tool whose results should not accumulate",
        parameters={},
        is_interactive=False,
        implementation_path="",
        options=ToolConfig(
            include_only_in_context_window=True, context_window=1
        ),
    )
    Tool.registry.register(tool, name=name)
    yield tool
    Tool.registry._items.pop(name, None)


def _stack_with_results(mock_agent, tool_name, count):
    """Build a stack holding ``count`` results from ``tool_name``."""
    stack = Stack(agent=mock_agent)
    stack.add_interaction(
        TaskDefinition(
            stack=stack,
            task=Task(
                name="t",
                description="d",
                parameters={},
                prompt="go",
                tools=[],
            ),
        )
    )
    for index in range(count):
        stack.add_interaction(
            AskOracle(
                stack=stack,
                prompt=Prompt(
                    type="text",
                    text=f"result number {index}",
                    tool_name=tool_name,
                ),
                template_inputs={},
            )
        )
    return stack


class TestCapIsApplied:
    """The option must change what the model actually sees."""

    def test_older_results_drop_out(self, mock_agent, capped_tool):
        """With context_window=1 only the most recent result survives."""
        stack = _stack_with_results(mock_agent, capped_tool.name, 3)

        rendered = str(stack.render_stack_context(branch=None))

        assert "result number 2" in rendered
        assert "result number 0" not in rendered

    def test_uncapped_tool_still_accumulates(self, mock_agent):
        """Tools without the option are unaffected by the fix."""
        stack = _stack_with_results(mock_agent, "some_unregistered_tool", 3)

        rendered = str(stack.render_stack_context(branch=None))

        assert "result number 0" in rendered
        assert "result number 2" in rendered


class TestTheOriginalDefect:
    """Documents why the lookup is by name and not by membership."""

    def test_membership_of_get_tools_is_always_false(self, capped_tool):
        """get_tools() returns List[Tool]; a str never compares equal."""
        assert capped_tool.name not in [capped_tool]

    def test_cap_survives_a_config_that_omits_the_tool(
        self, mock_agent, capped_tool
    ):
        """A task chain swaps config mid-run; the cap must not switch off.

        The builder's reviewer stage runs under a config listing only finish,
        on the same stack, so a config-scoped cap would let every earlier
        result re-enter context at the largest call of the run.
        """
        stack = _stack_with_results(mock_agent, capped_tool.name, 3)
        mock_agent.config.tools = ["builtins.finish:finish"]

        rendered = str(stack.render_stack_context(branch=None))

        assert "result number 0" not in rendered
