"""Tests for Waiting interaction and Condition class."""

from unittest.mock import MagicMock

import pytest

from gimle.hugin.agent.config import Config
from gimle.hugin.agent.session_state import SessionState
from gimle.hugin.agent.task import Task
from gimle.hugin.interaction.conditions import (
    Condition,
    all_branches_complete,
    wait_for_ticks,
)
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.interaction.tool_call import ToolCall
from gimle.hugin.interaction.waiting import Waiting


@pytest.fixture
def mock_session():
    """Create a mock session."""
    session = MagicMock()
    session.environment = MagicMock()
    session.environment.config_registry = MagicMock()
    session.environment.task_registry = MagicMock()
    session.environment.template_registry = MagicMock()
    session.environment.template_registry.registered.return_value = {}
    return session


@pytest.fixture
def mock_agent(mock_session):
    """Create a mock agent with stack."""
    from gimle.hugin.agent.agent import Agent

    config = Config(
        name="test_config",
        description="Test config",
        system_template="test_system",
        tools=[],
    )
    agent = Agent(config=config, session=mock_session)
    return agent


@pytest.fixture
def mock_session_with_state(mock_session):
    """Extend mock_session with a real SessionState."""
    mock_session.state = SessionState()
    return mock_session


@pytest.fixture
def mock_agent_with_state(mock_session_with_state):
    """Create a mock agent with real SessionState for shared state tests."""
    from gimle.hugin.agent.agent import Agent

    config = Config(
        name="test_config",
        description="Test config",
        system_template="test_system",
        tools=[],
    )
    agent = Agent(config=config, session=mock_session_with_state)
    return agent


class TestCondition:
    """Tests for the Condition class."""

    def test_condition_register_decorator(self):
        """Test registering a condition function with the decorator."""
        # Clean up any existing registration
        if "test_condition_func" in Condition.registry.registered():
            Condition.registry.remove("test_condition_func")

        @Condition.register()
        def test_condition_func(stack, branch):
            return True

        assert "test_condition_func" in Condition.registry.registered()

        # Cleanup
        Condition.registry.remove("test_condition_func")

    def test_condition_to_dict(self):
        """Test serializing a condition to dict."""
        condition = Condition(
            evaluator="my_evaluator",
            parameters={"key": "value", "count": 3},
        )

        result = condition.to_dict()

        assert result == {
            "evaluator": "my_evaluator",
            "parameters": {"key": "value", "count": 3},
        }

    def test_condition_from_dict(self):
        """Test deserializing a condition from dict."""
        data = {
            "evaluator": "my_evaluator",
            "parameters": {"key": "value"},
        }

        condition = Condition.from_dict(data)

        assert condition.evaluator == "my_evaluator"
        assert condition.parameters == {"key": "value"}

    def test_condition_evaluate_without_parameters(self, mock_agent):
        """Test evaluating a condition without extra parameters."""
        # Register a test condition
        if "simple_condition" in Condition.registry.registered():
            Condition.registry.remove("simple_condition")

        @Condition.register()
        def simple_condition(stack, branch):
            return stack is not None and branch == "test_branch"

        try:
            condition = Condition(evaluator="simple_condition")

            # Should return True when branch matches
            result = condition.evaluate(mock_agent.stack, "test_branch")
            assert result is True

            # Should return False when branch doesn't match
            result = condition.evaluate(mock_agent.stack, "other_branch")
            assert result is False
        finally:
            Condition.registry.remove("simple_condition")

    def test_condition_evaluate_with_parameters(self, mock_agent):
        """Test evaluating a condition with extra parameters."""
        if "param_condition" in Condition.registry.registered():
            Condition.registry.remove("param_condition")

        @Condition.register()
        def param_condition(stack, branch, threshold=5):
            # Return True if branch name length exceeds threshold
            return branch is not None and len(branch) > threshold

        try:
            # With default threshold (5)
            condition = Condition(
                evaluator="param_condition",
                parameters={"threshold": 3},
            )

            result = condition.evaluate(mock_agent.stack, "test")  # len=4 > 3
            assert result is True

            result = condition.evaluate(mock_agent.stack, "ab")  # len=2 <= 3
            assert result is False
        finally:
            Condition.registry.remove("param_condition")

    def test_condition_evaluate_missing_evaluator(self, mock_agent):
        """Test that evaluating with missing evaluator raises error."""
        condition = Condition(evaluator="nonexistent_evaluator")

        with pytest.raises(ValueError, match="not found"):
            condition.evaluate(mock_agent.stack, None)


