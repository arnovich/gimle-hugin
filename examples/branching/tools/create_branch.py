"""Branching tools for the branching example."""

from typing import TYPE_CHECKING, List

from gimle.hugin.interaction.conditions import Condition
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.interaction.waiting import Waiting
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

# Maximum number of branches to create before waiting
MAX_BRANCHES = 3


def create_branch(
    stack: "Stack", branch_name: str, approach_description: str
) -> ToolResponse:
    """Create a new branch to explore a solution approach.

    This creates a new branch that will explore a specific solution
    approach in parallel with other branches. The branch loads the
    'explore_branch' task from the registry, which only has the finish
    tool - preventing recursive branch creation.

    After MAX_BRANCHES branches are created, returns a Waiting interaction
    that waits for all branches to complete, then chains to aggregate_branches.

    Args:
        stack: The stack to add the branch to
        branch_name: Name for the branch (use snake_case)
        approach_description: What approach this branch will explore

    Returns:
        ToolResponse confirming branch creation
    """
    # Get the original task definition for context
    task_def_interaction = stack.get_task_definition_interaction()
    if task_def_interaction is None:
        return ToolResponse(
            is_error=True,
            content={"error": "No task definition found in stack"},
        )

    original_task = task_def_interaction.task
    if original_task is None:
        return ToolResponse(
            is_error=True,
            content={"error": "No task found in task definition"},
        )

    # Load the branch exploration task from the registry
    branch_task_template = stack.agent.environment.task_registry.get(
        "explore_branch"
    )

    # Set the input parameters for this specific branch
    branch_task = branch_task_template.set_input_parameters(
        {
            "problem": original_task.parameters["problem"].get("value"),
            "criteria": original_task.parameters["criteria"].get("value"),
            "approach": approach_description,
        }
    )

    # Create task definition on the branch
    task_def = TaskDefinition(
        stack=stack,
        task=branch_task,
        branch=branch_name,
    )

    # Track this branch in shared state
    tracked_branches: List[str] = stack.get_shared_state(
        key="tracked_branches",
        namespace="common",
        default=[],
    )
    tracked_branches.append(branch_name)
    stack.set_shared_state(
        key="tracked_branches",
        value=tracked_branches,
        namespace="common",
    )

    stack.add_interaction(task_def, branch=branch_name)

    # Check if we've created enough branches
    if len(tracked_branches) >= MAX_BRANCHES:
        # Return a Waiting that will check for branch completion
        # and then chain to aggregate_branches
        return ToolResponse(
            is_error=False,
            content={
                "branch_name": branch_name,
                "approach": approach_description,
                "message": f"Created branch '{branch_name}' to explore: {approach_description}",
                "total_branches": len(tracked_branches),
                "waiting": f"All {MAX_BRANCHES} branches created. "
                "Waiting for them to complete...",
            },
            response_interaction=Waiting(
                stack=stack,
                branch=None,  # Main branch
                condition=Condition(
                    evaluator="all_branches_complete",
                    parameters={"branches": tracked_branches.copy()},
                ),
                next_tool="aggregate_branches",
                next_tool_args={},
            ),
        )

    return ToolResponse(
        is_error=False,
        content={
            "branch_name": branch_name,
            "approach": approach_description,
            "message": f"Created branch '{branch_name}' to explore: {approach_description}",
            "branches_created": len(tracked_branches),
            "branches_remaining": MAX_BRANCHES - len(tracked_branches),
        },
    )
