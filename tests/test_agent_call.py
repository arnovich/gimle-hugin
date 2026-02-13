"""Tests for AgentCall and AgentResult interactions."""

from typing import TYPE_CHECKING, Optional
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.agent.task import Task
from gimle.hugin.interaction.agent_call import AgentCall
from gimle.hugin.interaction.agent_result import AgentResult
from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.interaction.task_result import TaskResult
from gimle.hugin.interaction.waiting import Waiting
from gimle.hugin.tools.tool import Tool

from .memory_storage import MemoryStorage


class TestAgentCallBasic:
    """Test basic AgentCall functionality."""

    def test_agent_call_initialization(self):
        """Test AgentCall initialization with config and task."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=[],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # Create config and task for child agent
        child_config = Config(
            name="child-agent",
            description="Child agent",
            system_template="You are a child agent.",
            tools=[],
        )
        child_task = Task(
            name="child_task",
            description="Task for child agent",
            parameters={},
            prompt="Do something",
            tools=[],
        )

        # Create AgentCall
        agent_call = AgentCall(
            stack=parent_agent.stack, config=child_config, task=child_task
        )

        assert agent_call.config == child_config
        assert agent_call.task == child_task
        assert agent_call.agent_id is None
        assert hasattr(agent_call, "uuid")

    def test_agent_call_step_creates_child_agent(self):
        """Test that stepping AgentCall creates a child agent and adds Waiting interaction."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=[],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # Create config and task for child agent
        child_config = Config(
            name="child-agent",
            description="Child agent",
            system_template="You are a child agent.",
            tools=[],
        )
        child_task = Task(
            name="child_task",
            description="Task for child agent",
            parameters={},
            prompt="Do something",
            tools=[],
        )

        # Create and add AgentCall to parent's stack
        agent_call = AgentCall(
            stack=parent_agent.stack, config=child_config, task=child_task
        )
        parent_agent.stack.add_interaction(agent_call)

        # Initially there should be only 1 agent (parent) and 1 interaction
        assert len(session.agents) == 1
        initial_parent_stack_size = len(parent_agent.stack.interactions)

        # Step the AgentCall
        result = agent_call.step()

        # Should return True and create a child agent
        assert result is True
        assert len(session.agents) == 2
        assert agent_call.agent_id is not None

        # Verify child agent was created
        child_agent = session.get_agent(agent_call.agent_id)
        assert child_agent is not None
        assert child_agent.config.name == "child-agent"
        assert len(child_agent.stack.interactions) == 1
        assert isinstance(child_agent.stack.interactions[0], TaskDefinition)
        assert child_agent.stack.interactions[0].task.name == "child_task"

        # Verify Waiting interaction was added to parent's stack
        assert (
            len(parent_agent.stack.interactions)
            == initial_parent_stack_size + 1
        )
        last_interaction = parent_agent.stack.interactions[-1]
        assert isinstance(last_interaction, Waiting)

    def test_waiting_interaction_returns_false(self):
        """Test that Waiting interaction returns False when stepped."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=[],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # Create and add Waiting interaction
        waiting = Waiting(stack=parent_agent.stack)
        parent_agent.stack.add_interaction(waiting)

        # Stepping Waiting should return False (pauses parent agent)
        result = waiting.step()
        assert result is False


class TestAgentCallWithTool:
    """Test AgentCall creation via a tool."""

    @pytest.fixture
    def call_agent_tool(self):
        """Register a test tool that creates an AgentCall."""

        @Tool.register(
            name="call_agent",
            description="Call another agent to perform a task",
            parameters={
                "agent_name": {
                    "type": "string",
                    "description": "Name of the agent to call",
                    "required": True,
                },
                "task_prompt": {
                    "type": "string",
                    "description": "Task for the agent to perform",
                    "required": True,
                },
            },
            is_interactive=False,
        )
        def call_agent(
            agent_name: str,
            task_prompt: str,
            stack: "Stack",
            branch: Optional[str] = None,
        ) -> AgentCall:
            """Call another agent to perform a task."""
            # Create config for child agent
            child_config = Config(
                name=agent_name,
                description=f"Agent {agent_name}",
                system_template="You are a helpful assistant.",
                tools=["builtins.finish"],
            )

            # Create task for child agent
            child_task = Task(
                name=f"{agent_name}_task",
                description=f"Task for {agent_name}",
                parameters={},
                prompt=task_prompt,
                tools=["builtins.finish"],
            )

            # Return AgentCall interaction
            return AgentCall(stack=stack, config=child_config, task=child_task)

        yield

        # Cleanup: remove the tool after test
        Tool.registry.remove("call_agent")

    def test_tool_creates_agent_call(self, call_agent_tool):
        """Test that a tool can create and return an AgentCall."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=["call_agent"],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # Get the tool
        tool = Tool.get_tool("call_agent")
        assert tool is not None

        # Call the tool
        agent_call = tool.func(
            agent_name="worker",
            task_prompt="Calculate 2 + 2",
            stack=parent_agent.stack,
        )

        # Verify AgentCall was created
        assert isinstance(agent_call, AgentCall)
        assert agent_call.config.name == "worker"
        assert agent_call.task.prompt == "Calculate 2 + 2"
        assert agent_call.agent_id is None


