"""Tests for deterministic control flow features.

This module tests three levels of deterministic control:
1. Tool Chaining - Tools calling other tools directly
2. Task Chaining - Tasks chaining to other tasks
3. Config State Machine - Automatic config transitions
"""

from typing import Any
from unittest.mock import Mock, patch

import pytest

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.config_state_machine import (
    ConfigStateMachine,
    ConfigTransition,
    TransitionTrigger,
)
from gimle.hugin.agent.task import Task
from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.stack import Stack
from gimle.hugin.interaction.task_chain import TaskChain
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.interaction.task_result import TaskResult
from gimle.hugin.interaction.tool_call import ToolCall
from gimle.hugin.interaction.tool_result import ToolResult
from gimle.hugin.llm.prompt.prompt import Prompt
from gimle.hugin.tools.tool import Tool, ToolResponse

# =============================================================================
# Level 1: Tool Chaining Tests
# =============================================================================


class TestToolResponseChaining:
    """Test ToolResponse chaining fields."""

    def test_tool_response_with_next_tool(self):
        """Test creating ToolResponse with next_tool field."""
        response = ToolResponse(
            is_error=False,
            content={"result": "data"},
            next_tool="process_data",
            next_tool_args={"data": "test"},
            include_in_context=False,
        )

        assert response.next_tool == "process_data"
        assert response.next_tool_args == {"data": "test"}
        assert response.include_in_context is False

    def test_tool_response_default_include_in_context(self):
        """Test that include_in_context defaults to True."""
        response = ToolResponse(
            is_error=False,
            content={"result": "data"},
        )

        assert response.include_in_context is True
        assert response.next_tool is None
        assert response.next_tool_args is None


class TestToolResultChaining:
    """Test ToolResult deterministic chaining."""

    def test_tool_result_with_next_tool(self, mock_agent):
        """Test ToolResult chaining to next tool."""
        stack = mock_agent.stack

        # Register the next tool
        @Tool.register(
            name="chained_tool",
            description="Tool that is chained to",
            parameters={
                "data": {"type": "string", "description": "Input data"}
            },
        )
        def chained_tool(
            data: str, stack: Stack, **kwargs: Any
        ) -> ToolResponse:
            return ToolResponse(is_error=False, content={"processed": data})

        try:
            # Create ToolResult with next_tool
            tool_result = ToolResult(
                stack=stack,
                result={"intermediate": "data"},
                tool_call_id="test_call_123",
                tool_name="first_tool",
                is_error=False,
                next_tool="chained_tool",
                next_tool_args={"data": "test_value"},
                include_in_context=False,
            )
            stack.add_interaction(tool_result)

            # Step should create a ToolCall for the chained tool
            initial_count = len(stack.interactions)
            result = tool_result.step()

            assert result is True
            assert len(stack.interactions) == initial_count + 1

            # Verify the new interaction is a ToolCall
            new_interaction = stack.interactions[-1]
            assert isinstance(new_interaction, ToolCall)
            assert new_interaction.tool == "chained_tool"
            assert new_interaction.args == {"data": "test_value"}
            assert (
                new_interaction.tool_call_id == "test_call_123"
            )  # Inherits from parent
        finally:
            Tool.registry.remove("chained_tool")

    def test_tool_result_without_next_tool(self, mock_agent):
        """Test ToolResult without chaining returns to oracle."""
        stack = mock_agent.stack

        # Add required TaskDefinition
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Create ToolResult without next_tool
        tool_result = ToolResult(
            stack=stack,
            result={"data": "result"},
            tool_call_id="test_call_456",
            tool_name="some_tool",
            is_error=False,
        )
        stack.add_interaction(tool_result)

        # Step should create AskOracle (default behavior)
        result = tool_result.step()

        assert result is True
        new_interaction = stack.interactions[-1]
        assert isinstance(new_interaction, AskOracle)


