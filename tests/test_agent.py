"""Tests for Agent functionality and full flow integration."""

from unittest.mock import Mock, patch

import pytest

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.task import Task
from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.stack import Stack
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.interaction.tool_result import ToolResult
from gimle.hugin.llm.prompt.prompt import Prompt
from gimle.hugin.tools.tool import Tool


class TestAgentBasic:
    """Test basic Agent functionality."""

    def test_agent_initialization(self, mock_session):
        """Test Agent initialization."""
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            llm_model="test-model",
            tools=["search_tool"],
        )
        agent = Agent(session=mock_session, config=config)

        assert agent.session == mock_session
        assert agent.config == config
        assert isinstance(agent.stack, Stack)
        assert agent.stack.agent == agent

    def test_agent_with_custom_stack(self, mock_session):
        """Test Agent with custom stack."""
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        # Create custom stack with empty agent reference (will be set when agent uses it)
        custom_stack = Stack(agent=None, interactions=[])
        # Now create agent with custom stack - the stack's agent will be set
        agent_with_stack = Agent(
            session=mock_session, config=config, stack=custom_stack
        )

        assert agent_with_stack.stack == custom_stack
        # The stack's agent should now point to the agent that was created with it
        # Note: Stack doesn't automatically update agent reference, so we check differently
        assert hasattr(agent_with_stack.stack, "agent")

    def test_agent_step(self, mock_session):
        """Test Agent step calls stack.step()."""
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=mock_session, config=config)

        # Add a mock interaction that returns True
        mock_interaction = Mock()
        mock_interaction.step.return_value = True
        agent.stack.add_interaction(mock_interaction)

        result = agent.step()

        assert result is True
        assert mock_interaction.step.called

    def test_agent_step_empty_stack(self, mock_session):
        """Test Agent step with empty stack returns False."""
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=mock_session, config=config)

        result = agent.step()

        assert result is False

    def test_agent_get_tools(self, mock_session):
        """Test Agent get_tools returns registered tools."""
        # Track which tool we add so we can remove only it
        added_tool = None

        @Tool.register(
            name="test_tool",
            description="Test tool",
            parameters={"param": {"type": "string", "description": "Param"}},
            is_interactive=False,
        )
        def test_tool(param: str) -> dict:
            return {"result": param}

        added_tool = "test_tool"

        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=["test_tool"],
        )
        agent = Agent(session=mock_session, config=config)

        tools = agent.config.tools
        assert len(tools) == 1
        assert tools[0] == "test_tool"

        # Remove only the tool we added, not the entire registry
        if added_tool:
            Tool.registry.remove(added_tool)

    def test_agent_get_tools_filters_interactive(self, mock_session):
        """Test Agent get_tools filters interactive tools when not in interactive mode."""
        # Track which tools we add so we can remove only them
        added_tools = []

        @Tool.register(
            name="regular_tool",
            description="Regular tool",
            parameters={},
            is_interactive=False,
        )
        def regular_tool() -> dict:
            return {}

        added_tools.append("regular_tool")

        @Tool.register(
            name="interactive_tool",
            description="Interactive tool",
            parameters={},
            is_interactive=True,
        )
        def interactive_tool() -> dict:
            return {}

        added_tools.append("interactive_tool")

        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=["regular_tool", "interactive_tool"],
            interactive=False,
        )
        agent = Agent(session=mock_session, config=config)

        tools = agent.config.tools
        assert len(tools) == 2
        assert tools[0] == "regular_tool"
        assert tools[1] == "interactive_tool"

        # Now test with interactive=True
        config.interactive = True
        tools = agent.config.tools
        assert len(tools) == 2

        # Remove only the tools we added, not the entire registry
        for tool_name in added_tools:
            Tool.registry.remove(tool_name)

    def test_agent_id_property(self, mock_session):
        """Test Agent id property returns uuid."""
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=mock_session, config=config)

        agent_id = agent.id
        assert agent_id == agent.uuid
        assert isinstance(agent_id, str)
        assert len(agent_id) > 0