class TestAllBranchesComplete:
    """Tests for the all_branches_complete condition function."""

    def test_all_branches_complete_empty_list(self, mock_agent):
        """Test with empty branches list returns False (done waiting)."""
        # No branches to check = all complete = done waiting = False
        result = all_branches_complete([], mock_agent.stack, None)
        assert result is False

    def test_all_branches_complete_all_complete(self, mock_agent):
        """Test returns False (done waiting) when all branches are complete."""
        # Add a TaskDefinition to make the stack valid
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Test prompt",
        )
        task_def = TaskDefinition(stack=mock_agent.stack, task=task)
        mock_agent.stack.add_interaction(task_def)

        # Create branches with Waiting (complete state)
        for branch_name in ["branch_1", "branch_2"]:
            branch_task_def = TaskDefinition(
                stack=mock_agent.stack,
                task=task,
                branch=branch_name,
            )
            mock_agent.stack.add_interaction(
                branch_task_def, branch=branch_name
            )
            waiting = Waiting(stack=mock_agent.stack, branch=branch_name)
            mock_agent.stack.add_interaction(waiting, branch=branch_name)

        # All branches complete = done waiting = False
        result = all_branches_complete(
            ["branch_1", "branch_2"], mock_agent.stack, None
        )
        assert result is False

    def test_all_branches_complete_some_incomplete(self, mock_agent):
        """Test returns True (still waiting) when some branches not complete."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Test prompt",
        )
        task_def = TaskDefinition(stack=mock_agent.stack, task=task)
        mock_agent.stack.add_interaction(task_def)

        # Create one complete branch
        branch_task_def = TaskDefinition(
            stack=mock_agent.stack,
            task=task,
            branch="complete_branch",
        )
        mock_agent.stack.add_interaction(
            branch_task_def, branch="complete_branch"
        )
        waiting = Waiting(stack=mock_agent.stack, branch="complete_branch")
        mock_agent.stack.add_interaction(waiting, branch="complete_branch")

        # Create one incomplete branch (just TaskDefinition, no Waiting)
        incomplete_task_def = TaskDefinition(
            stack=mock_agent.stack,
            task=task,
            branch="incomplete_branch",
        )
        mock_agent.stack.add_interaction(
            incomplete_task_def, branch="incomplete_branch"
        )

        # Some branches incomplete = still waiting = True
        result = all_branches_complete(
            ["complete_branch", "incomplete_branch"], mock_agent.stack, None
        )
        assert result is True


class TestWaiting:
    """Tests for the Waiting interaction."""

    def test_waiting_no_condition_is_terminal(self, mock_agent):
        """Test that Waiting without condition is terminal (returns False)."""
        waiting = Waiting(stack=mock_agent.stack)

        result = waiting.step()

        assert result is False

    def test_waiting_condition_still_waiting(self, mock_agent):
        """Test that Waiting returns True when condition returns True (still waiting)."""
        # Register a condition that always returns True (still waiting)
        if "always_waiting" in Condition.registry.registered():
            Condition.registry.remove("always_waiting")

        @Condition.register()
        def always_waiting(stack, branch):
            return True  # Still waiting

        try:
            condition = Condition(evaluator="always_waiting")
            waiting = Waiting(
                stack=mock_agent.stack,
                condition=condition,
                next_tool="some_tool",
            )

            result = waiting.step()

            # Returns True to indicate "continue stepping"
            assert result is True
            # Should not have added any interactions (not chaining to tool yet)
            assert len(mock_agent.stack.interactions) == 0
        finally:
            Condition.registry.remove("always_waiting")

    def test_waiting_condition_done_chains_to_tool(self, mock_agent):
        """Test that Waiting chains to next_tool when condition returns False."""
        # Register a condition that returns False (done waiting)
        if "done_waiting" in Condition.registry.registered():
            Condition.registry.remove("done_waiting")

        @Condition.register()
        def done_waiting(stack, branch):
            return False  # Done waiting

        try:
            condition = Condition(evaluator="done_waiting")
            waiting = Waiting(
                stack=mock_agent.stack,
                condition=condition,
                next_tool="aggregate_results",
                next_tool_args={"key": "value"},
            )

            result = waiting.step()

            assert result is True
            # Should have added a ToolCall
            assert len(mock_agent.stack.interactions) == 1
            tool_call = mock_agent.stack.interactions[0]
            assert isinstance(tool_call, ToolCall)
            assert tool_call.tool == "aggregate_results"
            assert tool_call.args == {"key": "value"}
            assert tool_call.tool_call_id is None  # Deterministic chain
        finally:
            Condition.registry.remove("done_waiting")

    def test_waiting_condition_done_no_next_tool(self, mock_agent):
        """Test that Waiting returns False when done but no next_tool."""
        if "done_no_tool" in Condition.registry.registered():
            Condition.registry.remove("done_no_tool")

        @Condition.register()
        def done_no_tool(stack, branch):
            return False  # Done waiting

        try:
            condition = Condition(evaluator="done_no_tool")
            waiting = Waiting(
                stack=mock_agent.stack,
                condition=condition,
                # No next_tool specified
            )

            result = waiting.step()

            assert result is False
            # Should not have added any interactions
            assert len(mock_agent.stack.interactions) == 0
        finally:
            Condition.registry.remove("done_no_tool")

    def test_waiting_preserves_branch_on_chain(self, mock_agent):
        """Test that chained ToolCall inherits the Waiting's branch."""
        if "done_branch" in Condition.registry.registered():
            Condition.registry.remove("done_branch")

        @Condition.register()
        def done_branch(stack, branch):
            return False

        try:
            condition = Condition(evaluator="done_branch")
            waiting = Waiting(
                stack=mock_agent.stack,
                branch="my_branch",
                condition=condition,
                next_tool="my_tool",
            )

            waiting.step()

            tool_call = mock_agent.stack.interactions[0]
            assert tool_call.branch == "my_branch"
        finally:
            Condition.registry.remove("done_branch")

    def test_waiting_from_dict(self, mock_agent):
        """Test deserializing Waiting from dict."""
        data = {
            "branch": "test_branch",
            "condition": {
                "evaluator": "test_eval",
                "parameters": {"x": 1},
            },
            "next_tool": "my_tool",
            "next_tool_args": {"arg1": "val1"},
        }

        waiting = Waiting._from_dict(data, mock_agent.stack, [])

        assert waiting.branch == "test_branch"
        assert waiting.condition is not None
        assert waiting.condition.evaluator == "test_eval"
        assert waiting.condition.parameters == {"x": 1}
        assert waiting.next_tool == "my_tool"
        assert waiting.next_tool_args == {"arg1": "val1"}

    def test_waiting_from_dict_no_condition(self, mock_agent):
        """Test deserializing Waiting without condition."""
        data = {
            "branch": None,
        }

        waiting = Waiting._from_dict(data, mock_agent.stack, [])

        assert waiting.branch is None
        assert waiting.condition is None
        assert waiting.next_tool is None
        assert waiting.next_tool_args == {}


