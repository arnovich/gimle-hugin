"""Tests for Session functionality and full flow integration."""

from typing import TYPE_CHECKING, Optional
from unittest.mock import Mock, patch

import pytest

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.artifacts.text import Text
from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.interaction.tool_result import ToolResult
from gimle.hugin.llm.prompt.prompt import Prompt
from gimle.hugin.storage.storage import Storage
from gimle.hugin.tools.tool import Tool


class MemoryStorage(Storage):
    """A memory-based storage implementation for testing."""

    def __init__(self) -> None:
        """Initialize the memory storage."""
        super().__init__()
        self._artifacts: dict[str, dict] = {}
        self._sessions: dict[str, dict] = {}
        self._agents: dict[str, dict] = {}
        self._interactions: dict[str, dict] = {}
        self._files: dict[str, bytes] = {}

    def list_sessions(self) -> list[str]:
        """List all sessions in the storage."""
        return list(self._sessions.keys())

    def list_agents(self) -> list[str]:
        """List all agents in the storage."""
        return list(self._agents.keys())

    def list_interactions(self) -> list[str]:
        """List all interactions in the storage."""
        return list(self._interactions.keys())

    def list_artifacts(self) -> list[str]:
        """List all artifacts in the storage."""
        return list(self._artifacts.keys())

    def _load_artifact(
        self,
        uuid: str,
        stack: Optional["Stack"] = None,
        load_interaction: bool = True,
    ) -> Artifact:
        """Load an artifact from memory."""
        if uuid not in self._artifacts:
            raise ValueError(f"Artifact {uuid} not found in storage")
        return Artifact.from_dict(
            self._artifacts[uuid],
            storage=self,
            stack=stack,
            load_interaction=load_interaction,
        )

    def _save_artifact(self, artifact: Artifact) -> None:
        """Save an artifact to memory."""
        self._artifacts[artifact.uuid] = artifact.to_dict()

    def _load_session(self, uuid: str, environment: "Environment") -> Session:
        """Load a session from memory."""
        if uuid not in self._sessions:
            raise ValueError(f"Session {uuid} not found in storage")
        return Session.from_dict(self._sessions[uuid], environment=environment)

    def _save_session(self, session: Session) -> None:
        """Save a session to memory."""
        self._sessions[session.uuid] = session.to_dict()

    def _load_agent(self, uuid: str, session: "Session") -> Agent:
        """Load an agent from memory."""
        if uuid not in self._agents:
            raise ValueError(f"Agent {uuid} not found in storage")
        return Agent.from_dict(
            self._agents[uuid], storage=self, session=session
        )

    def _save_agent(self, agent: Agent) -> None:
        """Save an agent to memory."""
        self._agents[agent.uuid] = agent.to_dict()

    def _load_interaction(self, uuid: str, stack: "Stack") -> Interaction:
        """Load an interaction from memory."""
        if uuid not in self._interactions:
            raise ValueError(f"Interaction {uuid} not found in storage")
        return Interaction.from_dict(self._interactions[uuid], stack=stack)

    def _save_interaction(self, interaction: Interaction) -> None:
        """Save an interaction to memory."""
        self._interactions[interaction.uuid] = interaction.to_dict()

    def _delete_artifact(self, artifact: Artifact) -> None:
        """Delete an artifact from memory."""
        if artifact.uuid in self._artifacts:
            del self._artifacts[artifact.uuid]

    def _delete_session(self, session: Session) -> None:
        """Delete a session from memory."""
        if session.uuid in self._sessions:
            del self._sessions[session.uuid]

    def _delete_agent(self, agent: Agent) -> None:
        """Delete an agent from memory."""
        if agent.uuid in self._agents:
            del self._agents[agent.uuid]

    def _delete_interaction(self, interaction: Interaction) -> None:
        """Delete an interaction from memory."""
        if interaction.uuid in self._interactions:
            del self._interactions[interaction.uuid]

    def save_file(
        self, artifact_uuid: str, content: bytes, extension: str
    ) -> str:
        """Save file content to memory."""
        filename = artifact_uuid
        if extension:
            filename = f"{artifact_uuid}.{extension}"
        file_path = f"files/{filename}"
        self._files[file_path] = content
        return file_path

    def load_file(self, file_path: str) -> bytes:
        """Load file content from memory."""
        if file_path not in self._files:
            raise FileNotFoundError(f"File not found: {file_path}")
        return self._files[file_path]