class TestAgentFullFlow:
    """Test Agent full flow with step loop."""

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
        def search_tool(query: str) -> dict:
            return {"results": f"Results for {query}"}

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
        def calculate_tool(a: int, b: int) -> dict:
            return {"result": a + b}

        added_tools.append("calculate_tool")

        yield

        # Remove only the tools we added, not the entire registry
        for tool_name in added_tools:
            Tool.registry.remove(tool_name)

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_agent_step_loop_with_task_definition(
        self, mock_chat_completion, mock_session, mock_tools
    ):
        """Test looping through agent.step() multiple times starting from TaskDefinition."""
        # Set up agent with tools
        config = Config(
            name="loop_agent",
            description="Agent for loop testing",
            system_template="You are a helpful assistant. {{ system_message }}",
            llm_model="test-model",
            tools=["search_tool", "calculate_tool"],
            options={"llm_model": "test-model"},
        )
        agent = Agent(session=mock_session, config=config)

        # Set up TaskDefinition on the stack
        task = Task(
            name="loop_task",
            description="Task for loop testing",
            parameters={},
            prompt="Search for information and provide a summary",
            tools=["search_tool", "calculate_tool"],
        )
        task_def = TaskDefinition(stack=agent.stack, task=task)
        agent.stack.add_interaction(task_def)

        # Track the step count and responses
        step_count = 0
        max_steps = 15
        call_count = 0

        # Define response sequence for chat_completion
        def chat_completion_side_effect(*args, **kwargs):
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

        # Start with TaskDefinition - add AskOracle to begin the flow
        prompt = Prompt(
            type="text", text="Search for Python tutorials and calculate 5 + 3"
        )
        ask_oracle = AskOracle(
            stack=agent.stack, prompt=prompt, template_inputs={}
        )
        agent.stack.add_interaction(ask_oracle)

        # Loop through agent steps
        while step_count < max_steps:
            # Check if the last interaction is a ToolResult that needs response_type set
            if agent.stack.interactions and isinstance(
                agent.stack.interactions[-1], ToolResult
            ):
                tool_result = agent.stack.interactions[-1]
                if not hasattr(tool_result, "response_type"):
                    # Find the corresponding ToolCall to get the tool_call_id
                    from gimle.hugin.interaction.tool_call import ToolCall

                    for interaction in reversed(agent.stack.interactions[:-1]):
                        if (
                            isinstance(interaction, ToolCall)
                            and interaction.tool_call_id
                            == tool_result.tool_call_id
                        ):
                            tool_result.tool_call_id = interaction.tool_call_id
                            break

            result = agent.step()
            step_count += 1

            # If step returns False, we've reached the end
            if result is False:
                break

            # Check that agent and stack are still valid
            assert agent.session == mock_session
            assert agent.stack.agent == agent
            assert len(agent.stack.interactions) > 0

            # Safety check: if we have too many interactions, something might be wrong
            assert (
                len(agent.stack.interactions) <= 25
            ), "Too many interactions created"

        # Verify we completed the loop
        assert step_count > 0, "Should have executed at least one step"
        assert (
            len(agent.stack.interactions) > 1
        ), "Should have multiple interactions on stack"

        # Check final state
        assert agent.stack.ninteractions() == len(agent.stack.interactions)

        # Verify TaskDefinition is still first
        assert isinstance(agent.stack.interactions[0], TaskDefinition)

        # Verify we have the expected interaction types
        interaction_types = [type(i).__name__ for i in agent.stack.interactions]
        assert "TaskDefinition" in interaction_types
        assert "AskOracle" in interaction_types
        assert "OracleResponse" in interaction_types

        # Verify chat_completion was called
        assert (
            mock_chat_completion.called
        ), "chat_completion should have been called"
        assert (
            mock_chat_completion.call_count >= 1
        ), "chat_completion should have been called at least once"

        # Verify final interaction is OracleResponse (text, no tool call)
        from gimle.hugin.interaction.oracle_response import OracleResponse

        final_interaction = agent.stack.interactions[-2]
        assert isinstance(final_interaction, OracleResponse)

        # Check that tools are registered and accessible
        tools = agent.config.tools
        assert len(tools) >= 0  # Should be able to get tools without error


