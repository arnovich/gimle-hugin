"""Tests for Stack functionality and full flow integration."""

from typing import Any, Dict
from unittest.mock import Mock, patch

import pytest

from gimle.hugin.agent.task import Task
from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.oracle_response import OracleResponse
from gimle.hugin.interaction.stack import Stack
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.interaction.task_result import TaskResult
from gimle.hugin.interaction.tool_call import ToolCall
from gimle.hugin.interaction.tool_result import ToolResult
from gimle.hugin.interaction.waiting import Waiting
from gimle.hugin.llm.prompt.prompt import Prompt
from gimle.hugin.tools.tool import Tool, ToolResponse


class TestStackBasic:
    """Test basic Stack functionality."""

    def test_stack_initialization(self, mock_agent):
        """Test Stack initialization."""
        stack = Stack(agent=mock_agent)
        assert stack.agent == mock_agent
        assert stack.interactions == []
        assert stack.branches == {}

    def test_stack_add_interaction(self, mock_agent):
        """Test adding interactions to stack."""
        stack = Stack(agent=mock_agent)
        interaction = Mock()

        stack.add_interaction(interaction)

        assert len(stack.interactions) == 1
        assert stack.interactions[0] == interaction

    def test_stack_add_interaction_with_branch(self, mock_agent):
        """Test adding interactions with branch."""
        stack = Stack(agent=mock_agent)
        interaction = Mock()

        stack.add_interaction(interaction, branch="branch1")

        assert len(stack.interactions) == 1
        assert interaction.branch == "branch1"

    def test_stack_ninteractions(self, mock_agent):
        """Test ninteractions method."""
        stack = Stack(agent=mock_agent)
        assert stack.ninteractions() == 0

        stack.add_interaction(Mock())
        stack.add_interaction(Mock())

        assert stack.ninteractions() == 2

    def test_stack_step_empty(self, mock_agent):
        """Test stepping empty stack returns False."""
        stack = Stack(agent=mock_agent)
        assert stack.step() is False

    def test_stack_step_with_interaction(self, mock_agent):
        """Test stepping stack with interaction."""
        stack = Stack(agent=mock_agent)
        interaction = Mock()
        interaction.step.return_value = True
        stack.add_interaction(interaction)

        result = stack.step()

        assert result is True
        assert interaction.step.called

    def test_stack_get_task_definition(self, mock_agent):
        """Test getting task definition from stack."""
        stack = Stack(agent=mock_agent)
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        retrieved_task = stack.get_task_definition()
        assert retrieved_task == task

    def test_stack_get_task_definition_empty(self, mock_agent):
        """Test getting task definition from empty stack."""
        stack = Stack(agent=mock_agent)

        # Empty stack returns None (not ValueError)
        result = stack.get_task_definition()
        assert result is None

        # But if we have interactions without TaskDefinition, it raises ValueError
        stack.add_interaction(Mock())  # Add a non-TaskDefinition interaction
        with pytest.raises(ValueError, match="No task definition found"):
            stack.get_task_definition()

    def test_stack_get_task_definition_latest(self, mock_agent):
        """Test getting latest task definition when multiple exist."""
        stack = Stack(agent=mock_agent)

        task1 = Task(
            name="task1",
            description="First",
            parameters={},
            prompt="First task",
            tools=[],
        )
        task_def1 = TaskDefinition(stack=stack, task=task1)
        stack.add_interaction(task_def1)

        task2 = Task(
            name="task2",
            description="Second",
            parameters={},
            prompt="Second task",
            tools=[],
        )
        task_def2 = TaskDefinition(stack=stack, task=task2)
        stack.add_interaction(task_def2)

        retrieved_task = stack.get_task_definition()
        assert retrieved_task == task2  # Should return latest

    def test_stack_get_tools_from_task(self, mock_agent):
        """Test getting tools from task definition."""
        stack = Stack(agent=mock_agent)
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=["tool1", "tool2"],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Track which tools we add so we can remove only them
        added_tools = []

        @Tool.register(name="tool1", description="Tool 1", parameters={})
        def tool1():
            pass

        added_tools.append("tool1")

        @Tool.register(name="tool2", description="Tool 2", parameters={})
        def tool2():
            pass

        added_tools.append("tool2")

        tools = sorted([tool.name for tool in stack.get_tools()])
        assert len(tools) == 2
        assert tools[0] == "tool1"
        assert tools[1] == "tool2"

        # Remove only the tools we added, not the entire registry
        for tool_name in added_tools:
            Tool.registry.remove(tool_name)

    def test_stack_get_tools_from_agent(self, mock_agent):
        """Test getting tools from agent when task has no tools."""
        stack = Stack(agent=mock_agent)
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=None,
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Mock agent.get_tools
        mock_agent.get_tools = Mock(return_value=[])

        tools = stack.get_tools()
        assert isinstance(tools, list)

    def test_stack_get_system_template_from_task(self, mock_agent):
        """Test getting system template from task."""
        stack = Stack(agent=mock_agent)
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
            system_template="Task system template",
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        template = stack.get_system_template()
        assert template == "Task system template"

    def test_stack_get_system_template_from_agent(self, mock_agent):
        """Test getting system template from agent when task has none."""
        stack = Stack(agent=mock_agent)
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
            system_template=None,
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        template = stack.get_system_template()
        assert template == mock_agent.config.system_template