class TestWaitingIntegration:
    """Integration tests for Waiting with real branch completion."""

    def test_waiting_with_all_branches_complete(self, mock_agent):
        """Test Waiting with all_branches_complete condition."""
        # Register the all_branches_complete condition
        if "all_branches_complete" in Condition.registry.registered():
            Condition.registry.remove("all_branches_complete")

        Condition.registry.register(
            all_branches_complete, name="all_branches_complete"
        )

        try:
            # Set up main task
            task = Task(
                name="test_task",
                description="Test",
                parameters={},
                prompt="Test",
            )
            task_def = TaskDefinition(stack=mock_agent.stack, task=task)
            mock_agent.stack.add_interaction(task_def)

            # Create two complete branches
            for branch_name in ["branch_a", "branch_b"]:
                branch_task_def = TaskDefinition(
                    stack=mock_agent.stack,
                    task=task,
                    branch=branch_name,
                )
                mock_agent.stack.add_interaction(
                    branch_task_def, branch=branch_name
                )
                # Add Waiting to mark branch as complete
                branch_waiting = Waiting(
                    stack=mock_agent.stack, branch=branch_name
                )
                mock_agent.stack.add_interaction(
                    branch_waiting, branch=branch_name
                )

            # Now create a Waiting on main that checks for branch completion
            condition = Condition(
                evaluator="all_branches_complete",
                parameters={"branches": ["branch_a", "branch_b"]},
            )
            main_waiting = Waiting(
                stack=mock_agent.stack,
                branch=None,  # Main branch
                condition=condition,
                next_tool="aggregate_results",
                next_tool_args={},
            )

            # All branches complete -> condition returns False (done waiting)
            # -> step() chains to next_tool and returns True
            result = main_waiting.step()

            assert result is True
            # Should have added a ToolCall for aggregate_results
            # Find the ToolCall in the main branch interactions
            from gimle.hugin.interaction.tool_call import ToolCall

            main_interactions = [
                i for i in mock_agent.stack.interactions if i.branch is None
            ]
            tool_calls = [
                i for i in main_interactions if isinstance(i, ToolCall)
            ]
            assert len(tool_calls) == 1
            assert tool_calls[0].tool == "aggregate_results"

        finally:
            if "all_branches_complete" in Condition.registry.registered():
                Condition.registry.remove("all_branches_complete")


