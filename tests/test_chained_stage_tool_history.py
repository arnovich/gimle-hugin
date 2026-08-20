"""A later stage must not change how an earlier stage's turn is rendered.

Every stage of a task chain runs on the SAME stack, so when a later stage asks
the oracle it re-renders the whole history. ``OracleResponse.tool_call_id``
resolved the called tool against ``stack.get_tools()`` -- the tools visible
*now* -- rather than the tools visible when the call was made. A tool with
``respond_with_text`` renders as plain text (no ``tool_use`` block, and so
nothing owing it a ``tool_result``). Drop that tool from a later stage's list
and the same historical turn suddenly renders as a ``tool_use`` that nothing
answers, and the provider rejects the whole request:

    messages.14: `tool_use` ids were found without `tool_result` blocks
    immediately after: toolu_...

``finish`` is exactly such a tool and ends every builder stage, so any stage
that did not re-list ``finish`` failed 100% of builds. This is the same class
of bug the ``tool_context_policy`` snapshot already guards against: history
must not be re-interpreted through the present.
"""

import pytest

from gimle.hugin.agent.task import Task
from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.oracle_response import OracleResponse
from gimle.hugin.interaction.stack import Stack
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.llm.prompt.prompt import Prompt
from gimle.hugin.tools.tool import Tool, ToolConfig

TOOL_USE_ID = "toolu_stage_one_finish"


@pytest.fixture
def text_tool():
    """A terminating tool that answers with text rather than a tool_use."""
    tool = Tool(
        name="spy_finish",
        description="Ends a stage",
        parameters={},
        is_interactive=False,
        implementation_path="",
        options=ToolConfig(respond_with_text=True),
    )
    Tool.registry.register(tool, name=tool.name)
    yield tool
    Tool.registry._items.pop(tool.name, None)


def _chained_stack(mock_agent, second_stage_tools):
    """Stage one calls ``spy_finish``; stage two lists ``second_stage_tools``."""
    stack = Stack(agent=mock_agent)

    def task(name, tools):
        return Task(
            name=name,
            description="d",
            parameters={},
            prompt="go",
            tools=tools,
        )

    stack.add_interaction(
        TaskDefinition(stack=stack, task=task("stage_one", ["spy_finish"]))
    )
    stack.add_interaction(
        AskOracle(
            stack=stack,
            prompt=Prompt(type="text", text="build it"),
            template_inputs={},
        )
    )
    stack.add_interaction(
        OracleResponse(
            stack=stack,
            response={
                "content": {"result": "stage one done"},
                "tool_call": "spy_finish",
                "tool_call_id": TOOL_USE_ID,
            },
        )
    )
    # The chain swaps the task on the same stack -- no new stack, no reset.
    stack.add_interaction(
        TaskDefinition(stack=stack, task=task("stage_two", second_stage_tools))
    )
    stack.add_interaction(
        AskOracle(
            stack=stack,
            prompt=Prompt(type="text", text="review it"),
            template_inputs={},
        )
    )
    return stack


def _unanswered(messages):
    """Return tool_use ids with no tool_result anywhere in ``messages``."""
    opened, closed = [], set()
    for message in messages:
        content = message["content"]
        if not isinstance(content, list):
            continue
        for part in content:
            if part.get("type") == "tool_use":
                opened.append(part["id"])
            elif part.get("type") == "tool_result":
                closed.add(part.get("tool_use_id"))
    return [use_id for use_id in opened if use_id not in closed]


class TestHistoryIsRenderedAsItHappened:
    """The later stage's tool list must not rewrite the earlier stage."""

    def test_dropping_the_tool_does_not_orphan_its_turn(
        self, mock_agent, text_tool
    ):
        """The regression: stage two no longer lists the tool stage one used."""
        stack = _chained_stack(mock_agent, second_stage_tools=["some_other"])

        messages = stack.render_stack_context(branch=None)

        assert _unanswered(messages) == []

    def test_relisting_the_tool_is_still_fine(self, mock_agent, text_tool):
        """The pre-existing arrangement keeps working."""
        stack = _chained_stack(mock_agent, second_stage_tools=["spy_finish"])

        messages = stack.render_stack_context(branch=None)

        assert _unanswered(messages) == []

    def test_the_turn_renders_the_same_either_way(self, mock_agent, text_tool):
        """Rendering must not depend on the current stage's tool list at all."""
        dropped = _chained_stack(mock_agent, ["some_other"])
        relisted = _chained_stack(mock_agent, ["spy_finish"])

        assert dropped.render_stack_context(
            branch=None
        ) == relisted.render_stack_context(branch=None)