class TestAgentResult:
    """Test AgentResult functionality."""

    def test_agent_result_initialization(self):
        """Test AgentResult initialization."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=[],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # Create child agent with task result
        child_config = Config(
            name="child-agent",
            description="Child agent",
            system_template="You are a child agent.",
            tools=[],
        )
        child_agent = Agent(session=session, config=child_config)
        child_task = Task(
            name="child_task",
            description="Task for child agent",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=child_agent.stack, task=child_task)
        child_agent.stack.add_interaction(task_def)

        # Create TaskResult
        task_result = TaskResult(
            stack=child_agent.stack,
            finish_type="success",
            summary="Done",
            reason="Completed",
        )
        child_agent.stack.add_interaction(task_result)
        session.add_agent(child_agent)

        # Create AgentResult with TaskResult ID
        agent_result = AgentResult(
            stack=parent_agent.stack, task_result_id=task_result.id
        )

        assert agent_result.task_result_id == task_result.id
        assert hasattr(agent_result, "uuid")

    def test_agent_result_step_adds_ask_oracle(self):
        """Test that stepping AgentResult adds an AskOracle to the stack."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent with a TaskDefinition (required for ToolCall)
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=["call_agent"],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # Add TaskDefinition to parent
        parent_task = Task(
            name="parent_task",
            description="Parent task",
            parameters={},
            prompt="Orchestrate child agents",
            tools=["call_agent"],
        )
        parent_task_def = TaskDefinition(
            stack=parent_agent.stack, task=parent_task
        )
        parent_agent.stack.add_interaction(parent_task_def)

        # Add a ToolCall to parent (AgentResult.step needs this)
        from gimle.hugin.interaction.tool_call import ToolCall

        tool_call = ToolCall(
            stack=parent_agent.stack,
            tool="call_agent",
            args={"agent_name": "child-agent", "task_prompt": "Do something"},
            tool_call_id="call_123",
        )
        parent_agent.stack.add_interaction(tool_call)

        # Create child agent with TaskDefinition and TaskResult
        child_config = Config(
            name="child-agent",
            description="Child agent",
            system_template="You are a child agent.",
            tools=[],
        )
        child_task = Task(
            name="child_task",
            description="Task for child agent",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        child_agent = Agent.create_from_task(
            session=session, config=child_config, task=child_task, caller=None
        )
        session.add_agent(child_agent)

        # Add TaskResult to child agent
        task_result = TaskResult(
            stack=child_agent.stack,
            finish_type="success",
            result={"output": "Done"},
        )
        child_agent.stack.add_interaction(task_result)

        # Create and add AgentResult to parent's stack (using TaskResult ID)
        agent_result = AgentResult(
            stack=parent_agent.stack, task_result_id=task_result.id
        )
        parent_agent.stack.add_interaction(agent_result)

        # Step the AgentResult
        result = agent_result.step()

        # Should return True and add AskOracle to stack
        assert result is True

        # Verify an AskOracle was added to the parent stack
        ask_oracles = [
            i
            for i in parent_agent.stack.interactions
            if isinstance(i, AskOracle)
        ]
        assert len(ask_oracles) == 1
        ask_oracle = ask_oracles[0]

        # Verify the AskOracle has the correct prompt type
        assert ask_oracle.prompt.type == "tool_result"
        assert ask_oracle.prompt.tool_name == "call_agent"
        assert ask_oracle.prompt.tool_use_id == "call_123"

        # Verify the template_inputs contain the TaskResult's result
        assert ask_oracle.template_inputs == {"output": "Done"}


class TestAgentCallResultIntegration:
    """Test full integration of AgentCall and AgentResult."""

    @pytest.fixture
    def call_agent_tool(self):
        """Register a test tool that creates an AgentCall."""

        @Tool.register(
            name="call_agent",
            description="Call another agent to perform a task",
            parameters={
                "agent_name": {
                    "type": "string",
                    "description": "Name of the agent to call",
                    "required": True,
                },
                "task_prompt": {
                    "type": "string",
                    "description": "Task for the agent to perform",
                    "required": True,
                },
            },
            is_interactive=False,
        )
        def call_agent(
            agent_name: str,
            task_prompt: str,
            stack: "Stack",
            branch: Optional[str] = None,
        ) -> AgentCall:
            """Call another agent to perform a task."""
            # Create config for child agent
            child_config = Config(
                name=agent_name,
                description=f"Agent {agent_name}",
                system_template="You are a helpful assistant.",
                tools=["builtins.finish"],
            )

            # Create task for child agent
            child_task = Task(
                name=f"{agent_name}_task",
                description=f"Task for {agent_name}",
                parameters={},
                prompt=task_prompt,
                tools=["builtins.finish"],
            )

            # Return AgentCall interaction
            return AgentCall(stack=stack, config=child_config, task=child_task)

        yield

        # Cleanup: remove the tool after test
        Tool.registry.remove("call_agent")

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_full_agent_call_flow(self, mock_chat_completion, call_agent_tool):
        """Test full flow: parent calls child agent, child completes, result returned."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            llm_model="test-model",
            tools=["call_agent"],
        )
        parent_task = Task(
            name="parent_task",
            description="Parent task",
            parameters={},
            prompt="Delegate work to a child agent",
            tools=["call_agent"],
        )
        parent_agent = Agent.create_from_task(
            session=session, config=parent_config, task=parent_task, caller=None
        )
        session.add_agent(parent_agent)

        # Mock chat completion to return tool call to call_agent
        call_count = [0]

        def chat_completion_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Parent agent calls the call_agent tool
                return {
                    "role": "assistant",
                    "content": {
                        "agent_name": "worker",
                        "task_prompt": "Calculate 2 + 2",
                    },
                    "tool_call": "call_agent",
                    "tool_call_id": "call_1",
                }
            elif call_count[0] == 2:
                # Child agent calls finish tool
                return {
                    "role": "assistant",
                    "content": {
                        "finish_type": "success",
                        "result": "2 + 2 = 4",
                    },
                    "tool_call": "builtins.finish",
                    "tool_call_id": "call_2",
                }
            else:
                # Any other calls just return text
                return {
                    "role": "assistant",
                    "content": "Task completed",
                    "tool_call": None,
                    "tool_call_id": None,
                }

        mock_chat_completion.side_effect = chat_completion_side_effect

        # Run the session for a few steps
        step_count = 0
        max_steps = 20

        while step_count < max_steps:
            result = session.step()
            step_count += 1

            if not result:
                break

            # Safety check
            assert len(session.agents) <= 2, "Should have at most 2 agents"

        # Verify that child agent was created
        assert len(session.agents) == 2

        # Find child agent
        child_agent = next(
            (a for a in session.agents if a.config.name == "worker"), None
        )
        assert child_agent is not None
        assert child_agent.config.name == "worker"

        # Verify child agent has TaskDefinition and TaskResult
        assert len(child_agent.stack.interactions) >= 2
        assert isinstance(child_agent.stack.interactions[0], TaskDefinition)
        # The last interaction should be TaskResult after child finishes
        task_result_found = any(
            isinstance(i, TaskResult) for i in child_agent.stack.interactions
        )
        assert task_result_found, "Child agent should have a TaskResult"

        # Verify parent agent has AgentCall and Waiting
        agent_call_found = any(
            isinstance(i, AgentCall) for i in parent_agent.stack.interactions
        )
        assert agent_call_found, "Parent agent should have an AgentCall"

        waiting_found = any(
            isinstance(i, Waiting) for i in parent_agent.stack.interactions
        )
        assert waiting_found, "Parent agent should have a Waiting interaction"

    def test_child_agent_has_caller_reference(self):
        """Test that child agent's TaskDefinition has reference to caller."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=[],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # Create config and task for child agent
        child_config = Config(
            name="child-agent",
            description="Child agent",
            system_template="You are a child agent.",
            tools=[],
        )
        child_task = Task(
            name="child_task",
            description="Task for child agent",
            parameters={},
            prompt="Do something",
            tools=[],
        )

        # Create and step AgentCall
        agent_call = AgentCall(
            stack=parent_agent.stack, config=child_config, task=child_task
        )
        parent_agent.stack.add_interaction(agent_call)
        agent_call.step()

        # Get child agent
        child_agent = session.get_agent(agent_call.agent_id)
        assert child_agent is not None

        # Verify TaskDefinition has caller reference
        task_def = child_agent.stack.interactions[0]
        assert isinstance(task_def, TaskDefinition)
        assert task_def.caller_id == parent_agent.id
        assert task_def.caller == parent_agent

    def test_task_result_adds_agent_result_to_parent(self):
        """Test that TaskResult adds AgentResult to parent agent's stack."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=[],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # Create child agent with caller reference
        child_config = Config(
            name="child-agent",
            description="Child agent",
            system_template="You are a child agent.",
            tools=[],
        )
        child_task = Task(
            name="child_task",
            description="Task for child agent",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        child_agent = Agent.create_from_task(
            session=session,
            config=child_config,
            task=child_task,
            caller=parent_agent,
        )
        session.add_agent(child_agent)

        # Record initial parent stack size
        initial_parent_stack_size = len(parent_agent.stack.interactions)

        # Create and step TaskResult in child agent
        task_result = TaskResult(
            stack=child_agent.stack,
            finish_type="success",
            summary="Task completed successfully",
            reason="All work done",
        )
        child_agent.stack.add_interaction(task_result)

        # Step the task result
        result = task_result.step()

        # Should return True (adds AgentResult and Waiting)
        assert result is True

        # Verify AgentResult was added to parent's stack
        assert (
            len(parent_agent.stack.interactions)
            == initial_parent_stack_size + 1
        )
        last_interaction = parent_agent.stack.interactions[-1]
        assert isinstance(last_interaction, AgentResult)
        # The task_result_id should be the TaskResult interaction ID
        assert last_interaction.task_result_id == task_result.id

        # Verify Waiting was added to child's stack
        waiting_interaction = child_agent.stack.interactions[-1]
        assert isinstance(waiting_interaction, Waiting)

    def test_agent_result_contains_correct_task_result_id(self):
        """Test that AgentResult contains the correct TaskResult ID."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=[],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # Create child agent with caller reference
        child_config = Config(
            name="child-agent",
            description="Child agent",
            system_template="You are a child agent.",
            tools=[],
        )
        child_task = Task(
            name="child_task",
            description="Task for child agent",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        child_agent = Agent.create_from_task(
            session=session,
            config=child_config,
            task=child_task,
            caller=parent_agent,
        )
        session.add_agent(child_agent)

        # Create and step TaskResult
        task_result = TaskResult(
            stack=child_agent.stack,
            finish_type="success",
            summary="Done",
            reason="Completed",
        )
        child_agent.stack.add_interaction(task_result)
        task_result.step()

        # Get the AgentResult from parent's stack
        agent_result = parent_agent.stack.interactions[-1]
        assert isinstance(agent_result, AgentResult)

        # Verify it points to the TaskResult interaction
        assert agent_result.task_result_id == task_result.id

        # Verify we can retrieve the TaskResult using the ID
        retrieved_task_result = session.get_interaction(
            agent_result.task_result_id
        )
        assert retrieved_task_result == task_result
        assert isinstance(retrieved_task_result, TaskResult)

    def test_multiple_child_agents_return_results_to_parent(self):
        """Test that multiple child agents can return results to parent."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=[],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # Create first child agent
        child1_config = Config(
            name="child-agent-1",
            description="First child agent",
            system_template="You are child 1.",
            tools=[],
        )
        child1_task = Task(
            name="child1_task",
            description="Task 1",
            parameters={},
            prompt="Do task 1",
            tools=[],
        )
        child1_agent = Agent.create_from_task(
            session=session,
            config=child1_config,
            task=child1_task,
            caller=parent_agent,
        )
        session.add_agent(child1_agent)

        # Create second child agent
        child2_config = Config(
            name="child-agent-2",
            description="Second child agent",
            system_template="You are child 2.",
            tools=[],
        )
        child2_task = Task(
            name="child2_task",
            description="Task 2",
            parameters={},
            prompt="Do task 2",
            tools=[],
        )
        child2_agent = Agent.create_from_task(
            session=session,
            config=child2_config,
            task=child2_task,
            caller=parent_agent,
        )
        session.add_agent(child2_agent)

        initial_parent_stack_size = len(parent_agent.stack.interactions)

        # First child completes
        task_result1 = TaskResult(
            stack=child1_agent.stack,
            finish_type="success",
            summary="Child 1 done",
            reason="Completed task 1",
        )
        child1_agent.stack.add_interaction(task_result1)
        task_result1.step()

        # Second child completes
        task_result2 = TaskResult(
            stack=child2_agent.stack,
            finish_type="success",
            summary="Child 2 done",
            reason="Completed task 2",
        )
        child2_agent.stack.add_interaction(task_result2)
        task_result2.step()

        # Verify both AgentResults are on parent's stack
        assert (
            len(parent_agent.stack.interactions)
            == initial_parent_stack_size + 2
        )

        # Check first result - should point to TaskResult, not agent
        result1 = parent_agent.stack.interactions[-2]
        assert isinstance(result1, AgentResult)
        assert result1.task_result_id == task_result1.id

        # Check second result - should point to TaskResult, not agent
        result2 = parent_agent.stack.interactions[-1]
        assert isinstance(result2, AgentResult)
        assert result2.task_result_id == task_result2.id

    def test_task_result_without_caller_does_not_add_agent_result(self):
        """Test that TaskResult without caller doesn't add AgentResult."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create agent without caller (top-level agent)
        agent_config = Config(
            name="top-level-agent",
            description="Top level agent",
            system_template="You are a top level agent.",
            tools=[],
        )
        agent_task = Task(
            name="top_task",
            description="Top level task",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        agent = Agent.create_from_task(
            session=session, config=agent_config, task=agent_task, caller=None
        )
        session.add_agent(agent)

        # Create TaskResult
        task_result = TaskResult(
            stack=agent.stack,
            finish_type="success",
            summary="Done",
            reason="Completed",
        )
        agent.stack.add_interaction(task_result)

        # Step returns True and adds Waiting (no caller to notify)
        result = task_result.step()
        assert result is True

        # Verify a Waiting interaction was added
        from gimle.hugin.interaction.waiting import Waiting

        assert isinstance(agent.stack.interactions[-1], Waiting)

        # Verify no AgentResult was added anywhere (only this agent exists)
        assert len(session.agents) == 1
        # The stack should have TaskDefinition, TaskResult, and Waiting (no AgentResult)
        interaction_types = [type(i).__name__ for i in agent.stack.interactions]
        assert "AgentResult" not in interaction_types


class TestAgentCallReuse:
    """Test reusing existing agents via AgentCall."""

    def test_agent_call_creates_new_agent_without_agent_id(self):
        """Test that AgentCall without agent_id creates a new agent."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=[],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # Create AgentCall without agent_id
        child_config = Config(
            name="child-agent",
            description="Child agent",
            system_template="You are a child agent.",
            tools=[],
        )
        child_task = Task(
            name="child_task",
            description="Task for child agent",
            parameters={},
            prompt="Do first task",
            tools=[],
        )
        agent_call = AgentCall(
            stack=parent_agent.stack,
            config=child_config,
            task=child_task,
            agent_id=None,  # Explicitly no agent_id
        )
        parent_agent.stack.add_interaction(agent_call)

        # Initially one agent (parent)
        assert len(session.agents) == 1

        # Step creates new agent
        agent_call.step()
        assert len(session.agents) == 2

        # Verify agent_id was set
        assert agent_call.agent_id is not None

        # Verify child agent has one TaskDefinition
        child_agent = session.get_agent(agent_call.agent_id)
        assert child_agent is not None
        assert len(child_agent.stack.interactions) == 1
        assert isinstance(child_agent.stack.interactions[0], TaskDefinition)

    def test_agent_call_reuses_existing_agent_with_agent_id(self):
        """Test that AgentCall with agent_id reuses existing agent."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=[],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # Create child agent first
        child_config = Config(
            name="child-agent",
            description="Child agent",
            system_template="You are a child agent.",
            tools=[],
        )
        first_task = Task(
            name="first_task",
            description="First task",
            parameters={},
            prompt="Do first task",
            tools=[],
        )
        child_agent = Agent.create_from_task(
            session=session,
            config=child_config,
            task=first_task,
            caller=parent_agent,
        )
        session.add_agent(child_agent)

        # Initially two agents
        assert len(session.agents) == 2
        initial_child_interactions = len(child_agent.stack.interactions)
        initial_parent_interactions = len(parent_agent.stack.interactions)

        # Create AgentCall WITH agent_id to reuse existing agent
        second_task = Task(
            name="second_task",
            description="Second task",
            parameters={},
            prompt="Do second task",
            tools=[],
        )
        agent_call = AgentCall(
            stack=parent_agent.stack,
            config=child_config,
            task=second_task,
            agent_id=child_agent.id,  # Reuse existing agent
        )
        parent_agent.stack.add_interaction(agent_call)

        # Step should reuse agent, not create new one
        agent_call.step()
        assert len(session.agents) == 2  # Still only 2 agents

        # Verify new TaskDefinition was added to existing agent
        assert (
            len(child_agent.stack.interactions)
            == initial_child_interactions + 1
        )
        # Last interaction should be the new TaskDefinition
        last_interaction = child_agent.stack.interactions[-1]
        assert isinstance(last_interaction, TaskDefinition)
        assert last_interaction.task.name == "second_task"

        # Verify Waiting was added to parent's stack
        assert (
            len(parent_agent.stack.interactions)
            == initial_parent_interactions + 2  # AgentCall + Waiting
        )
        waiting_interaction = parent_agent.stack.interactions[-1]
        assert isinstance(waiting_interaction, Waiting)

    def test_multiple_calls_to_same_agent_accumulate_context(self):
        """Test that multiple calls to same agent accumulate context."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=[],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # First call - creates new agent
        child_config = Config(
            name="assistant",
            description="Assistant agent",
            system_template="You are an assistant.",
            tools=[],
        )
        task1 = Task(
            name="task1",
            description="Task 1",
            parameters={},
            prompt="Remember: user likes pizza",
            tools=[],
        )
        call1 = AgentCall(
            stack=parent_agent.stack, config=child_config, task=task1
        )
        parent_agent.stack.add_interaction(call1)
        call1.step()

        child_agent_id = call1.agent_id
        assert child_agent_id is not None

        # Second call - reuses same agent
        task2 = Task(
            name="task2",
            description="Task 2",
            parameters={},
            prompt="What does the user like?",
            tools=[],
        )
        call2 = AgentCall(
            stack=parent_agent.stack,
            config=child_config,
            task=task2,
            agent_id=child_agent_id,  # Reuse
        )
        parent_agent.stack.add_interaction(call2)
        call2.step()

        # Third call - reuses same agent again
        task3 = Task(
            name="task3",
            description="Task 3",
            parameters={},
            prompt="Also remember: user is allergic to peanuts",
            tools=[],
        )
        call3 = AgentCall(
            stack=parent_agent.stack,
            config=child_config,
            task=task3,
            agent_id=child_agent_id,  # Reuse
        )
        parent_agent.stack.add_interaction(call3)
        call3.step()

        # Verify only one child agent was created
        assert len(session.agents) == 2

        # Verify child agent has all three tasks in its stack
        child_agent = session.get_agent(child_agent_id)
        assert child_agent is not None
        assert len(child_agent.stack.interactions) == 3

        task_definitions = [
            i
            for i in child_agent.stack.interactions
            if isinstance(i, TaskDefinition)
        ]
        assert len(task_definitions) == 3
        assert task_definitions[0].task.prompt == "Remember: user likes pizza"
        assert task_definitions[1].task.prompt == "What does the user like?"
        assert (
            task_definitions[2].task.prompt
            == "Also remember: user is allergic to peanuts"
        )

    def test_agent_call_with_invalid_agent_id_raises_error(self):
        """Test that AgentCall with invalid agent_id raises error."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=[],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # Create AgentCall with non-existent agent_id
        child_config = Config(
            name="child-agent",
            description="Child agent",
            system_template="You are a child agent.",
            tools=[],
        )
        child_task = Task(
            name="child_task",
            description="Task for child agent",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        agent_call = AgentCall(
            stack=parent_agent.stack,
            config=child_config,
            task=child_task,
            agent_id="non-existent-id",
        )
        parent_agent.stack.add_interaction(agent_call)

        # Step should raise error
        with pytest.raises(ValueError, match="Agent non-existent-id not found"):
            agent_call.step()

    def test_tool_returns_agent_call_with_agent_id_for_reuse(self):
        """Test tool pattern that returns AgentCall with agent_id for reuse."""
        # Track the agent_id across calls
        persistent_agent_id = [None]

        @Tool.register(
            name="call_persistent_agent",
            description="Call an agent that maintains context",
            parameters={
                "task_prompt": {
                    "type": "string",
                    "description": "Task for the agent to perform",
                    "required": True,
                },
            },
            is_interactive=False,
        )
        def call_persistent_agent(
            task_prompt: str, stack: "Stack", branch: Optional[str] = None
        ) -> AgentCall:
            """Call an agent, reusing if it already exists."""
            child_config = Config(
                name="persistent-assistant",
                description="Persistent assistant agent",
                system_template="You are a persistent assistant.",
                tools=["builtins.finish"],
            )

            child_task = Task(
                name="assistant_task",
                description="Task for assistant",
                parameters={},
                prompt=task_prompt,
                tools=["builtins.finish"],
            )

            # Reuse agent if it exists
            return AgentCall(
                stack=stack,
                config=child_config,
                task=child_task,
                agent_id=persistent_agent_id[0],  # None first time, ID after
            )

        try:
            storage = MemoryStorage()
            environment = Environment(storage=storage)
            session = Session(environment=environment)

            # Create parent agent
            parent_config = Config(
                name="parent-agent",
                description="Parent agent",
                system_template="You are a parent agent.",
                tools=["call_persistent_agent"],
            )
            parent_agent = Agent(session=session, config=parent_config)
            session.add_agent(parent_agent)

            # First call - creates new agent
            tool = Tool.get_tool("call_persistent_agent")
            agent_call1 = tool.func(
                task_prompt="First task",
                stack=parent_agent.stack,
                branch=None,
            )
            parent_agent.stack.add_interaction(agent_call1)
            agent_call1.step()

            # Store the agent_id for reuse
            persistent_agent_id[0] = agent_call1.agent_id
            assert persistent_agent_id[0] is not None

            # Second call - reuses agent
            agent_call2 = tool.func(
                task_prompt="Second task",
                stack=parent_agent.stack,
                branch=None,
            )
            parent_agent.stack.add_interaction(agent_call2)
            agent_call2.step()

            # Verify same agent was reused
            assert agent_call2.agent_id == persistent_agent_id[0]
            assert len(session.agents) == 2  # Only parent and one child

            # Verify child has both tasks
            child_agent = session.get_agent(persistent_agent_id[0])
            assert len(child_agent.stack.interactions) == 2

        finally:
            # Cleanup
            Tool.registry.remove("call_persistent_agent")

    def test_agent_reuse_maintains_caller_reference(self):
        """Test that reused agent maintains caller reference."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=[],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # First call - creates new agent
        child_config = Config(
            name="child-agent",
            description="Child agent",
            system_template="You are a child agent.",
            tools=[],
        )
        task1 = Task(
            name="task1",
            description="Task 1",
            parameters={},
            prompt="First task",
            tools=[],
        )
        call1 = AgentCall(
            stack=parent_agent.stack, config=child_config, task=task1
        )
        parent_agent.stack.add_interaction(call1)
        call1.step()

        child_agent_id = call1.agent_id

        # Second call - reuses agent
        task2 = Task(
            name="task2",
            description="Task 2",
            parameters={},
            prompt="Second task",
            tools=[],
        )
        call2 = AgentCall(
            stack=parent_agent.stack,
            config=child_config,
            task=task2,
            agent_id=child_agent_id,
        )
        parent_agent.stack.add_interaction(call2)
        call2.step()

        # Verify both TaskDefinitions have the same caller
        child_agent = session.get_agent(child_agent_id)
        task_defs = [
            i
            for i in child_agent.stack.interactions
            if isinstance(i, TaskDefinition)
        ]

        assert len(task_defs) == 2
        assert task_defs[0].caller == parent_agent
        assert task_defs[1].caller == parent_agent


class TestAgentCallSerialization:
    """Test AgentCall and AgentResult serialization."""

    def test_agent_call_serialization(self):
        """Test AgentCall can be serialized and deserialized."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=[],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # Create config and task for child agent
        child_config = Config(
            name="child-agent",
            description="Child agent",
            system_template="You are a child agent.",
            tools=["builtins.finish"],
        )
        child_task = Task(
            name="child_task",
            description="Task for child agent",
            parameters={},
            prompt="Do something",
            tools=["builtins.finish"],
        )

        # Create AgentCall
        agent_call = AgentCall(
            stack=parent_agent.stack, config=child_config, task=child_task
        )
        parent_agent.stack.add_interaction(agent_call)

        # Save to storage
        storage.save_interaction(agent_call)

        # Serialize and deserialize using the Interaction base class method
        data = agent_call.to_dict()
        from gimle.hugin.interaction.interaction import Interaction

        loaded_agent_call = Interaction.from_dict(
            data, stack=parent_agent.stack
        )

        # Verify properties are preserved
        assert isinstance(loaded_agent_call, AgentCall)
        assert loaded_agent_call.uuid == agent_call.uuid
        assert loaded_agent_call.config.name == child_config.name
        assert loaded_agent_call.task.name == child_task.name
        assert loaded_agent_call.agent_id == agent_call.agent_id

    def test_agent_result_serialization(self):
        """Test AgentResult can be serialized and deserialized."""
        storage = MemoryStorage()
        environment = Environment(storage=storage)
        session = Session(environment=environment)

        # Create parent agent
        parent_config = Config(
            name="parent-agent",
            description="Parent agent",
            system_template="You are a parent agent.",
            tools=[],
        )
        parent_agent = Agent(session=session, config=parent_config)
        session.add_agent(parent_agent)

        # Create child agent with TaskResult
        child_config = Config(
            name="child-agent",
            description="Child agent",
            system_template="You are a child agent.",
            tools=[],
        )
        child_task = Task(
            name="child_task",
            description="Task for child agent",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        child_agent = Agent.create_from_task(
            session=session, config=child_config, task=child_task, caller=None
        )
        session.add_agent(child_agent)

        # Create TaskResult
        task_result = TaskResult(
            stack=child_agent.stack,
            finish_type="success",
            summary="Done",
            reason="Completed",
        )
        child_agent.stack.add_interaction(task_result)

        # Create AgentResult with TaskResult ID
        agent_result = AgentResult(
            stack=parent_agent.stack, task_result_id=task_result.id
        )
        parent_agent.stack.add_interaction(agent_result)

        # Save to storage
        storage.save_interaction(agent_result)

        # Serialize and deserialize
        data = agent_result.to_dict()
        from gimle.hugin.interaction.interaction import Interaction

        loaded_agent_result = Interaction.from_dict(
            data, stack=parent_agent.stack
        )

        # Verify properties are preserved
        assert isinstance(loaded_agent_result, AgentResult)
        assert loaded_agent_result.uuid == agent_result.uuid
        assert loaded_agent_result.task_result_id == task_result.id
