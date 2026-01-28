"""Tests for the finish tool."""

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.task import Task
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.interaction.task_result import TaskResult
from gimle.hugin.interaction.tool_call import ToolCall
from gimle.hugin.interaction.tool_result import ToolResult
from gimle.hugin.tools.builtins.finish import finish_tool
from gimle.hugin.tools.tool import Tool, ToolResponse


class TestFinishTool:
    """Test the finish tool functionality."""

    def test_finish_tool_registered(self):
        """Test that finish tool is registered."""
        # Import to trigger registration
        from gimle.hugin.tools import finish_tool  # noqa: F401

        assert "builtins.finish" in Tool.registry.registered()
        tool = Tool.registry.get("builtins.finish")
        assert tool.name == "builtins.finish"
        assert tool.description.startswith("Finish the current task")

    def test_finish_tool_returns_tool_response(self):
        """Test that finish_tool returns a ToolResponse with TaskResult type."""
        result = finish_tool(
            finish_type="success",
            result=None,
        )

        # finish_tool returns a ToolResponse, not TaskResult directly
        assert isinstance(result, ToolResponse)
        assert result.response_interaction == "TaskResult"
        assert result.content == {"finish_type": "success", "result": None}
        assert result.is_error is False

    def test_finish_tool_with_failure(self):
        """Test finish tool with failure type."""
        result = finish_tool(
            finish_type="failure",
            result=None,
        )

        assert isinstance(result, ToolResponse)
        assert result.response_interaction == "TaskResult"
        assert result.content == {"finish_type": "failure", "result": None}

    def test_finish_tool_default_success(self):
        """Test finish tool with success type."""
        result = finish_tool(
            finish_type="success",
            result=None,
        )

        assert isinstance(result, ToolResponse)
        assert result.content == {"finish_type": "success", "result": None}

    def test_task_result_step_terminates(self, mock_session):
        """Test that TaskResult.step() returns False to terminate flow."""
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=mock_session, config=config)
        stack = agent.stack

        task_definition = TaskDefinition.create_from_task(
            task=Task(
                name="test-task",
                description="Test task",
                parameters={},
                prompt="Test task",
                tools=[],
                system_template="You are a helpful assistant.",
                llm_model="test-model",
            ),
            stack=stack,
        )
        stack.add_interaction(task_definition)

        # Create TaskResult directly (as it would be created by the pipeline)
        task_result = TaskResult(
            stack=stack,
            finish_type="success",
        )

        # TaskResult.step() returns True and adds Waiting interaction
        result = task_result.step()
        assert result is True

        # Verify a Waiting interaction was added to signal termination
        from gimle.hugin.interaction.waiting import Waiting

        last = stack.interactions[-1]
        assert isinstance(last, Waiting)

    def test_finish_tool_via_tool_call(self, mock_session):
        """Test finish tool when called via ToolCall creates TaskResult."""
        # Import to trigger registration
        from gimle.hugin.tools.builtins.finish import finish_tool  # noqa: F401

        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=["builtins.finish"],
        )
        agent = Agent(session=mock_session, config=config)
        stack = agent.stack

        # Add task definition so get_tools works
        task_definition = TaskDefinition.create_from_task(
            task=Task(
                name="test-task",
                description="Test task",
                parameters={},
                prompt="Test task",
                tools=["builtins.finish"],
                system_template="You are a helpful assistant.",
                llm_model="test-model",
            ),
            stack=stack,
        )
        stack.add_interaction(task_definition)

        # Create a ToolCall for finish
        tool_call = ToolCall(
            stack=stack,
            tool="builtins.finish",
            args={
                "finish_type": "success",
                "reason": "Test reason",
            },
            tool_call_id="call_123",
        )

        # Execute the tool call - this creates a ToolResult
        result = tool_call.step()
        assert result is True

        # Should have TaskDefinition + ToolResult
        assert len(stack.interactions) == 2
        tool_result = stack.interactions[1]
        assert isinstance(tool_result, ToolResult)
        assert tool_result.response_interaction == "TaskResult"

        # Step the ToolResult to create TaskResult
        result = tool_result.step()
        assert result is True

        # Now should have TaskDefinition + ToolResult + TaskResult
        assert len(stack.interactions) == 3
        task_result = stack.interactions[2]
        assert isinstance(task_result, TaskResult)
        assert task_result.finish_type == "success"

    def test_finish_tool_via_execute_tool(self, mock_session):
        """Test finish tool via Tool.execute_tool returns ToolResponse."""
        # Import to trigger registration
        from gimle.hugin.tools.builtins.finish import finish_tool  # noqa: F401

        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=mock_session, config=config)
        stack = agent.stack

        tool = Tool.get_tool("builtins.finish")
        result = Tool.execute_tool(
            tool,
            finish_type="success",
            reason="Test reason",
            stack=stack,
            branch=None,
        )
        # execute_tool returns ToolResponse from the tool function
        assert isinstance(result, ToolResponse)
        assert result.response_interaction == "TaskResult"
        assert result.content == {"finish_type": "success", "result": None}