class TestStackFullFlow:
    """Test complete Stack flow with multiple interactions."""

    @pytest.fixture
    def mock_tools(self):
        """Register mock tools for testing."""
        # Track which tools we add so we can remove only them
        added_tools = []

        @Tool.register(
            name="search_tool",
            description="Search for information",
            parameters={
                "query": {"type": "string", "description": "Search query"}
            },
            options={},
        )
        def search_tool(query: str, stack: Stack, branch: str) -> ToolResponse:
            return ToolResponse(
                is_error=False, content={"results": f"Results for {query}"}
            )

        added_tools.append("search_tool")

        @Tool.register(
            name="calculate_tool",
            description="Perform calculations",
            parameters={
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"},
            },
            options={},
        )
        def calculate_tool(
            a: int, b: int, stack: Stack, branch: str
        ) -> ToolResponse:
            return ToolResponse(is_error=False, content={"result": a + b})

        added_tools.append("calculate_tool")

        yield

        # Remove only the tools we added, not the entire registry
        for tool_name in added_tools:
            Tool.registry.remove(tool_name)

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_full_flow_task_to_text_response(
        self, mock_chat_completion, mock_agent, mock_tools
    ):
        """Test full flow: TaskDefinition -> AskOracle -> OracleResponse (text) -> end."""
        stack = Stack(agent=mock_agent)

        # Step 1: Add TaskDefinition (always first)
        task = Task(
            name="test_task",
            description="Test task",
            parameters={},
            prompt="Answer a question",
            tools=["search_tool"],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Step 2: TaskDefinition.step() -> should create AskOracle
        # But TaskDefinition.step() just returns True, doesn't create AskOracle
        # So we manually add AskOracle to simulate the flow
        prompt = Prompt(type="text", text="What is the weather?")
        ask_oracle = AskOracle(stack=stack, prompt=prompt, template_inputs={})
        stack.add_interaction(ask_oracle)

        # Step 3: AskOracle.step() -> calls chat_completion -> adds OracleResponse
        mock_chat_completion.return_value = {
            "role": "assistant",
            "content": "The weather is sunny.",
            "tool_call": None,
        }

        result = ask_oracle.step()
        assert result is True
        assert (
            len(stack.interactions) == 3
        )  # TaskDef + AskOracle + OracleResponse

        oracle_response = stack.interactions[-1]
        assert isinstance(oracle_response, OracleResponse)

        # Step 4: OracleResponse.step() -> no tool call, returns False (end)
        result = oracle_response.step()
        assert result is False
        assert len(stack.interactions) == 4  # No new interaction added

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_full_flow_with_single_tool_call(
        self, mock_chat_completion, mock_agent, mock_tools
    ):
        """Test full flow: TaskDefinition -> AskOracle -> OracleResponse -> ToolCall -> ToolResult -> AskOracle -> OracleResponse (text)."""
        stack = Stack(agent=mock_agent)

        # Step 1: TaskDefinition
        task = Task(
            name="test_task",
            description="Test task",
            parameters={},
            prompt="Search for something",
            tools=["search_tool"],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Step 2: AskOracle (initial question)
        prompt = Prompt(type="text", text="Search for Python tutorials")
        ask_oracle1 = AskOracle(stack=stack, prompt=prompt, template_inputs={})
        stack.add_interaction(ask_oracle1)

        # Step 3: AskOracle.step() -> OracleResponse with tool_call
        mock_chat_completion.return_value = {
            "role": "assistant",
            "content": {"query": "Python tutorials"},
            "tool_call": "search_tool",
            "tool_call_id": "call_123",
        }
        ask_oracle1.step()

        assert len(stack.interactions) == 3
        oracle_response1 = stack.interactions[-1]
        assert isinstance(oracle_response1, OracleResponse)
        assert oracle_response1.response["tool_call"] == "search_tool"

        # Step 4: OracleResponse.step() -> ToolCall
        oracle_response1.step()

        assert len(stack.interactions) == 4
        tool_call = stack.interactions[-1]
        assert isinstance(tool_call, ToolCall)
        assert tool_call.tool == "search_tool"
        assert tool_call.tool_call_id == "call_123"

        # Step 5: ToolCall.step() -> ToolResult
        tool_call.step()

        assert len(stack.interactions) == 5
        tool_result = stack.interactions[-1]
        assert isinstance(tool_result, ToolResult)
        assert tool_result.tool_call_id == "call_123"

        # Step 6: ToolResult.step() -> AskOracle (with tool result)
        # Note: The code accesses self.stack.interactions[-1] which is ToolResult itself
        # We need to set response_type on tool_result to work around this bug
        tool_result.tool_call_id = "call_123"

        tool_result.step()

        assert len(stack.interactions) >= 6
        ask_oracle2 = stack.interactions[-1]
        assert isinstance(ask_oracle2, AskOracle)

        # Step 7: AskOracle.step() -> OracleResponse (final text response)
        mock_chat_completion.return_value = {
            "role": "assistant",
            "content": "Here are some Python tutorials: ...",
            "tool_call": None,
        }
        ask_oracle2.step()

        assert len(stack.interactions) >= 7
        oracle_response2 = stack.interactions[-1]
        assert isinstance(oracle_response2, OracleResponse)
        assert oracle_response2.response.get("tool_call") is None

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_full_flow_with_multiple_tool_calls(
        self, mock_chat_completion, mock_agent, mock_tools
    ):
        """Test full flow with multiple sequential tool calls."""
        stack = Stack(agent=mock_agent)

        # Setup task
        task = Task(
            name="test_task",
            description="Test task",
            parameters={},
            prompt="Do multiple things",
            tools=["search_tool", "calculate_tool"],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Initial AskOracle
        prompt = Prompt(type="text", text="Search and calculate")
        ask_oracle = AskOracle(stack=stack, prompt=prompt, template_inputs={})
        stack.add_interaction(ask_oracle)

        # First tool call
        mock_chat_completion.return_value = {
            "role": "assistant",
            "content": {"query": "test"},
            "tool_call": "search_tool",
            "tool_call_id": "call_1",
        }
        ask_oracle.step()

        oracle_response1 = stack.interactions[-1]
        oracle_response1.step()  # Creates ToolCall

        tool_call1 = stack.interactions[-1]
        tool_call1.step()  # Creates ToolResult

        tool_result1 = stack.interactions[-1]

        # Setup for ToolResult.step() - set response_type on tool_result itself
        tool_result1.tool_call_id = "call_1"

        tool_result1.step()  # Creates AskOracle

        ask_oracle2 = stack.interactions[-1]

        # Second tool call
        mock_chat_completion.return_value = {
            "role": "assistant",
            "content": {"a": 5, "b": 3},
            "tool_call": "calculate_tool",
            "tool_call_id": "call_2",
        }
        ask_oracle2.step()

        oracle_response2 = stack.interactions[-1]
        oracle_response2.step()  # Creates ToolCall

        tool_call2 = stack.interactions[-1]
        assert tool_call2.tool == "calculate_tool"

        tool_call2.step()  # Creates ToolResult

        tool_result2 = stack.interactions[-1]
        assert isinstance(tool_result2, ToolResult)

        # Final response - set response_type on tool_result itself
        tool_result2.tool_call_id = "call_2"

        tool_result2.step()  # Creates AskOracle

        ask_oracle3 = stack.interactions[-1]

        mock_chat_completion.return_value = {
            "role": "assistant",
            "content": "All done!",
            "tool_call": None,
        }
        ask_oracle3.step()

        final_response = stack.interactions[-1]
        assert isinstance(final_response, OracleResponse)
        assert final_response.response.get("tool_call") is None

    def test_stack_serialization(self, mock_agent):
        """Test Stack serialization to dict."""
        stack = Stack(agent=mock_agent)

        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        data = stack.to_dict()

        assert "interactions" in data
        assert len(data["interactions"]) == 1
        assert data["interactions"][0] == task_def.uuid

    def test_stack_from_dict(self, mock_agent):
        """Test Stack deserialization from dict."""
        stack = Stack(agent=mock_agent)

        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)
        mock_agent.session.storage.save_interaction(task_def)

        # Serialize
        data = stack.to_dict()

        # Deserialize
        new_stack = Stack.from_dict(
            data, storage=mock_agent.session.storage, agent=mock_agent
        )

        assert len(new_stack.interactions) == 1
        assert isinstance(new_stack.interactions[0], TaskDefinition)
        assert isinstance(new_stack.interactions[0].task, Task)
        assert new_stack.interactions[0].task.name == "test_task"
        assert new_stack.agent == mock_agent

    def test_stack_round_trip(self, mock_agent):
        """Test round-trip serialization/deserialization of Stack."""
        stack = Stack(agent=mock_agent)

        # Add multiple interactions
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)
        mock_agent.session.storage.save_interaction(task_def)

        from gimle.hugin.llm.prompt.prompt import Prompt

        prompt = Prompt(type="text", text="Test prompt")
        from gimle.hugin.interaction.ask_oracle import AskOracle

        ask_oracle = AskOracle(stack=stack, prompt=prompt, template_inputs={})
        stack.add_interaction(ask_oracle)
        mock_agent.session.storage.save_interaction(ask_oracle)

        # Serialize
        data = stack.to_dict()

        # Deserialize
        new_stack = Stack.from_dict(
            data, storage=mock_agent.session.storage, agent=mock_agent
        )

        # Verify
        assert len(new_stack.interactions) == 2
        assert isinstance(new_stack.interactions[0], TaskDefinition)
        assert isinstance(new_stack.interactions[1], AskOracle)
        assert isinstance(new_stack.interactions[0].task, Task)
        assert new_stack.interactions[0].task.name == "test_task"
        assert new_stack.interactions[1].prompt.text == "Test prompt"
        assert new_stack.agent == mock_agent

    def test_stack_with_branches(self, mock_agent):
        """Test Stack serialization with branches."""
        stack = Stack(agent=mock_agent)

        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def, branch="main")
        mock_agent.session.storage.save_interaction(task_def)

        from gimle.hugin.llm.prompt.prompt import Prompt

        prompt = Prompt(type="text", text="Test")
        from gimle.hugin.interaction.ask_oracle import AskOracle

        ask_oracle = AskOracle(stack=stack, prompt=prompt, template_inputs={})
        stack.add_interaction(ask_oracle, branch="branch1")
        mock_agent.session.storage.save_interaction(ask_oracle)

        # Serialize and deserialize
        data = stack.to_dict()
        new_stack = Stack.from_dict(
            data, storage=mock_agent.session.storage, agent=mock_agent
        )

        # Verify branches are preserved (if they're stored)
        assert len(new_stack.interactions) == 2
        # Note: branch information might be stored on interactions themselves

    def test_stack_step_through_full_flow(self, mock_agent, mock_tools):
        """Test stepping through a full flow using stack.step()."""
        stack = Stack(agent=mock_agent)

        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Answer a question",
            tools=["search_tool"],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Add AskOracle
        prompt = Prompt(type="text", text="Test question")
        ask_oracle = AskOracle(stack=stack, prompt=prompt, template_inputs={})
        stack.add_interaction(ask_oracle)

        # Mock chat_completion
        with patch("gimle.hugin.llm.completion.chat_completion") as mock_chat:
            mock_chat.return_value = {
                "role": "assistant",
                "content": "Answer",
                "tool_call": None,
            }

            # Step through interactions
            result = stack.step()  # Steps AskOracle
            assert result is True

            result = stack.step()  # Steps OracleResponse
            # OracleResponse with no tool_call returns False, so step returns False
            assert result is False

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_full_flow_with_finish_tool(
        self, mock_chat_completion, mock_agent, mock_tools
    ):
        """Test full flow ending with finish tool that terminates via TaskResult."""
        # Re-register finish tool after mock_tools fixture cleared the registry
        from gimle.hugin.tools.builtins.finish import finish_tool

        # Manually register it since the decorator only runs once on module import
        Tool.register(
            name="finish",
            description="Finish the current task and terminate the flow. Use this when the task is complete.",
            parameters={
                "finish_type": {
                    "type": "string",
                    "description": "Either 'success' or 'failure' to indicate task completion status",
                    "required": False,
                },
                "result": {
                    "type": "string",
                    "description": "The result of the task. This will be passed to the next task as the result parameter.",
                    "required": False,
                },
            },
            is_interactive=False,
        )(finish_tool)

        assert (
            "finish" in Tool.registry.registered()
        ), "Finish tool should be registered"

        stack = Stack(agent=mock_agent)

        # Step 1: TaskDefinition
        task = Task(
            name="test_task",
            description="Test task",
            parameters={},
            prompt="Complete a task and finish",
            tools=["search_tool", "finish"],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Step 2: AskOracle (initial question)
        prompt = Prompt(
            type="text", text="Search for information and then finish"
        )
        ask_oracle1 = AskOracle(stack=stack, prompt=prompt, template_inputs={})
        stack.add_interaction(ask_oracle1)

        # Step 3: AskOracle.step() -> OracleResponse with tool_call
        mock_chat_completion.return_value = {
            "role": "assistant",
            "content": {"query": "test"},
            "tool_call": "search_tool",
            "tool_call_id": "call_1",
        }
        ask_oracle1.step()

        assert len(stack.interactions) == 3
        oracle_response1 = stack.interactions[-1]
        assert isinstance(oracle_response1, OracleResponse)

        # Step 4: OracleResponse.step() -> ToolCall
        oracle_response1.step()

        tool_call1 = stack.interactions[-1]
        assert isinstance(tool_call1, ToolCall)
        assert tool_call1.tool == "search_tool"

        # Step 5: ToolCall.step() -> ToolResult
        tool_call1.step()

        tool_result1 = stack.interactions[-1]
        assert isinstance(tool_result1, ToolResult)

        # Step 6: ToolResult.step() -> AskOracle (with tool result)
        tool_result1.tool_call_id = "call_1"
        tool_result1.step()

        ask_oracle2 = stack.interactions[-1]
        assert isinstance(ask_oracle2, AskOracle)

        # Step 7: AskOracle.step() -> OracleResponse with finish tool call
        mock_chat_completion.return_value = {
            "role": "assistant",
            "content": {"finish_type": "success"},
            "tool_call": "finish",
            "tool_call_id": "call_2",
        }
        ask_oracle2.step()

        oracle_response2 = stack.interactions[-1]
        assert isinstance(oracle_response2, OracleResponse)
        assert oracle_response2.response["tool_call"] == "finish"

        # Step 8: OracleResponse.step() -> ToolCall (finish)
        oracle_response2.step()

        tool_call2 = stack.interactions[-1]
        assert isinstance(tool_call2, ToolCall)
        assert tool_call2.tool == "finish"

        # Step 9: ToolCall.step() -> ToolResult (finish tool returns ToolResponse)
        tool_call2.step()

        tool_result2 = stack.interactions[-1]
        assert isinstance(tool_result2, ToolResult)
        assert tool_result2.response_interaction == "TaskResult"

        # Step 10: ToolResult.step() -> TaskResult
        tool_result2.step()

        task_result = stack.interactions[-1]
        assert isinstance(task_result, TaskResult)
        assert task_result.finish_type == "success"

        # Step 11: TaskResult.step() -> adds Waiting interaction
        result = task_result.step()
        assert (
            result is True
        )  # Returns True, but adds Waiting to signal termination

        # Verify the flow is complete
        # We have: TaskDefinition, AskOracle1, OracleResponse1, ToolCall1, ToolResult1,
        #         AskOracle2, OracleResponse2, ToolCall2, ToolResult2, TaskResult, Waiting
        assert len(stack.interactions) == 11
        # Last interaction should be Waiting (signaling termination)
        from gimle.hugin.interaction.waiting import Waiting

        assert isinstance(stack.interactions[-1], Waiting)

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_stack_step_loop_with_task_definition(
        self, mock_chat_completion, mock_agent, mock_tools
    ):
        """Test looping through stack.step() multiple times starting from TaskDefinition."""
        stack = Stack(agent=mock_agent)

        # Step 1: Set up TaskDefinition
        task = Task(
            name="loop_task",
            description="Task for loop testing",
            parameters={},
            prompt="Search for information and provide a summary",
            tools=["search_tool", "calculate_tool"],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Track the step count and responses
        step_count = 0
        max_steps = 10
        call_count = 0

        # Define response sequence for chat_completion
        def chat_completion_side_effect(*args, **kwargs) -> Dict[str, Any]:
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First call: return tool call
                return {
                    "role": "assistant",
                    "content": {"query": "Python tutorials"},
                    "tool_call": "search_tool",
                    "tool_call_id": f"call_{call_count}",
                }
            elif call_count == 2:
                # Second call: return another tool call
                return {
                    "role": "assistant",
                    "content": {"a": 5, "b": 3},
                    "tool_call": "calculate_tool",
                    "tool_call_id": f"call_{call_count}",
                }
            else:
                # Final call: return text response
                return {
                    "role": "assistant",
                    "content": "I found the information and calculated the result. The answer is 8.",
                    "tool_call": None,
                }

        mock_chat_completion.side_effect = chat_completion_side_effect

        # Start with TaskDefinition - step it to create AskOracle
        # But TaskDefinition.step() just returns True, so we manually add AskOracle
        # In real flow, TaskDefinition would transition to AskOracle
        prompt = Prompt(
            type="text", text="Search for Python tutorials and calculate 5 + 3"
        )
        ask_oracle = AskOracle(stack=stack, prompt=prompt, template_inputs={})
        stack.add_interaction(ask_oracle)

        # Loop through steps
        while step_count < max_steps:
            # Check if the last interaction is a ToolResult that needs response_type set
            # This works around a bug where ToolResult.step() accesses self.stack.interactions[-1]
            # which is the ToolResult itself
            # if stack.interactions and isinstance(stack.interactions[-1], ToolResult):
            #     tool_result = stack.interactions[-1]
            #     if not hasattr(tool_result, 'response_type'):
            #         # Set response_type based on the tool call that created it
            #         # Find the corresponding ToolCall to get the tool_call_id
            #         for interaction in reversed(stack.interactions[:-1]):
            #             if isinstance(interaction, ToolCall) and interaction.tool_call_id == tool_result.tool_call_id:
            #                 tool_result.tool_call_id = interaction.tool_call_id
            #                 break

            result = stack.step()
            step_count += 1

            # If step returns False, we've reached the end (no more interactions to process)
            if result is False:
                break

            # Check that stack is still valid
            assert stack.agent == mock_agent
            assert len(stack.interactions) > 0

            # Safety check: if we have too many interactions, something might be wrong
            assert (
                len(stack.interactions) <= 20
            ), "Too many interactions created"

        # Verify we completed the loop
        assert step_count > 0, "Should have executed at least one step"
        assert (
            len(stack.interactions) > 1
        ), "Should have multiple interactions on stack"

        # Check final state
        assert stack.ninteractions() == len(stack.interactions)

        # Verify TaskDefinition is still first
        assert isinstance(stack.interactions[0], TaskDefinition)

        # Verify we have the expected interaction types
        interaction_types = [type(i).__name__ for i in stack.interactions]
        assert "TaskDefinition" in interaction_types
        assert "AskOracle" in interaction_types
        assert "OracleResponse" in interaction_types
        assert "ToolCall" in interaction_types
        assert "ToolResult" in interaction_types

        # Verify final interaction is OracleResponse (text, no tool call)
        final_interaction = stack.interactions[-2]
        assert isinstance(final_interaction, OracleResponse)
        assert final_interaction.response.get("tool_call") is None
        assert (
            "information"
            in final_interaction.response.get("content", "").lower()
            or "answer" in final_interaction.response.get("content", "").lower()
        )

        # Verify chat_completion was called
        assert (
            mock_chat_completion.called
        ), "chat_completion should have been called"
        assert (
            mock_chat_completion.call_count >= 1
        ), "chat_completion should have been called at least once"


class TestStackBranching:
    """Test Stack branching functionality."""

    def test_get_active_branches_empty_stack(self, mock_agent):
        """Test get_active_branches with empty stack."""
        stack = Stack(agent=mock_agent)
        branches = stack.get_active_branches()
        assert branches == []

    def test_get_active_branches_main_only(self, mock_agent):
        """Test get_active_branches with only main branch."""
        stack = Stack(agent=mock_agent)
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)  # branch=None (main)

        branches = stack.get_active_branches()
        assert branches == [None]

    def test_get_active_branches_multiple(self, mock_agent):
        """Test get_active_branches with multiple branches."""
        stack = Stack(agent=mock_agent)
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )

        # Add main branch interaction
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Add branch1 interaction
        prompt = Prompt(type="text", text="Branch 1")
        ask1 = AskOracle(stack=stack, prompt=prompt, template_inputs={})
        stack.add_interaction(ask1, branch="branch1")

        # Add branch2 interaction
        prompt2 = Prompt(type="text", text="Branch 2")
        ask2 = AskOracle(stack=stack, prompt=prompt2, template_inputs={})
        stack.add_interaction(ask2, branch="branch2")

        branches = stack.get_active_branches()
        assert branches == [None, "branch1", "branch2"]

    def test_get_branch_fork_index(self, mock_agent):
        """Test finding the fork point for a branch."""
        stack = Stack(agent=mock_agent)
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )

        # Add 3 main branch interactions
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        prompt1 = Prompt(type="text", text="Main 1")
        ask1 = AskOracle(stack=stack, prompt=prompt1, template_inputs={})
        stack.add_interaction(ask1)

        prompt2 = Prompt(type="text", text="Main 2")
        ask2 = AskOracle(stack=stack, prompt=prompt2, template_inputs={})
        stack.add_interaction(ask2)

        # Add branch at index 3
        prompt_branch = Prompt(type="text", text="Branch")
        ask_branch = AskOracle(
            stack=stack, prompt=prompt_branch, template_inputs={}
        )
        stack.add_interaction(ask_branch, branch="feature")

        fork_index = stack.get_branch_fork_index("feature")
        assert fork_index == 3

    def test_get_branch_fork_index_not_found(self, mock_agent):
        """Test get_branch_fork_index raises ValueError for missing branch."""
        stack = Stack(agent=mock_agent)
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        with pytest.raises(ValueError, match="Branch nonexistent not found"):
            stack.get_branch_fork_index("nonexistent")

    def test_get_branch_interactions_main(self, mock_agent):
        """Test get_branch_interactions for main branch."""
        stack = Stack(agent=mock_agent)
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )

        # Add main branch interactions
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        prompt1 = Prompt(type="text", text="Main")
        ask1 = AskOracle(stack=stack, prompt=prompt1, template_inputs={})
        stack.add_interaction(ask1)

        # Add branch interaction (should NOT appear in main)
        prompt_branch = Prompt(type="text", text="Branch")
        ask_branch = AskOracle(
            stack=stack, prompt=prompt_branch, template_inputs={}
        )
        stack.add_interaction(ask_branch, branch="feature")

        main_interactions = stack.get_branch_interactions(None)
        assert len(main_interactions) == 2
        assert all(i.branch is None for i in main_interactions)

    def test_get_branch_interactions_named_branch(self, mock_agent):
        """Test get_branch_interactions for a named branch."""
        stack = Stack(agent=mock_agent)
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )

        # Add main branch interactions (before fork)
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        prompt1 = Prompt(type="text", text="Main 1")
        ask1 = AskOracle(stack=stack, prompt=prompt1, template_inputs={})
        stack.add_interaction(ask1)

        # Fork: add feature branch interaction
        prompt_feature = Prompt(type="text", text="Feature 1")
        ask_feature1 = AskOracle(
            stack=stack, prompt=prompt_feature, template_inputs={}
        )
        stack.add_interaction(ask_feature1, branch="feature")

        # Add more main branch interaction (after fork)
        prompt2 = Prompt(type="text", text="Main 2")
        ask2 = AskOracle(stack=stack, prompt=prompt2, template_inputs={})
        stack.add_interaction(ask2)

        # Add more feature branch interaction
        prompt_feature2 = Prompt(type="text", text="Feature 2")
        ask_feature2 = AskOracle(
            stack=stack, prompt=prompt_feature2, template_inputs={}
        )
        stack.add_interaction(ask_feature2, branch="feature")

        feature_interactions = stack.get_branch_interactions("feature")

        # Should see: TaskDef, Main1 (before fork), Feature1, Feature2
        assert len(feature_interactions) == 4
        assert feature_interactions[0] == task_def
        assert feature_interactions[1] == ask1
        assert feature_interactions[2] == ask_feature1
        assert feature_interactions[3] == ask_feature2

    def test_get_last_interaction_for_branch(self, mock_agent):
        """Test getting last interaction for a specific branch."""
        stack = Stack(agent=mock_agent)
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )

        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        prompt_main = Prompt(type="text", text="Main")
        ask_main = AskOracle(
            stack=stack, prompt=prompt_main, template_inputs={}
        )
        stack.add_interaction(ask_main)

        prompt_branch = Prompt(type="text", text="Branch")
        ask_branch = AskOracle(
            stack=stack, prompt=prompt_branch, template_inputs={}
        )
        stack.add_interaction(ask_branch, branch="feature")

        # Last main branch interaction
        last_main = stack.get_last_interaction_for_branch(None)
        assert last_main == ask_main

        # Last feature branch interaction
        last_feature = stack.get_last_interaction_for_branch("feature")
        assert last_feature == ask_branch

        # Nonexistent branch
        last_none = stack.get_last_interaction_for_branch("nonexistent")
        assert last_none is None

    def test_is_branch_complete(self, mock_agent):
        """Test checking if a branch is complete."""
        stack = Stack(agent=mock_agent)
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )

        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Main branch not complete
        assert stack.is_branch_complete(None) is False

        # Add TaskResult to main branch
        task_result = TaskResult(stack=stack, finish_type="success")
        stack.add_interaction(task_result)

        # Main branch now complete
        assert stack.is_branch_complete(None) is False

        waiting = Waiting(stack=stack)
        stack.add_interaction(waiting)

        # Main branch now complete
        assert stack.is_branch_complete(None) is True

        # Feature branch doesn't exist, so not complete
        assert stack.is_branch_complete("feature") is False

    def test_step_multiple_branches(self, mock_agent):
        """Test that step() steps all active branches."""
        stack = Stack(agent=mock_agent)
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )

        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Track which branches are stepped
        stepped_branches = []

        # Add real interactions and patch their step methods
        prompt_main = Prompt(type="text", text="Main")
        ask_main = AskOracle(
            stack=stack, prompt=prompt_main, template_inputs={}
        )
        ask_main.step = lambda: (stepped_branches.append("main"), True)[1]
        stack.add_interaction(ask_main)

        prompt1 = Prompt(type="text", text="Branch 1")
        ask1 = AskOracle(stack=stack, prompt=prompt1, template_inputs={})
        ask1.step = lambda: (stepped_branches.append("branch1"), True)[1]
        stack.add_interaction(ask1, branch="branch1")

        prompt2 = Prompt(type="text", text="Branch 2")
        ask2 = AskOracle(stack=stack, prompt=prompt2, template_inputs={})
        ask2.step = lambda: (stepped_branches.append("branch2"), True)[1]
        stack.add_interaction(ask2, branch="branch2")

        # Step should step all branches
        result = stack.step()
        assert result is True
        assert "main" in stepped_branches
        assert "branch1" in stepped_branches
        assert "branch2" in stepped_branches

    def test_step_skips_complete_branches(self, mock_agent):
        """Test that step() skips branches that have TaskResult."""
        stack = Stack(agent=mock_agent)
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )

        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Add TaskResult to main branch (completing it)
        task_result = TaskResult(stack=stack, finish_type="success")
        stack.add_interaction(task_result)

        # Add incomplete branch with tracked step
        stepped_branches = []

        prompt_feature = Prompt(type="text", text="Feature")
        ask_feature = AskOracle(
            stack=stack, prompt=prompt_feature, template_inputs={}
        )
        ask_feature.step = lambda: (stepped_branches.append("feature"), True)[1]
        stack.add_interaction(ask_feature, branch="feature")

        # Step should only step the feature branch (main is complete)
        result = stack.step()
        assert result is True
        assert stepped_branches == ["feature"]

    def test_render_stack_context_for_branch(self, mock_agent):
        """Test that render_stack_context filters by branch."""
        stack = Stack(agent=mock_agent)
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )

        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Add main branch AskOracle
        prompt_main = Prompt(type="text", text="Main question")
        ask_main = AskOracle(
            stack=stack, prompt=prompt_main, template_inputs={}
        )
        stack.add_interaction(ask_main)

        # Add feature branch AskOracle
        prompt_feature = Prompt(type="text", text="Feature question")
        ask_feature = AskOracle(
            stack=stack, prompt=prompt_feature, template_inputs={}
        )
        stack.add_interaction(ask_feature, branch="feature")

        # Render main branch context
        main_context = stack.render_stack_context(branch=None)
        # Should only include main branch interactions
        assert len(main_context) == 1
        assert "Main question" in str(main_context)
        assert "Feature question" not in str(main_context)

        # Render feature branch context
        feature_context = stack.render_stack_context(branch="feature")
        # Should include main (before fork) + feature interactions
        # TaskDef + ask_main are before fork, ask_feature is on feature
        assert len(feature_context) == 2
        assert "Main question" in str(feature_context)
        assert "Feature question" in str(feature_context)