class TestToolChainingFlow:
    """Test complete tool chaining flow."""

    @pytest.fixture
    def chained_tools(self):
        """Register a chain of tools."""
        added_tools = []

        @Tool.register(
            name="validate_tool",
            description="Validates data and chains to transform",
            parameters={
                "data": {"type": "string", "description": "Data to validate"}
            },
        )
        def validate_tool(
            data: str, stack: Stack, **kwargs: Any
        ) -> ToolResponse:
            return ToolResponse(
                is_error=False,
                content={"status": "validated", "data": data},
                next_tool="transform_tool",
                next_tool_args={"validated_data": data},
                include_in_context=False,
            )

        added_tools.append("validate_tool")

        @Tool.register(
            name="transform_tool",
            description="Transforms data and chains to store",
            parameters={
                "validated_data": {
                    "type": "string",
                    "description": "Validated data",
                }
            },
        )
        def transform_tool(
            validated_data: str, stack: Stack, **kwargs: Any
        ) -> ToolResponse:
            return ToolResponse(
                is_error=False,
                content={
                    "status": "transformed",
                    "data": validated_data.upper(),
                },
                next_tool="store_tool",
                next_tool_args={"transformed_data": validated_data.upper()},
                include_in_context=False,
            )

        added_tools.append("transform_tool")

        @Tool.register(
            name="store_tool",
            description="Stores data (end of chain)",
            parameters={
                "transformed_data": {
                    "type": "string",
                    "description": "Data to store",
                }
            },
        )
        def store_tool(
            transformed_data: str, stack: Stack, **kwargs: Any
        ) -> ToolResponse:
            return ToolResponse(
                is_error=False,
                content={"status": "stored", "data": transformed_data},
                # No next_tool - end of chain
            )

        added_tools.append("store_tool")

        yield

        for tool_name in added_tools:
            Tool.registry.remove(tool_name)

    def test_complete_tool_chain(self, mock_agent, chained_tools):
        """Test a complete chain of three tools."""
        stack = mock_agent.stack

        # Add required TaskDefinition
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Process data",
            tools=["validate_tool", "transform_tool", "store_tool"],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Start with initial ToolCall (from oracle)
        tool_call = ToolCall(
            stack=stack,
            tool="validate_tool",
            args={"data": "test_input"},
            tool_call_id="oracle_call_1",
        )
        stack.add_interaction(tool_call)

        # Step 1: ToolCall -> ToolResult (validate)
        tool_call.step()
        assert isinstance(stack.interactions[-1], ToolResult)
        tool_result1 = stack.interactions[-1]
        assert tool_result1.next_tool == "transform_tool"

        # Step 2: ToolResult (validate) -> ToolCall (transform)
        tool_result1.step()
        assert isinstance(stack.interactions[-1], ToolCall)
        tool_call2 = stack.interactions[-1]
        assert tool_call2.tool == "transform_tool"
        assert tool_call2.tool_call_id == "oracle_call_1"  # Inherits from chain

        # Step 3: ToolCall -> ToolResult (transform)
        tool_call2.step()
        assert isinstance(stack.interactions[-1], ToolResult)
        tool_result2 = stack.interactions[-1]
        assert tool_result2.next_tool == "store_tool"

        # Step 4: ToolResult (transform) -> ToolCall (store)
        tool_result2.step()
        assert isinstance(stack.interactions[-1], ToolCall)
        tool_call3 = stack.interactions[-1]
        assert tool_call3.tool == "store_tool"

        # Step 5: ToolCall -> ToolResult (store, end of chain)
        tool_call3.step()
        assert isinstance(stack.interactions[-1], ToolResult)
        tool_result3 = stack.interactions[-1]
        assert tool_result3.next_tool is None  # End of chain

        # Step 6: ToolResult (store) -> AskOracle (back to LLM)
        tool_result3.step()
        assert isinstance(stack.interactions[-1], AskOracle)