class TestWaitForTicks:
    """Tests for the wait_for_ticks condition function."""

    def test_wait_for_ticks_keeps_waiting(self, mock_agent_with_state):
        """Test returns True for first N-1 evaluations."""
        stack = mock_agent_with_state.stack
        waiting = Waiting(stack=stack)
        stack.add_interaction(waiting)

        # With ticks=3, first two calls should return True
        assert wait_for_ticks(stack, branch=None, ticks=3) is True
        assert wait_for_ticks(stack, branch=None, ticks=3) is True

    def test_wait_for_ticks_done_after_n_ticks(self, mock_agent_with_state):
        """Test returns False on the Nth evaluation."""
        stack = mock_agent_with_state.stack
        waiting = Waiting(stack=stack)
        stack.add_interaction(waiting)

        # With ticks=3, third call should return False
        assert wait_for_ticks(stack, branch=None, ticks=3) is True
        assert wait_for_ticks(stack, branch=None, ticks=3) is True
        assert wait_for_ticks(stack, branch=None, ticks=3) is False

    def test_wait_for_ticks_cleans_up_state(self, mock_agent_with_state):
        """Test shared state key is removed after done."""
        stack = mock_agent_with_state.stack
        waiting = Waiting(stack=stack)
        stack.add_interaction(waiting)
        key = f"_wait_ticks_{waiting.uuid}"

        # Run through all ticks
        wait_for_ticks(stack, branch=None, ticks=1)

        # Key should be cleaned up
        assert stack.get_shared_state(key) is None

    def test_wait_for_ticks_independent_waitings(self, mock_agent_with_state):
        """Test two Waiting instances don't interfere."""
        stack = mock_agent_with_state.stack

        # Create two waitings on different branches
        waiting_a = Waiting(stack=stack, branch="branch_a")
        stack.add_interaction(waiting_a, branch="branch_a")
        waiting_b = Waiting(stack=stack, branch="branch_b")
        stack.add_interaction(waiting_b, branch="branch_b")

        # Advance branch_a twice (ticks=3)
        assert wait_for_ticks(stack, branch="branch_a", ticks=3) is True
        assert wait_for_ticks(stack, branch="branch_a", ticks=3) is True

        # branch_b has not been advanced yet, should be at 1
        assert wait_for_ticks(stack, branch="branch_b", ticks=3) is True

        # branch_a reaches ticks=3, should be done
        assert wait_for_ticks(stack, branch="branch_a", ticks=3) is False

        # branch_b still waiting (only at 2)
        assert wait_for_ticks(stack, branch="branch_b", ticks=3) is True

    def test_wait_for_ticks_raises_on_empty_branch(self, mock_agent_with_state):
        """Test raises ValueError when branch has no interactions."""
        stack = mock_agent_with_state.stack
        with pytest.raises(ValueError, match="No interaction found"):
            wait_for_ticks(stack, branch="nonexistent", ticks=3)

    def test_wait_for_ticks_raises_on_invalid_ticks(
        self, mock_agent_with_state
    ):
        """Test raises ValueError when ticks < 1."""
        stack = mock_agent_with_state.stack
        waiting = Waiting(stack=stack)
        stack.add_interaction(waiting)

        with pytest.raises(ValueError, match="ticks must be >= 1"):
            wait_for_ticks(stack, branch=None, ticks=0)

        with pytest.raises(ValueError, match="ticks must be >= 1"):
            wait_for_ticks(stack, branch=None, ticks=-5)

    def test_wait_for_ticks_one_completes_immediately(
        self, mock_agent_with_state
    ):
        """Test ticks=1 returns False on the very first call."""
        stack = mock_agent_with_state.stack
        waiting = Waiting(stack=stack)
        stack.add_interaction(waiting)

        assert wait_for_ticks(stack, branch=None, ticks=1) is False

    def test_wait_for_ticks_via_condition_evaluate(self, mock_agent_with_state):
        """Test wait_for_ticks through the Condition.evaluate() path."""
        stack = mock_agent_with_state.stack
        waiting = Waiting(stack=stack)
        stack.add_interaction(waiting)

        condition = Condition(
            evaluator="wait_for_ticks",
            parameters={"ticks": 2},
        )

        assert condition.evaluate(stack, None) is True
        assert condition.evaluate(stack, None) is False

    def test_wait_for_ticks_via_waiting_step(self, mock_agent_with_state):
        """Test full integration: Waiting.step() with wait_for_ticks."""
        stack = mock_agent_with_state.stack
        condition = Condition(
            evaluator="wait_for_ticks",
            parameters={"ticks": 2},
        )
        waiting = Waiting(
            stack=stack,
            condition=condition,
            next_tool="check_folder",
            next_tool_args={"folder_path": "/tmp"},
        )
        stack.add_interaction(waiting)

        # First step: still waiting
        assert waiting.step() is True
        assert len(stack.interactions) == 1  # No ToolCall added

        # Second step: done, chains to next_tool
        assert waiting.step() is True
        assert len(stack.interactions) == 2
        chained = stack.interactions[1]
        assert isinstance(chained, ToolCall)
        assert chained.tool == "check_folder"
        assert chained.args == {"folder_path": "/tmp"}