class TestSessionBasic:
    """Test basic Session functionality."""

    def test_session_initialization(self):
        """Test Session initialization."""
        environment = Environment()
        session = Session(environment=environment)

        assert session.agents == []
        assert hasattr(session, "uuid")
        assert session.environment == environment

    def test_session_add_agent(self):
        """Test adding an agent to session."""
        environment = Environment()
        session = Session(environment=environment)
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=session, config=config)

        session.add_agent(agent)

        assert len(session.agents) == 1
        assert session.agents[0] == agent
        assert agent.session == session

    def test_session_get_agent(self):
        """Test getting an agent from session by uuid."""
        environment = Environment()
        session = Session(environment=environment)
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=session, config=config)
        session.add_agent(agent)

        retrieved_agent = session.get_agent(agent.uuid)

        assert retrieved_agent == agent

    def test_session_get_agent_not_found(self):
        """Test getting a non-existent agent returns None."""
        environment = Environment()
        session = Session(environment=environment)

        result = session.get_agent("nonexistent-uuid")

        assert result is None

    def test_session_step_single_agent(self):
        """Test session step with single agent."""
        environment = Environment()
        session = Session(environment=environment)
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=session, config=config)

        # Add a mock interaction that returns True
        mock_interaction = Mock()
        mock_interaction.step.return_value = True
        agent.stack.add_interaction(mock_interaction)

        session.add_agent(agent)

        result = session.step()

        assert result is True
        assert mock_interaction.step.called

    def test_session_step_multiple_agents(self):
        """Test session step with multiple agents."""
        environment = Environment()
        session = Session(environment=environment)

        config1 = Config(
            name="agent1",
            description="First agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent1 = Agent(session=session, config=config1)
        mock_interaction1 = Mock()
        mock_interaction1.step.return_value = False
        agent1.stack.add_interaction(mock_interaction1)
        session.add_agent(agent1)

        config2 = Config(
            name="agent2",
            description="Second agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent2 = Agent(session=session, config=config2)
        mock_interaction2 = Mock()
        mock_interaction2.step.return_value = True
        agent2.stack.add_interaction(mock_interaction2)
        session.add_agent(agent2)

        result = session.step()

        # Should return True if any agent returns True
        assert result is True
        assert mock_interaction1.step.called
        assert mock_interaction2.step.called

    def test_session_step_no_agents(self):
        """Test session step with no agents returns False."""
        environment = Environment()
        session = Session(environment=environment)

        result = session.step()

        assert result is False

    def test_session_step_all_agents_return_false(self):
        """Test session step when all agents return False."""
        environment = Environment()
        session = Session(environment=environment)

        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=session, config=config)
        # Empty stack will return False
        session.add_agent(agent)

        result = session.step()

        assert result is False


class TestSessionFullFlow:
    """Test Session full flow with step loop."""

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
    def test_session_step_loop_with_agent(
        self, mock_chat_completion, mock_tools
    ):
        """Test looping through session.step() multiple times with an agent."""
        # Create session
        environment = Environment()
        session = Session(environment=environment)

        # Set up agent with tools
        config = Config(
            name="loop_agent",
            description="Agent for loop testing",
            system_template="You are a helpful assistant. {{ system_message }}",
            llm_model="test-model",
            tools=["search_tool", "calculate_tool"],
            options={"llm_model": "test-model"},
        )
        agent = Agent(session=session, config=config)

        # Set up TaskDefinition on the agent's stack
        task = Task(
            name="loop_task",
            description="Task for loop testing",
            parameters={},
            prompt="Search for information and provide a summary",
            tools=["search_tool", "calculate_tool"],
        )
        task_def = TaskDefinition(stack=agent.stack, task=task)
        agent.stack.add_interaction(task_def)

        # Add agent to session
        session.add_agent(agent)

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

        # Loop through session steps
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

            result = session.step()
            step_count += 1

            # If step returns False, we've reached the end
            if result is False:
                break

            # Check that session and agents are still valid
            assert len(session.agents) == 1
            assert session.agents[0] == agent
            assert agent.session == session
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

        # Verify agent is still in session
        retrieved_agent = session.get_agent(agent.uuid)
        assert retrieved_agent == agent

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_session_step_loop_multiple_agents(
        self, mock_chat_completion, mock_tools
    ):
        """Test looping through session.step() with multiple agents."""
        # Create session
        environment = Environment()
        session = Session(environment=environment)

        # Create first agent
        config1 = Config(
            name="agent1",
            description="First agent",
            system_template="You are a helpful assistant.",
            llm_model="test-model",
            tools=["search_tool"],
            options={"llm_model": "test-model"},
        )
        agent1 = Agent(session=session, config=config1)

        task1 = Task(
            name="task1",
            description="First task",
            parameters={},
            prompt="Search for information",
            tools=["search_tool"],
        )
        task_def1 = TaskDefinition(stack=agent1.stack, task=task1)
        agent1.stack.add_interaction(task_def1)
        session.add_agent(agent1)

        # Create second agent
        config2 = Config(
            name="agent2",
            description="Second agent",
            system_template="You are a helpful assistant.",
            llm_model="test-model",
            tools=["calculate_tool"],
            options={"llm_model": "test-model"},
        )
        agent2 = Agent(session=session, config=config2)

        task2 = Task(
            name="task2",
            description="Second task",
            parameters={},
            prompt="Calculate something",
            tools=["calculate_tool"],
        )
        task_def2 = TaskDefinition(stack=agent2.stack, task=task2)
        agent2.stack.add_interaction(task_def2)
        session.add_agent(agent2)

        # Mock chat_completion to return simple responses
        mock_chat_completion.return_value = {
            "role": "assistant",
            "content": "Completed the task.",
            "tool_call": None,
        }

        # Add AskOracle to both agents
        prompt1 = Prompt(type="text", text="Search")
        ask_oracle1 = AskOracle(
            stack=agent1.stack, prompt=prompt1, template_inputs={}
        )
        agent1.stack.add_interaction(ask_oracle1)

        prompt2 = Prompt(type="text", text="Calculate")
        ask_oracle2 = AskOracle(
            stack=agent2.stack, prompt=prompt2, template_inputs={}
        )
        agent2.stack.add_interaction(ask_oracle2)

        # Step through session multiple times
        step_count = 0
        max_steps = 10

        while step_count < max_steps:
            result = session.step()
            step_count += 1

            if result is False:
                break

            # Verify both agents are still in session
            assert len(session.agents) == 2
            assert agent1 in session.agents
            assert agent2 in session.agents

        # Verify both agents have interactions
        assert len(agent1.stack.interactions) > 0
        assert len(agent2.stack.interactions) > 0


class TestSessionSerialization:
    """Test Session serialization and deserialization."""

    def test_session_to_dict_empty(self):
        """Test serializing an empty session."""
        environment = Environment()
        session = Session(environment=environment)
        data = session.to_dict()

        assert "agents" in data
        assert "uuid" in data
        assert data["agents"] == []
        # assert data["artifacts"]["artifacts"] == []
        assert data["uuid"] == session.uuid

    def test_session_to_dict_with_agents(self):
        """Test serializing a session with agents."""
        environment = Environment()
        session = Session(environment=environment)
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=["tool1"],
            llm_model="test-model",
            interactive=False,
            options={"key": "value"},
        )
        agent = Agent(session=session, config=config)
        session.add_agent(agent)

        data = session.to_dict()

        assert len(data["agents"]) == 1
        assert data["agents"][0] == agent.uuid

    def test_session_from_dict_empty(self):
        """Test deserializing an empty session."""
        storage = MemoryStorage()
        data = {
            "artifacts": {"artifacts": []},
            "agents": [],
            "uuid": "test-uuid-123",
        }

        environment = Environment(storage=storage)
        session = Session.from_dict(data, environment=environment)

        assert session.uuid == "test-uuid-123"
        assert len(session.agents) == 0

    def test_session_from_dict_with_agents(self):
        """Test deserializing a session with agents."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
            llm_model="test-model",
        )
        agent = Agent(session=session, config=config)

        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=agent.stack, task=task)
        agent.stack.add_interaction(task_def)
        session.add_agent(agent)

        # Save all entities to storage before serializing
        storage.save_interaction(task_def)
        storage.save_agent(agent)
        storage.save_session(session)

        # Serialize and deserialize
        data = session.to_dict()
        new_environment = Environment(storage=storage)
        new_session = Session.from_dict(data, environment=new_environment)

        # Verify structure
        assert len(new_session.agents) == 1
        assert new_session.agents[0].uuid == agent.uuid
        assert new_session.agents[0].config.name == "test-agent"
        assert new_session.agents[0].session.uuid == new_session.uuid
        assert len(new_session.agents[0].stack.interactions) == 1
        assert isinstance(
            new_session.agents[0].stack.interactions[0], TaskDefinition
        )

    def test_session_round_trip(self):
        """Test round-trip serialization/deserialization."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create first agent
        config1 = Config(
            name="agent1",
            description="First agent",
            system_template="You are agent 1.",
            tools=["tool1"],
            llm_model="model1",
        )
        agent1 = Agent(session=session, config=config1)
        task1 = Task(
            name="task1",
            description="Task 1",
            parameters={},
            prompt="Do task 1",
            tools=[],
        )
        task_def1 = TaskDefinition(stack=agent1.stack, task=task1)
        agent1.stack.add_interaction(task_def1)
        session.add_agent(agent1)

        # Create second agent
        config2 = Config(
            name="agent2",
            description="Second agent",
            system_template="You are agent 2.",
            tools=["tool2"],
            llm_model="model2",
        )
        agent2 = Agent(session=session, config=config2)
        task2 = Task(
            name="task2",
            description="Task 2",
            parameters={},
            prompt="Do task 2",
            tools=[],
        )
        task_def2 = TaskDefinition(stack=agent2.stack, task=task2)
        agent2.stack.add_interaction(task_def2)
        session.add_agent(agent2)

        # Save all entities to storage
        storage.save_interaction(task_def1)
        storage.save_interaction(task_def2)
        storage.save_agent(agent1)
        storage.save_agent(agent2)
        storage.save_session(session)

        # Serialize
        data = session.to_dict()

        # Deserialize
        new_environment = Environment(storage=storage)
        new_session = Session.from_dict(data, environment=new_environment)

        # Verify all properties
        assert new_session.uuid == session.uuid
        assert len(new_session.agents) == 2

        # Verify first agent
        agent1_new = new_session.get_agent(agent1.uuid)
        assert agent1_new is not None
        assert agent1_new.config.name == "agent1"
        assert agent1_new.config.llm_model == "model1"
        assert len(agent1_new.stack.interactions) == 1
        assert agent1_new.stack.interactions[0].task.name == "task1"

        # Verify second agent
        agent2_new = new_session.get_agent(agent2.uuid)
        assert agent2_new is not None
        assert agent2_new.config.name == "agent2"
        assert agent2_new.config.llm_model == "model2"
        assert len(agent2_new.stack.interactions) == 1
        assert agent2_new.stack.interactions[0].task.name == "task2"

    def test_session_with_artifacts(self):
        """Test session serialization with artifacts."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=session, config=config)

        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=agent.stack, task=task)
        agent.stack.add_interaction(task_def)
        session.add_agent(agent)
        storage.save_agent(agent)

        # Create an artifact
        artifact = Artifact(interaction=task_def)
        storage.save_interaction(task_def)
        storage.save_artifact(artifact)

        # Serialize and deserialize
        data = session.to_dict()
        new_environment = Environment(storage=storage)
        Session.from_dict(data, environment=new_environment)

    def test_session_preserves_uuid(self):
        """Test that session UUID is preserved during serialization."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)
        original_uuid = session.uuid

        storage.save_session(session)
        data = session.to_dict()
        new_environment = Environment(storage=storage)
        new_session = Session.from_dict(data, environment=new_environment)

        assert new_session.uuid == original_uuid

    def test_session_preserves_all_uuids(self):
        """Test that all UUIDs (session, agents, interactions, artifacts) are preserved."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)
        session_uuid = session.uuid

        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=session, config=config)
        agent_uuid = agent.uuid

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
        session.add_agent(agent)

        # Save all entities to storage
        storage.save_interaction(task_def)
        storage.save_agent(agent)
        storage.save_session(session)

        # Serialize and deserialize
        data = session.to_dict()
        new_environment = Environment(storage=storage)
        new_session = Session.from_dict(data, environment=new_environment)

        # Verify all UUIDs are preserved
        assert new_session.uuid == session_uuid
        assert len(new_session.agents) == 1
        assert new_session.agents[0].uuid == agent_uuid
        assert new_session.agents[0].stack.interactions[0].uuid == task_def_uuid

    def test_session_save_and_verify_all_subcomponents(self):
        """Test creating a session verify all sub-components are saved."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)
        session_uuid = session.uuid

        # Create first agent with multiple interactions and artifacts
        config1 = Config(
            name="agent1",
            description="First agent",
            system_template="You are agent 1.",
            tools=[],
            llm_model="model1",
        )
        agent1 = Agent(session=session, config=config1)
        agent1_uuid = agent1.uuid

        # Add first interaction (TaskDefinition)
        task1 = Task(
            name="task1",
            description="Task 1",
            parameters={},
            prompt="Do task 1",
            tools=[],
        )
        task_def1 = TaskDefinition(stack=agent1.stack, task=task1)
        task_def1_uuid = task_def1.uuid
        agent1.stack.add_interaction(task_def1)

        # Add artifact to first interaction
        artifact1 = Text(
            interaction=task_def1, content="Result from task 1", format="plain"
        )
        artifact1_uuid = artifact1.uuid
        task_def1.add_artifact(artifact1)

        # Add second interaction (AskOracle)
        prompt1 = Prompt(type="text", text="Ask something")
        ask_oracle1 = AskOracle(
            stack=agent1.stack, prompt=prompt1, template_inputs={}
        )
        ask_oracle1_uuid = ask_oracle1.uuid
        agent1.stack.add_interaction(ask_oracle1)

        # Add artifact to second interaction
        artifact2 = Text(
            interaction=ask_oracle1,
            content="Oracle response",
            format="markdown",
        )
        artifact2_uuid = artifact2.uuid
        ask_oracle1.add_artifact(artifact2)

        session.add_agent(agent1)

        # Create second agent with interactions and artifacts
        config2 = Config(
            name="agent2",
            description="Second agent",
            system_template="You are agent 2.",
            tools=[],
            llm_model="model2",
        )
        agent2 = Agent(session=session, config=config2)
        agent2_uuid = agent2.uuid

        # Add interaction to second agent
        task2 = Task(
            name="task2",
            description="Task 2",
            parameters={},
            prompt="Do task 2",
            tools=[],
        )
        task_def2 = TaskDefinition(stack=agent2.stack, task=task2)
        task_def2_uuid = task_def2.uuid
        agent2.stack.add_interaction(task_def2)

        # Add artifact to second agent's interaction
        artifact3 = Text(
            interaction=task_def2, content="Result from task 2", format="json"
        )
        artifact3_uuid = artifact3.uuid
        task_def2.add_artifact(artifact3)

        session.add_agent(agent2)

        # Save the session (this should save all sub-components)
        storage.save_session(session)

        # Verify that all components are saved in storage
        # Check session
        assert f"session:{session_uuid}" in storage.store
        assert session_uuid in storage._sessions

        # Check agents
        assert f"agent:{agent1_uuid}" in storage.store
        assert f"agent:{agent2_uuid}" in storage.store
        assert agent1_uuid in storage._agents
        assert agent2_uuid in storage._agents

        # Check interactions
        assert f"interaction:{task_def1_uuid}" in storage.store
        assert f"interaction:{ask_oracle1_uuid}" in storage.store
        assert f"interaction:{task_def2_uuid}" in storage.store
        assert task_def1_uuid in storage._interactions
        assert ask_oracle1_uuid in storage._interactions
        assert task_def2_uuid in storage._interactions

        # Check artifacts
        assert f"artifact:{artifact1_uuid}" in storage.store
        assert f"artifact:{artifact2_uuid}" in storage.store
        assert f"artifact:{artifact3_uuid}" in storage.store
        assert artifact1_uuid in storage._artifacts
        assert artifact2_uuid in storage._artifacts
        assert artifact3_uuid in storage._artifacts

        # Load the session back and verify all components are present
        loaded_session = storage.load_session(
            session_uuid, environment=environment
        )

        # Verify session
        assert loaded_session.uuid == session_uuid
        assert len(loaded_session.agents) == 2

        # Verify first agent
        loaded_agent1 = loaded_session.get_agent(agent1_uuid)
        assert loaded_agent1 is not None
        assert loaded_agent1.uuid == agent1_uuid
        assert loaded_agent1.config.name == "agent1"
        assert len(loaded_agent1.stack.interactions) == 2

        # Verify first agent's interactions
        loaded_task_def1 = loaded_agent1.stack.interactions[0]
        assert loaded_task_def1.uuid == task_def1_uuid
        assert isinstance(loaded_task_def1, TaskDefinition)
        assert len(loaded_task_def1.artifacts) == 1
        assert loaded_task_def1.artifacts[0].uuid == artifact1_uuid
        assert isinstance(loaded_task_def1.artifacts[0], Text)
        assert loaded_task_def1.artifacts[0].content == "Result from task 1"

        loaded_ask_oracle1 = loaded_agent1.stack.interactions[1]
        assert loaded_ask_oracle1.uuid == ask_oracle1_uuid
        assert isinstance(loaded_ask_oracle1, AskOracle)
        assert len(loaded_ask_oracle1.artifacts) == 1
        assert loaded_ask_oracle1.artifacts[0].uuid == artifact2_uuid
        assert isinstance(loaded_ask_oracle1.artifacts[0], Text)
        assert loaded_ask_oracle1.artifacts[0].content == "Oracle response"

        # Verify second agent
        loaded_agent2 = loaded_session.get_agent(agent2_uuid)
        assert loaded_agent2 is not None
        assert loaded_agent2.uuid == agent2_uuid
        assert loaded_agent2.config.name == "agent2"
        assert len(loaded_agent2.stack.interactions) == 1

        # Verify second agent's interaction
        loaded_task_def2 = loaded_agent2.stack.interactions[0]
        assert loaded_task_def2.uuid == task_def2_uuid
        assert isinstance(loaded_task_def2, TaskDefinition)
        assert len(loaded_task_def2.artifacts) == 1
        assert loaded_task_def2.artifacts[0].uuid == artifact3_uuid
        assert isinstance(loaded_task_def2.artifacts[0], Text)
        assert loaded_task_def2.artifacts[0].content == "Result from task 2"
        assert loaded_task_def2.artifacts[0].format == "json"

        # Verify all artifacts can be loaded independently
        loaded_artifact1 = storage.load_artifact(artifact1_uuid)
        assert loaded_artifact1.uuid == artifact1_uuid
        assert isinstance(loaded_artifact1, Text)
        assert loaded_artifact1.content == "Result from task 1"

        loaded_artifact2 = storage.load_artifact(artifact2_uuid)
        assert loaded_artifact2.uuid == artifact2_uuid
        assert isinstance(loaded_artifact2, Text)
        assert loaded_artifact2.content == "Oracle response"

        loaded_artifact3 = storage.load_artifact(artifact3_uuid)
        assert loaded_artifact3.uuid == artifact3_uuid
        assert isinstance(loaded_artifact3, Text)
        assert loaded_artifact3.content == "Result from task 2"