class TestIncludeInContext:
    """Test include_in_context filtering."""

    def test_ask_oracle_include_in_context_true(self, mock_agent):
        """Test that AskOracle with include_in_context=True is included."""
        stack = mock_agent.stack

        task = Task(
            name="test",
            description="Test",
            parameters={},
            prompt="Test",
            tools=[],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Add AskOracle with include_in_context=True (default)
        prompt = Prompt(type="text", text="Visible prompt content")
        ask_oracle = AskOracle(
            stack=stack,
            prompt=prompt,
            template_inputs={},
            include_in_context=True,
        )
        stack.add_interaction(ask_oracle)

        # Should be included in context
        context = stack.render_stack_context()
        assert len(context) > 0
        assert any(
            "Visible prompt content" in str(msg.get("content", ""))
            for msg in context
        )

    def test_ask_oracle_include_in_context_false(self, mock_agent):
        """Test that AskOracle with include_in_context=False is filtered."""
        stack = mock_agent.stack

        task = Task(
            name="test",
            description="Test",
            parameters={},
            prompt="Test",
            tools=[],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Add AskOracle with include_in_context=False
        prompt = Prompt(type="text", text="Hidden prompt content")
        ask_oracle = AskOracle(
            stack=stack,
            prompt=prompt,
            template_inputs={},
            include_in_context=False,
        )
        stack.add_interaction(ask_oracle)

        # Should NOT be included in context
        context = stack.render_stack_context()
        for msg in context:
            assert "Hidden prompt content" not in str(msg.get("content", ""))

    def test_tool_result_include_in_context_field(self, mock_agent):
        """Test that ToolResult has include_in_context field."""
        stack = mock_agent.stack

        # Create ToolResult with include_in_context=False
        tool_result = ToolResult(
            stack=stack,
            result={"data": "hidden"},
            tool_call_id="call_hidden",
            tool_name="hidden_tool",
            is_error=False,
            include_in_context=False,
        )

        assert tool_result.include_in_context is False

        # Create ToolResult with default (True)
        tool_result_default = ToolResult(
            stack=stack,
            result={"data": "visible"},
            tool_call_id="call_visible",
            tool_name="visible_tool",
            is_error=False,
        )

        assert tool_result_default.include_in_context is True


# =============================================================================
# Level 2: Task Chaining Tests
# =============================================================================


class TestTaskChainingFields:
    """Test Task chaining field serialization."""

    def test_task_with_next_task(self):
        """Test Task with next_task field."""
        task = Task(
            name="first_task",
            description="First task",
            parameters={},
            prompt="Do first thing",
            next_task="second_task",
            pass_result_as="first_result",
        )

        assert task.next_task == "second_task"
        assert task.pass_result_as == "first_result"

    def test_task_with_task_sequence(self):
        """Test Task with task_sequence field."""
        task = Task(
            name="pipeline",
            description="Pipeline task",
            parameters={},
            prompt="Run pipeline",
            task_sequence=["step1", "step2", "step3"],
        )

        assert task.task_sequence == ["step1", "step2", "step3"]

    def test_task_from_dict_with_chaining(self):
        """Test Task.from_dict preserves chaining fields."""
        data = {
            "name": "chained_task",
            "description": "A chained task",
            "parameters": {
                "input": {
                    "type": "string",
                    "description": "",
                    "required": False,
                    "default": "value",
                }
            },
            "prompt": "Do something",
            "next_task": "next_one",
            "task_sequence": ["a", "b", "c"],
            "pass_result_as": "prev_result",
            "chain_config": "special_config",
        }

        task = Task.from_dict(data)

        assert task.next_task == "next_one"
        assert task.task_sequence == ["a", "b", "c"]
        assert task.pass_result_as == "prev_result"
        assert task.chain_config == "special_config"


class TestTaskChainInteraction:
    """Test TaskChain interaction."""

    def test_task_chain_creation(self, mock_agent):
        """Test creating TaskChain interaction."""
        stack = mock_agent.stack

        task_chain = TaskChain(
            stack=stack,
            next_task_name="next_task",
            previous_result={"data": "from_previous"},
            sequence_index=0,
        )

        assert task_chain.next_task_name == "next_task"
        assert task_chain.previous_result == {"data": "from_previous"}
        assert task_chain.sequence_index == 0

    def test_task_chain_with_sequence(self, mock_agent):
        """Test TaskChain with task sequence."""
        stack = mock_agent.stack

        task_chain = TaskChain(
            stack=stack,
            task_sequence=["task1", "task2", "task3"],
            sequence_index=1,
            previous_result={"step": "complete"},
        )

        assert task_chain.task_sequence == ["task1", "task2", "task3"]
        assert task_chain.sequence_index == 1

    def test_task_chain_from_dict(self, mock_agent):
        """Test TaskChain deserialization."""
        stack = mock_agent.stack

        data = {
            "uuid": "test-uuid-123",
            "next_task_name": "chained_task",
            "task_sequence": ["a", "b"],
            "sequence_index": 1,
            "previous_result": {"key": "value"},
            "chain_config": "alt_config",
        }

        task_chain = TaskChain._from_dict(data, stack=stack, artifacts=[])

        assert task_chain.next_task_name == "chained_task"
        assert task_chain.task_sequence == ["a", "b"]
        assert task_chain.sequence_index == 1
        assert task_chain.previous_result == {"key": "value"}
        assert task_chain.chain_config == "alt_config"


class TestTaskResultChaining:
    """Test TaskResult triggering task chains."""

    def test_task_result_with_next_task(self, mock_agent):
        """Test TaskResult creates TaskChain when next_task is set."""
        stack = mock_agent.stack

        # Create task with next_task
        task = Task(
            name="first",
            description="First task",
            parameters={},
            prompt="Do first",
            next_task="second",
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Register the next task in environment
        second_task = Task(
            name="second",
            description="Second task",
            parameters={},
            prompt="Do second",
        )
        mock_agent.environment.task_registry.register(second_task)

        try:
            # Create TaskResult
            task_result = TaskResult(
                stack=stack,
                result={"data": "first_output"},
                finish_type="success",
            )
            stack.add_interaction(task_result)

            # Step should create TaskChain
            result = task_result.step()

            assert result is True
            new_interaction = stack.interactions[-1]
            assert isinstance(new_interaction, TaskChain)
            assert new_interaction.next_task_name == "second"
            assert new_interaction.previous_result == {"data": "first_output"}
        finally:
            mock_agent.environment.task_registry.remove("second")

    def test_task_result_with_task_sequence(self, mock_agent):
        """Test TaskResult with task_sequence creates TaskChain."""
        stack = mock_agent.stack

        # Create task with task_sequence
        task = Task(
            name="pipeline",
            description="Pipeline",
            parameters={
                "_chain_sequence_index": {
                    "type": "integer",
                    "description": "Internal: task sequence index",
                    "required": False,
                    "default": 0,
                    "value": 0,
                }
            },
            prompt="Run pipeline",
            task_sequence=["step1", "step2", "step3"],
        )
        task_def = TaskDefinition(stack=stack, task=task)
        stack.add_interaction(task_def)

        # Register sequence tasks
        for i in range(1, 4):
            step_task = Task(
                name=f"step{i}",
                description=f"Step {i}",
                parameters={},
                prompt=f"Do step {i}",
            )
            mock_agent.environment.task_registry.register(step_task)

        try:
            # Create TaskResult
            task_result = TaskResult(
                stack=stack,
                result={"step": 1},
                finish_type="success",
            )
            stack.add_interaction(task_result)

            result = task_result.step()

            assert result is True
            new_interaction = stack.interactions[-1]
            assert isinstance(new_interaction, TaskChain)
            assert new_interaction.task_sequence == ["step1", "step2", "step3"]
            assert new_interaction.sequence_index == 1  # Next index
        finally:
            for i in range(1, 4):
                mock_agent.environment.task_registry.remove(f"step{i}")


# =============================================================================
# Level 3: Config State Machine Tests
# =============================================================================


class TestTransitionTrigger:
    """Test TransitionTrigger dataclass."""

    def test_tool_call_trigger(self):
        """Test tool_call trigger creation."""
        trigger = TransitionTrigger(
            type="tool_call",
            tool_name="approve_plan",
        )

        assert trigger.type == "tool_call"
        assert trigger.tool_name == "approve_plan"

    def test_step_count_trigger(self):
        """Test step_count trigger creation."""
        trigger = TransitionTrigger(
            type="step_count",
            min_steps=10,
        )

        assert trigger.type == "step_count"
        assert trigger.min_steps == 10

    def test_state_pattern_trigger(self):
        """Test state_pattern trigger creation."""
        trigger = TransitionTrigger(
            type="state_pattern",
            pattern={"blocked": True, "retries": {"$gte": 3}},
        )

        assert trigger.type == "state_pattern"
        assert trigger.pattern == {"blocked": True, "retries": {"$gte": 3}}

    def test_trigger_serialization(self):
        """Test trigger to_dict and from_dict."""
        original = TransitionTrigger(
            type="tool_call",
            tool_name="finish",
        )

        data = original.to_dict()
        restored = TransitionTrigger.from_dict(data)

        assert restored.type == original.type
        assert restored.tool_name == original.tool_name


class TestConfigTransition:
    """Test ConfigTransition dataclass."""

    def test_transition_creation(self):
        """Test creating a config transition."""
        trigger = TransitionTrigger(type="tool_call", tool_name="start_exec")
        transition = ConfigTransition(
            name="plan_to_exec",
            from_state="planning_mode",
            to_state="execution_mode",
            trigger=trigger,
            priority=10,
        )

        assert transition.name == "plan_to_exec"
        assert transition.from_state == "planning_mode"
        assert transition.to_state == "execution_mode"
        assert transition.priority == 10

    def test_transition_wildcard_from_state(self):
        """Test transition with wildcard from_state."""
        trigger = TransitionTrigger(type="step_count", min_steps=100)
        transition = ConfigTransition(
            name="timeout",
            from_state="*",
            to_state="summary_mode",
            trigger=trigger,
        )

        assert transition.from_state == "*"

    def test_transition_serialization(self):
        """Test transition to_dict and from_dict."""
        original = ConfigTransition(
            name="test_transition",
            from_state="state_a",
            to_state="state_b",
            trigger=TransitionTrigger(type="tool_call", tool_name="switch"),
            priority=5,
        )

        data = original.to_dict()
        restored = ConfigTransition.from_dict(data)

        assert restored.name == original.name
        assert restored.from_state == original.from_state
        assert restored.to_state == original.to_state
        assert restored.trigger.type == original.trigger.type
        assert restored.priority == original.priority


class TestConfigStateMachine:
    """Test ConfigStateMachine dataclass."""

    def test_state_machine_creation(self):
        """Test creating a state machine."""
        transitions = [
            ConfigTransition(
                name="start",
                from_state="init",
                to_state="running",
                trigger=TransitionTrigger(type="tool_call", tool_name="begin"),
                priority=10,
            ),
            ConfigTransition(
                name="finish",
                from_state="running",
                to_state="done",
                trigger=TransitionTrigger(type="tool_call", tool_name="end"),
                priority=5,
            ),
        ]

        sm = ConfigStateMachine(
            initial_state="init",
            transitions=transitions,
            on_no_match="stay",
        )

        assert sm.initial_state == "init"
        assert len(sm.transitions) == 2
        assert sm.on_no_match == "stay"

    def test_get_transitions_by_priority(self):
        """Test transitions are sorted by priority."""
        transitions = [
            ConfigTransition(
                name="low",
                from_state="*",
                to_state="a",
                trigger=TransitionTrigger(type="step_count", min_steps=1),
                priority=1,
            ),
            ConfigTransition(
                name="high",
                from_state="*",
                to_state="b",
                trigger=TransitionTrigger(type="step_count", min_steps=1),
                priority=10,
            ),
            ConfigTransition(
                name="medium",
                from_state="*",
                to_state="c",
                trigger=TransitionTrigger(type="step_count", min_steps=1),
                priority=5,
            ),
        ]

        sm = ConfigStateMachine(initial_state="start", transitions=transitions)
        sorted_transitions = sm.get_transitions_by_priority()

        assert sorted_transitions[0].name == "high"
        assert sorted_transitions[1].name == "medium"
        assert sorted_transitions[2].name == "low"

    def test_state_machine_serialization(self):
        """Test state machine to_dict and from_dict."""
        original = ConfigStateMachine(
            initial_state="planning",
            transitions=[
                ConfigTransition(
                    name="approve",
                    from_state="planning",
                    to_state="executing",
                    trigger=TransitionTrigger(
                        type="tool_call", tool_name="approve"
                    ),
                ),
            ],
            on_no_match="error",
        )

        data = original.to_dict()
        restored = ConfigStateMachine.from_dict(data)

        assert restored.initial_state == original.initial_state
        assert len(restored.transitions) == len(original.transitions)
        assert restored.on_no_match == original.on_no_match


class TestConfigWithStateMachine:
    """Test Config with state_machine field."""

    def test_config_with_state_machine(self):
        """Test creating Config with state_machine."""
        sm = ConfigStateMachine(
            initial_state="mode_a",
            transitions=[
                ConfigTransition(
                    name="switch",
                    from_state="mode_a",
                    to_state="mode_b",
                    trigger=TransitionTrigger(
                        type="tool_call", tool_name="switch"
                    ),
                ),
            ],
        )

        config = Config(
            name="test_config",
            description="Test",
            llm_model="test-model",
            system_template="system",
            state_machine=sm,
        )

        assert config.state_machine is not None
        assert config.state_machine.initial_state == "mode_a"

    def test_config_from_dict_with_state_machine(self):
        """Test Config.from_dict parses state_machine."""
        data = {
            "name": "sm_config",
            "description": "Config with state machine",
            "llm_model": "model",
            "system_template": "system",
            "state_machine": {
                "initial_state": "planning",
                "transitions": [
                    {
                        "name": "execute",
                        "from_state": "planning",
                        "to_state": "executing",
                        "trigger": {"type": "tool_call", "tool_name": "start"},
                    }
                ],
                "on_no_match": "stay",
            },
        }

        config = Config.from_dict(data)

        assert config.state_machine is not None
        assert config.state_machine.initial_state == "planning"
        assert len(config.state_machine.transitions) == 1


class TestAgentStateMachineTransitions:
    """Test Agent state machine transitions."""

    @pytest.fixture
    def state_machine_session(self, mock_session):
        """Create a session with state configs."""
        # Register mode configs
        planning_config = Config(
            name="planning_mode",
            description="Planning mode",
            llm_model="test-model",
            system_template="planning_template",
            tools=["analyze", "create_plan", "approve_plan"],
        )

        execution_config = Config(
            name="execution_mode",
            description="Execution mode",
            llm_model="test-model",
            system_template="execution_template",
            tools=["execute", "complete"],
        )

        mock_session.environment.config_registry.register(planning_config)
        mock_session.environment.config_registry.register(execution_config)

        yield mock_session

        mock_session.environment.config_registry.remove("planning_mode")
        mock_session.environment.config_registry.remove("execution_mode")

    def test_agent_initial_state(self, state_machine_session):
        """Test agent starts in initial state."""
        sm = ConfigStateMachine(
            initial_state="planning_mode",
            transitions=[],
        )

        main_config = Config(
            name="main",
            description="Main config",
            llm_model="test-model",
            system_template="system",
            state_machine=sm,
        )

        agent = Agent(session=state_machine_session, config=main_config)

        assert agent.current_state == "planning_mode"
        # Agent should have loaded the planning_mode config
        assert agent.config.name == "planning_mode"

    def test_agent_tool_call_transition(self, state_machine_session):
        """Test agent transitions on tool call trigger."""
        sm = ConfigStateMachine(
            initial_state="planning_mode",
            transitions=[
                ConfigTransition(
                    name="start_execution",
                    from_state="planning_mode",
                    to_state="execution_mode",
                    trigger=TransitionTrigger(
                        type="tool_call", tool_name="approve"
                    ),
                ),
            ],
        )

        main_config = Config(
            name="main",
            description="Main config",
            llm_model="test-model",
            system_template="system",
            state_machine=sm,
        )

        agent = Agent(session=state_machine_session, config=main_config)

        # Simulate a tool call and result for "approve"
        tool_call = ToolCall(
            stack=agent.stack,
            tool="approve",
            args={},
            tool_call_id="call_1",
        )
        agent.stack.add_interaction(tool_call)

        tool_result = ToolResult(
            stack=agent.stack,
            result={"status": "approved"},
            tool_call_id="call_1",
            tool_name="approve",
            is_error=False,
        )
        agent.stack.add_interaction(tool_result)

        # Mock the step to not fail on tool execution
        with patch.object(agent.stack, "step", return_value=True):
            agent.step()

        # Should have transitioned
        assert agent.current_state == "execution_mode"
        assert agent.config.name == "execution_mode"

    def test_agent_step_count_transition(self, state_machine_session):
        """Test agent transitions after step count threshold."""
        sm = ConfigStateMachine(
            initial_state="planning_mode",
            transitions=[
                ConfigTransition(
                    name="timeout",
                    from_state="planning_mode",
                    to_state="execution_mode",
                    trigger=TransitionTrigger(type="step_count", min_steps=3),
                ),
            ],
        )

        main_config = Config(
            name="main",
            description="Main config",
            llm_model="test-model",
            system_template="system",
            state_machine=sm,
        )

        agent = Agent(session=state_machine_session, config=main_config)

        # Take steps
        with patch.object(agent.stack, "step", return_value=True):
            agent.stack.add_interaction(Mock())
            agent.step()  # step 1
            assert agent.current_state == "planning_mode"

            agent.stack.add_interaction(Mock())
            agent.step()  # step 2
            assert agent.current_state == "planning_mode"

            agent.stack.add_interaction(Mock())  # step 3
            agent.step()  # step 3 - should transition
            assert agent.stack.ninteractions() == 3
            assert agent.current_state == "execution_mode"

    def test_agent_state_pattern_transition(self, state_machine_session):
        """Test agent transitions on state pattern match."""
        sm = ConfigStateMachine(
            initial_state="planning_mode",
            transitions=[
                ConfigTransition(
                    name="blocked_replan",
                    from_state="planning_mode",
                    to_state="execution_mode",
                    trigger=TransitionTrigger(
                        type="state_pattern",
                        pattern={"blocked": True},
                    ),
                ),
            ],
        )

        main_config = Config(
            name="main",
            description="Main config",
            llm_model="test-model",
            system_template="system",
            state_machine=sm,
        )

        agent = Agent(session=state_machine_session, config=main_config)

        # Set shared state
        agent.stack.set_shared_state("blocked", True)

        with patch.object(agent.stack, "step", return_value=True):
            agent.step()

        assert agent.current_state == "execution_mode"

    def test_agent_pattern_operators(self, state_machine_session):
        """Test state pattern with comparison operators."""
        sm = ConfigStateMachine(
            initial_state="planning_mode",
            transitions=[
                ConfigTransition(
                    name="high_retries",
                    from_state="planning_mode",
                    to_state="execution_mode",
                    trigger=TransitionTrigger(
                        type="state_pattern",
                        pattern={"retries": {"$gte": 3}},
                    ),
                ),
            ],
        )

        main_config = Config(
            name="main",
            description="Main config",
            llm_model="test-model",
            system_template="system",
            state_machine=sm,
        )

        agent = Agent(session=state_machine_session, config=main_config)

        # Set retries below threshold
        agent.stack.set_shared_state("retries", 2)
        with patch.object(agent.stack, "step", return_value=True):
            agent.step()
        assert agent.current_state == "planning_mode"

        # Set retries at threshold
        agent.stack.set_shared_state("retries", 3)
        with patch.object(agent.stack, "step", return_value=True):
            agent.step()
        assert agent.current_state == "execution_mode"

    def test_agent_transition_loop(self, state_machine_session):
        """Test agent can loop between states."""
        sm = ConfigStateMachine(
            initial_state="planning_mode",
            transitions=[
                ConfigTransition(
                    name="to_execution",
                    from_state="planning_mode",
                    to_state="execution_mode",
                    trigger=TransitionTrigger(
                        type="tool_call", tool_name="approve"
                    ),
                ),
                ConfigTransition(
                    name="back_to_planning",
                    from_state="execution_mode",
                    to_state="planning_mode",
                    trigger=TransitionTrigger(
                        type="tool_call", tool_name="replan"
                    ),
                ),
            ],
        )

        main_config = Config(
            name="main",
            description="Main config",
            llm_model="test-model",
            system_template="system",
            state_machine=sm,
        )

        agent = Agent(session=state_machine_session, config=main_config)
        assert agent.current_state == "planning_mode"

        # Transition to execution
        tool_call = ToolCall(stack=agent.stack, tool="approve", args={})
        agent.stack.add_interaction(tool_call)
        tool_result = ToolResult(
            stack=agent.stack,
            result={"status": "approved"},
            tool_call_id="call_1",
            tool_name="approve",
            is_error=False,
        )
        agent.stack.add_interaction(tool_result)
        with patch.object(agent.stack, "step", return_value=True):
            agent.step()
        assert agent.current_state == "execution_mode"

        # Transition back to planning
        tool_call2 = ToolCall(stack=agent.stack, tool="replan", args={})
        agent.stack.add_interaction(tool_call2)
        tool_result2 = ToolResult(
            stack=agent.stack,
            result={"status": "replanned"},
            tool_call_id="call_2",
            tool_name="replan",
            is_error=False,
        )
        agent.stack.add_interaction(tool_result2)
        with patch.object(agent.stack, "step", return_value=True):
            agent.step()
        assert agent.current_state == "planning_mode"


class TestAgentStateMachineSerialization:
    """Test Agent state machine serialization."""

    def test_agent_to_dict_includes_state_machine(self, mock_session):
        """Test agent serialization includes state machine state."""
        sm = ConfigStateMachine(
            initial_state="mode_a",
            transitions=[],
        )

        # Register the config
        mode_config = Config(
            name="mode_a",
            description="Mode A",
            llm_model="test-model",
            system_template="system",
        )
        mock_session.environment.config_registry.register(mode_config)

        try:
            config = Config(
                name="main",
                description="Main",
                llm_model="test-model",
                system_template="system",
                state_machine=sm,
            )

            agent = Agent(session=mock_session, config=config)

            data = agent.to_dict()

            assert data["_current_state"] == "mode_a"
            assert "_state_machine" in data
            assert data["_state_machine"]["initial_state"] == "mode_a"
        finally:
            mock_session.environment.config_registry.remove("mode_a")

    def test_agent_from_dict_restores_state_machine(self, mock_session):
        """Test agent deserialization restores state machine state."""
        # Register the config
        mode_config = Config(
            name="mode_b",
            description="Mode B",
            llm_model="test-model",
            system_template="system",
        )
        mock_session.environment.config_registry.register(mode_config)

        try:
            data = {
                "uuid": "test-agent-uuid",
                "config": {
                    "name": "mode_b",
                    "description": "Test",
                    "llm_model": "test-model",
                    "system_template": "system",
                },
                "stack": {"interactions": []},
                "_current_state": "mode_b",
                "_state_machine": {
                    "initial_state": "mode_a",
                    "transitions": [],
                    "on_no_match": "stay",
                },
            }

            agent = Agent.from_dict(
                data, storage=mock_session.storage, session=mock_session
            )

            assert agent._current_state == "mode_b"
            assert agent._state_machine is not None
            assert agent._state_machine.initial_state == "mode_a"
        finally:
            mock_session.environment.config_registry.remove("mode_b")


class TestConfigHistory:
    """Test config state machine history tracking."""

    @pytest.fixture
    def state_machine_session(self, mock_session):
        """Create a session with state configs."""
        planning_config = Config(
            name="planning_mode",
            description="Planning mode",
            llm_model="test-model",
            system_template="planning_template",
            tools=["analyze", "create_plan", "approve_plan"],
        )

        execution_config = Config(
            name="execution_mode",
            description="Execution mode",
            llm_model="test-model",
            system_template="execution_template",
            tools=["execute", "complete"],
        )

        mock_session.environment.config_registry.register(planning_config)
        mock_session.environment.config_registry.register(execution_config)

        yield mock_session

        mock_session.environment.config_registry.remove("planning_mode")
        mock_session.environment.config_registry.remove("execution_mode")

    def test_config_history_initial_state(self, state_machine_session):
        """Agent with state machine has one history entry after init."""
        sm = ConfigStateMachine(
            initial_state="planning_mode",
            transitions=[],
        )
        main_config = Config(
            name="main",
            description="Main config",
            llm_model="test-model",
            system_template="system",
            state_machine=sm,
        )

        agent = Agent(session=state_machine_session, config=main_config)

        assert len(agent.config_history) == 1
        entry = agent.config_history[0]
        assert entry["state"] == "planning_mode"
        assert entry["interaction_id"] is None
        assert "timestamp" in entry

    def test_config_history_after_transition(self, state_machine_session):
        """After a transition, history has 2 entries with correct IDs."""
        sm = ConfigStateMachine(
            initial_state="planning_mode",
            transitions=[
                ConfigTransition(
                    name="start_execution",
                    from_state="planning_mode",
                    to_state="execution_mode",
                    trigger=TransitionTrigger(
                        type="tool_call", tool_name="approve"
                    ),
                ),
            ],
        )
        main_config = Config(
            name="main",
            description="Main config",
            llm_model="test-model",
            system_template="system",
            state_machine=sm,
        )

        agent = Agent(session=state_machine_session, config=main_config)

        # Add tool call and result for "approve"
        tool_call = ToolCall(
            stack=agent.stack,
            tool="approve",
            args={},
            tool_call_id="call_1",
        )
        agent.stack.add_interaction(tool_call)

        tool_result = ToolResult(
            stack=agent.stack,
            result={"status": "approved"},
            tool_call_id="call_1",
            tool_name="approve",
            is_error=False,
        )
        agent.stack.add_interaction(tool_result)

        with patch.object(agent.stack, "step", return_value=True):
            agent.step()

        assert len(agent.config_history) == 2
        assert agent.config_history[0]["state"] == "planning_mode"
        assert agent.config_history[0]["interaction_id"] is None
        assert agent.config_history[1]["state"] == "execution_mode"
        # The triggering interaction is the ToolResult (last on stack)
        assert agent.config_history[1]["interaction_id"] == str(
            tool_result.uuid
        )

    def test_config_history_multiple_transitions(self, state_machine_session):
        """After multiple transitions, history has correct sequence."""
        sm = ConfigStateMachine(
            initial_state="planning_mode",
            transitions=[
                ConfigTransition(
                    name="to_execution",
                    from_state="planning_mode",
                    to_state="execution_mode",
                    trigger=TransitionTrigger(
                        type="tool_call", tool_name="approve"
                    ),
                ),
                ConfigTransition(
                    name="back_to_planning",
                    from_state="execution_mode",
                    to_state="planning_mode",
                    trigger=TransitionTrigger(
                        type="tool_call", tool_name="replan"
                    ),
                ),
            ],
        )
        main_config = Config(
            name="main",
            description="Main config",
            llm_model="test-model",
            system_template="system",
            state_machine=sm,
        )

        agent = Agent(session=state_machine_session, config=main_config)
        assert len(agent.config_history) == 1

        # First transition: planning -> execution
        tc1 = ToolCall(
            stack=agent.stack,
            tool="approve",
            args={},
        )
        agent.stack.add_interaction(tc1)
        tr1 = ToolResult(
            stack=agent.stack,
            result={},
            tool_call_id="c1",
            tool_name="approve",
            is_error=False,
        )
        agent.stack.add_interaction(tr1)
        with patch.object(agent.stack, "step", return_value=True):
            agent.step()

        assert len(agent.config_history) == 2

        # Second transition: execution -> planning
        tc2 = ToolCall(
            stack=agent.stack,
            tool="replan",
            args={},
        )
        agent.stack.add_interaction(tc2)
        tr2 = ToolResult(
            stack=agent.stack,
            result={},
            tool_call_id="c2",
            tool_name="replan",
            is_error=False,
        )
        agent.stack.add_interaction(tr2)
        with patch.object(agent.stack, "step", return_value=True):
            agent.step()

        assert len(agent.config_history) == 3
        states = [e["state"] for e in agent.config_history]
        assert states == [
            "planning_mode",
            "execution_mode",
            "planning_mode",
        ]

    def test_config_history_serialization(self, state_machine_session):
        """to_dict/from_dict round-trips config history."""
        sm = ConfigStateMachine(
            initial_state="planning_mode",
            transitions=[
                ConfigTransition(
                    name="to_exec",
                    from_state="planning_mode",
                    to_state="execution_mode",
                    trigger=TransitionTrigger(
                        type="tool_call", tool_name="approve"
                    ),
                ),
            ],
        )
        main_config = Config(
            name="main",
            description="Main config",
            llm_model="test-model",
            system_template="system",
            state_machine=sm,
        )

        agent = Agent(session=state_machine_session, config=main_config)

        # Trigger a transition
        tc = ToolCall(
            stack=agent.stack,
            tool="approve",
            args={},
            tool_call_id="c1",
        )
        agent.stack.add_interaction(tc)
        tr = ToolResult(
            stack=agent.stack,
            result={},
            tool_call_id="c1",
            tool_name="approve",
            is_error=False,
        )
        agent.stack.add_interaction(tr)
        with patch.object(agent.stack, "step", return_value=True):
            agent.step()

        # Serialize
        data = agent.to_dict()
        assert "_config_history" in data
        assert len(data["_config_history"]) == 2

        # Deserialize
        restored = Agent.from_dict(
            data,
            storage=state_machine_session.storage,
            session=state_machine_session,
        )
        assert restored.config_history == agent.config_history
        assert len(restored.config_history) == 2
        assert restored.config_history[0]["state"] == "planning_mode"
        assert restored.config_history[1]["state"] == "execution_mode"

    def test_config_history_empty_without_state_machine(self, mock_session):
        """Agent without state machine has empty config history."""
        config = Config(
            name="simple",
            description="No state machine",
            llm_model="test-model",
            system_template="system",
        )
        agent = Agent(session=mock_session, config=config)

        assert agent.config_history == []