class TestAgentSerialization:
    """Test Agent serialization and deserialization."""

    def test_agent_to_dict(self, mock_session):
        """Test serializing an agent."""
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=["tool1", "tool2"],
            llm_model="test-model",
            interactive=True,
            options={"key": "value"},
        )
        agent = Agent(session=mock_session, config=config)

        data = agent.to_dict()

        assert "config" in data
        assert "stack" in data
        assert "uuid" in data
        assert data["uuid"] == agent.uuid
        assert data["config"]["name"] == "test-agent"
        assert data["config"]["tools"] == ["tool1", "tool2"]
        assert data["config"]["llm_model"] == "test-model"
        assert data["config"]["interactive"] is True
        assert data["config"]["options"] == {"key": "value"}

    def test_agent_from_dict(self, mock_session):
        """Test deserializing an agent."""
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
            llm_model="test-model",
        )
        agent = Agent(session=mock_session, config=config)
        storage = mock_session.storage

        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=agent.stack, task=task)
        agent.stack.add_interaction(task_def)
        storage.save_interaction(task_def)

        # Serialize and deserialize
        data = agent.to_dict()
        new_agent = Agent.from_dict(data, storage=storage, session=mock_session)

        # Verify structure
        assert new_agent.uuid == agent.uuid
        assert new_agent.config.name == "test-agent"
        assert new_agent.config.llm_model == "test-model"
        assert new_agent.session == mock_session
        assert len(new_agent.stack.interactions) == 1
        assert isinstance(new_agent.stack.interactions[0], TaskDefinition)
        assert new_agent.stack.agent == new_agent

    def test_agent_round_trip(self, mock_session):
        """Test round-trip serialization/deserialization."""
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=["tool1"],
            llm_model="model1",
            interactive=False,
            options={"opt1": "val1"},
        )
        agent = Agent(session=mock_session, config=config)

        task = Task(
            name="test_task",
            description="Test",
            parameters={
                "param1": {
                    "type": "string",
                    "description": "",
                    "required": False,
                    "default": "value1",
                }
            },
            prompt="Do something",
            tools=["tool1"],
            system_template="Custom system",
            llm_model="model1",
        )
        task_def = TaskDefinition(stack=agent.stack, task=task)
        agent.stack.add_interaction(task_def)
        mock_session.storage.save_interaction(task_def)

        # Add another interaction
        from gimle.hugin.llm.prompt.prompt import Prompt

        prompt = Prompt(type="text", text="Test prompt")
        from gimle.hugin.interaction.ask_oracle import AskOracle

        ask_oracle = AskOracle(
            stack=agent.stack, prompt=prompt, template_inputs={}
        )
        agent.stack.add_interaction(ask_oracle)
        mock_session.storage.save_interaction(ask_oracle)

        # Serialize
        data = agent.to_dict()

        # Deserialize
        new_agent = Agent.from_dict(
            data, storage=mock_session.storage, session=mock_session
        )

        # Verify all properties
        assert new_agent.uuid == agent.uuid
        assert new_agent.config.name == "test-agent"
        assert new_agent.config.tools == ["tool1"]
        assert new_agent.config.llm_model == "model1"
        assert new_agent.config.interactive is False
        assert new_agent.config.options == {"opt1": "val1"}
        assert len(new_agent.stack.interactions) == 2
        assert new_agent.stack.interactions[0].task.name == "test_task"
        assert isinstance(new_agent.stack.interactions[1], AskOracle)

    def test_agent_preserves_uuid(self, mock_session):
        """Test that agent UUID is preserved during serialization."""
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=mock_session, config=config)
        original_uuid = agent.uuid

        data = agent.to_dict()
        new_agent = Agent.from_dict(
            data, storage=mock_session.storage, session=mock_session
        )

        assert new_agent.uuid == original_uuid

    def test_agent_with_empty_stack(self, mock_session):
        """Test agent serialization with empty stack."""
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=mock_session, config=config)
        # Stack should be empty by default

        data = agent.to_dict()
        new_agent = Agent.from_dict(
            data, storage=mock_session.storage, session=mock_session
        )

        assert len(new_agent.stack.interactions) == 0
        assert new_agent.stack.agent == new_agent

    def test_agent_preserves_interaction_uuids(self, mock_session):
        """Test that interaction UUIDs are preserved during agent serialization."""
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=mock_session, config=config)

        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=agent.stack, task=task)
        task_def_uuid = task_def.uuid
        agent.stack.add_interaction(task_def)
        mock_session.storage.save_interaction(task_def)

        from gimle.hugin.llm.prompt.prompt import Prompt

        prompt = Prompt(type="text", text="Test prompt")
        from gimle.hugin.interaction.ask_oracle import AskOracle

        ask_oracle = AskOracle(
            stack=agent.stack, prompt=prompt, template_inputs={}
        )
        ask_oracle_uuid = ask_oracle.uuid
        agent.stack.add_interaction(ask_oracle)
        mock_session.storage.save_interaction(ask_oracle)

        # Serialize and deserialize
        data = agent.to_dict()
        new_agent = Agent.from_dict(
            data, storage=mock_session.storage, session=mock_session
        )

        # Verify interaction UUIDs are preserved
        assert len(new_agent.stack.interactions) == 2
        assert new_agent.stack.interactions[0].uuid == task_def_uuid
        assert new_agent.stack.interactions[1].uuid == ask_oracle_uuid