class TestSessionRun:
    """Test Session.run() functionality."""

    def test_session_run_single_agent(self):
        """Test session.run() with single agent."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=session, config=config)

        # Add mock interactions that return True, then False
        mock_interaction1 = Mock()
        mock_interaction1.step.side_effect = [True, False]
        mock_interaction1.artifacts = []
        agent.stack.add_interaction(mock_interaction1)

        session.add_agent(agent)

        # Run until completion
        step_count = session.run()

        assert step_count == 1
        assert mock_interaction1.step.call_count == 2

    def test_session_run_with_max_steps(self):
        """Test session.run() respects max_steps limit."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=session, config=config)

        # Add mock interaction that always returns True
        mock_interaction = Mock()
        mock_interaction.step.return_value = True
        mock_interaction.artifacts = []
        agent.stack.add_interaction(mock_interaction)

        session.add_agent(agent)

        # Run with max_steps limit
        step_count = session.run(max_steps=5)

        assert step_count == 5
        assert mock_interaction.step.call_count == 5

    def test_session_run_with_multiple_agents(self):
        """Test session.run() with multiple agents."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create two agents
        config1 = Config(
            name="agent1",
            description="First agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent1 = Agent(session=session, config=config1)
        mock_interaction1 = Mock()
        # Agent 1: True for 2 steps, then False
        mock_interaction1.step.side_effect = [True, True, False]
        mock_interaction1.artifacts = []
        agent1.stack.add_interaction(mock_interaction1)
        session.add_agent(agent1)

        config2 = Config(
            name="agent2",
            description="Second agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent2 = Agent(session=session, config=config2)
        mock_interaction2 = Mock()
        # Agent 2: True for 1 step, then False
        mock_interaction2.step.side_effect = [False, True, False]
        mock_interaction2.artifacts = []
        agent2.stack.add_interaction(mock_interaction2)
        session.add_agent(agent2)

        # Run until both agents are done
        step_count = session.run()

        # Should run 2 steps (both agents have activity in step 1 and 2)
        assert step_count == 2
        assert mock_interaction1.step.call_count == 3
        assert mock_interaction2.step.call_count == 3

    def test_session_run_returns_zero_if_no_activity(self):
        """Test session.run() returns 0 if no agent activity."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=session, config=config)

        # Add mock interaction that immediately returns False
        mock_interaction = Mock()
        mock_interaction.step.return_value = False
        mock_interaction.artifacts = []
        agent.stack.add_interaction(mock_interaction)

        session.add_agent(agent)

        # Run should complete immediately
        step_count = session.run()

        assert step_count == 0
        assert mock_interaction.step.call_count == 1

    def test_session_run_saves_session(self):
        """Test session.run() saves session after each step and at completion."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=session, config=config)

        # Add mock interactions
        mock_interaction = Mock()
        mock_interaction.step.side_effect = [True, True, False]
        mock_interaction.artifacts = []
        agent.stack.add_interaction(mock_interaction)

        session.add_agent(agent)

        # Run the session
        step_count = session.run()

        assert step_count == 2

        # Session should be saved: once after each step + once at end
        # Initial state is not saved before run starts
        # So we expect: 2 saves during steps + 1 final save = 3 total
        assert session.uuid in storage._sessions
        # Verify session was saved
        assert storage._sessions[session.uuid] is not None

    def test_session_run_with_max_steps_logs_correctly(self):
        """Test session.run() logs when max_steps is reached."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=session, config=config)

        # Add mock interaction that always returns True
        mock_interaction = Mock()
        mock_interaction.step.return_value = True
        mock_interaction.artifacts = []
        agent.stack.add_interaction(mock_interaction)

        session.add_agent(agent)

        # Capture logs
        with patch("gimle.hugin.agent.session.logger") as mock_logger:
            step_count = session.run(max_steps=3)

            assert step_count == 3
            # Check that max steps log was called
            mock_logger.info.assert_any_call("Max steps reached (3)")

    def test_session_run_with_no_max_steps(self):
        """Test session.run() without max_steps runs until completion."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=session, config=config)

        # Add mock interactions with specific sequence
        mock_interaction = Mock()
        mock_interaction.step.side_effect = [True, True, True, False]
        mock_interaction.artifacts = []
        agent.stack.add_interaction(mock_interaction)

        session.add_agent(agent)

        # Run without max_steps
        step_count = session.run()

        assert step_count == 3
        assert mock_interaction.step.call_count == 4

    def test_session_run_empty_session(self):
        """Test session.run() with no agents."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Run empty session
        step_count = session.run()

        assert step_count == 0

    def test_session_run_integration_with_step(self):
        """Test that session.run() correctly integrates with session.step()."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)
        config = Config(
            name="test-agent",
            description="Test agent",
            system_template="You are a helpful assistant.",
            tools=[],
        )
        agent = Agent(session=session, config=config)

        # Add mock interaction
        mock_interaction = Mock()
        # Create a counter to track calls
        call_count = [0]

        def side_effect():
            call_count[0] += 1
            return call_count[0] <= 2  # True for first 2 calls, False after

        mock_interaction.step.side_effect = side_effect
        mock_interaction.artifacts = []
        agent.stack.add_interaction(mock_interaction)

        session.add_agent(agent)

        # Run the session
        step_count = session.run()

        # Should have run 2 steps
        assert step_count == 2
        # step() should have been called 3 times total
        # (once more after the last True to get the False)
        assert call_count[0] == 3
