"""Branch comparison tool for the branching example."""

from typing import TYPE_CHECKING, Any, Dict

from gimle.hugin.interaction.task_result import TaskResult
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def compare_branches(stack: "Stack") -> ToolResponse:
    """Compare results from all branches and provide summary.

    This tool examines all active branches and their completion status,
    providing a comparison of results for decision-making.

    Args:
        stack: The stack to compare branches from

    Returns:
        ToolResponse with comparison of all branch results
    """
    branches = stack.get_active_branches()
    results: Dict[str, Dict[str, Any]] = {}

    for branch in branches:
        if branch is None:
            continue

        if stack.is_branch_complete(branch):
            last = stack.get_last_interaction_for_branch(branch)
            if isinstance(last, TaskResult):
                branch_interactions = stack.get_branch_interactions(branch)
                results[branch] = {
                    "status": last.finish_type,
                    "interactions": len(branch_interactions),
                    "completed": True,
                }
        else:
            branch_interactions = stack.get_branch_interactions(branch)
            results[branch] = {
                "status": "in_progress",
                "interactions": len(branch_interactions),
                "completed": False,
            }

    comparison = "Branch Comparison Results:\n\n"
    for branch_name, data in results.items():
        status = "✓ Completed" if data["completed"] else "⋯ In Progress"
        comparison += f"Branch: {branch_name}\n"
        comparison += f"  Status: {status} ({data['status']})\n"
        comparison += f"  Interactions: {data['interactions']}\n\n"

    if not results:
        comparison = "No branches have been created yet."

    return ToolResponse(
        is_error=False,
        content={
            "branches": results,
            "comparison": comparison,
        },
    )
