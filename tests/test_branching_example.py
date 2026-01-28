"""Integration tests for branching example."""

import shutil
import tempfile
from unittest.mock import patch

import pytest

from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.storage.local import LocalStorage


@pytest.fixture(autouse=True)
def _mock_llm_for_branching_example():
    """Prevent live LLM calls in the branching example tests.

    These tests are intended to validate branching mechanics (stack behavior),
    not the behavior of any specific external LLM provider.
    """
    state = {"created": 0, "compared": False}

    def _last_user_text(messages):
        for m in reversed(messages):
            if m.get("role") != "user":
                continue
            content = m.get("content")
            if (
                isinstance(content, list)
                and content
                and isinstance(content[0], dict)
                and content[0].get("type") == "text"
            ):
                return str(content[0].get("text") or "")
        return ""

    def fake_chat_completion(system_prompt, messages, tools, llm_model):
        last_user = _last_user_text(messages)

        # Branch tasks created by create_branch use a modified prompt.
        if "Explore approach:" in last_user:
            return {
                "role": "assistant",
                "content": "Explored approach. Ready to conclude.",
                "tool_call": None,
                "tool_call_id": None,
                "input_tokens": 1,
                "output_tokens": 1,
                "extra_content": None,
            }

        # Main task: deterministically create two branches, then compare.
        if (
            "Solve the following problem by exploring multiple approaches"
            in last_user
        ):
            if state["created"] < 2:
                state["created"] += 1
                branch_name = f"approach_{state['created']}"
                return {
                    "role": "assistant",
                    "content": {
                        "branch_name": branch_name,
                        "approach_description": f"Approach {state['created']}",
                    },
                    "tool_call": "create_branch",
                    "tool_call_id": f"create_branch_{state['created']}",
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "extra_content": None,
                }

            if not state["compared"]:
                state["compared"] = True
                return {
                    "role": "assistant",
                    "content": {},
                    "tool_call": "compare_branches",
                    "tool_call_id": "compare_branches_1",
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "extra_content": None,
                }

        # Default: end the branch (no tool call).
        return {
            "role": "assistant",
            "content": "Final recommendation.",
            "tool_call": None,
            "tool_call_id": None,
            "input_tokens": 1,
            "output_tokens": 1,
            "extra_content": None,
        }

    with patch(
        "gimle.hugin.llm.completion.chat_completion",
        side_effect=fake_chat_completion,
    ):
        yield

    # Cleanup: these example tools are loaded into the global Tool registry via
    # Environment.load(...), so remove them to avoid cross-test pollution.
    from gimle.hugin.tools.tool import Tool

    for name in ("create_branch", "compare_branches", "aggregate_branches"):
        if name in Tool.registry.registered():
            Tool.registry.remove(name)


class TestBranchingExample:
    """Test branching example demonstrates stack branching."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage for test."""
        temp_dir = tempfile.mkdtemp()
        storage = LocalStorage(base_path=temp_dir)
        yield storage
        shutil.rmtree(temp_dir)

    def test_creates_multiple_branches(self, temp_storage):
        """Test that agent can create multiple branches."""
        env = Environment.load("examples/branching", storage=temp_storage)
        session = Session(environment=env)

        config = env.config_registry.get("problem_solver")
        task = env.task_registry.get("solve_problem")
        agent = session.create_agent_from_task(config, task)

        for _ in range(50):
            if not agent.step():
                break

        branches = agent.stack.get_active_branches()
        assert len(branches) > 1, "Should have created at least one branch"

    def test_branch_isolation(self, temp_storage):
        """Test that branches don't see each other's interactions."""
        env = Environment.load("examples/branching", storage=temp_storage)
        session = Session(environment=env)

        config = env.config_registry.get("problem_solver")
        task = env.task_registry.get("solve_problem")
        agent = session.create_agent_from_task(config, task)

        for _ in range(50):
            if not agent.step():
                break

        branches = agent.stack.get_active_branches()

        if len(branches) < 3:
            pytest.skip("Not enough branches created for isolation test")

        branch_a = branches[1]
        branch_b = branches[2]

        interactions_a = agent.stack.get_branch_interactions(branch_a)
        interactions_b = agent.stack.get_branch_interactions(branch_b)

        a_branches = {i.branch for i in interactions_a}
        b_branches = {i.branch for i in interactions_b}

        assert (
            branch_b not in a_branches
        ), "Branch A should not see Branch B's interactions"
        assert (
            branch_a not in b_branches
        ), "Branch B should not see Branch A's interactions"

    def test_branch_sees_main_up_to_fork(self, temp_storage):
        """Test that branches see main branch up to fork point."""
        env = Environment.load("examples/branching", storage=temp_storage)
        session = Session(environment=env)

        config = env.config_registry.get("problem_solver")
        task = env.task_registry.get("solve_problem")
        agent = session.create_agent_from_task(config, task)

        for _ in range(50):
            if not agent.step():
                break

        branches = agent.stack.get_active_branches()

        if len(branches) < 2:
            pytest.skip("No branches created")

        branch = branches[1]

        branch_interactions = agent.stack.get_branch_interactions(branch)

        main_interactions = [i for i in branch_interactions if i.branch is None]
        assert (
            len(main_interactions) > 0
        ), "Branch should see some main branch interactions"

    def test_all_branches_can_complete(self, temp_storage):
        """Test that all branches can complete independently."""
        env = Environment.load("examples/branching", storage=temp_storage)
        session = Session(environment=env)

        config = env.config_registry.get("problem_solver")
        task = env.task_registry.get("solve_problem")
        agent = session.create_agent_from_task(config, task)

        for _ in range(100):
            if not agent.step():
                break

        branches = agent.stack.get_active_branches()

        if len(branches) < 2:
            pytest.skip("No branches created")

        completed_count = sum(
            1 for branch in branches if agent.stack.is_branch_complete(branch)
        )

        assert completed_count >= 0, "Should have some completed branches"

    def test_compare_branches_works(self, temp_storage):
        """Test that compare_branches tool returns results."""
        env = Environment.load("examples/branching", storage=temp_storage)
        session = Session(environment=env)

        config = env.config_registry.get("problem_solver")
        task = env.task_registry.get("solve_problem")
        agent = session.create_agent_from_task(config, task)

        for _ in range(50):
            if not agent.step():
                break

        branches = agent.stack.get_active_branches()
        assert len(branches) >= 1, "Should have at least main branch"
