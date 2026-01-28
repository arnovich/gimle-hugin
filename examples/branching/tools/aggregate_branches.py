"""Aggregate branches tool for the branching example."""

from typing import TYPE_CHECKING, Any, Dict, List

from gimle.hugin.interaction.task_result import TaskResult
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def aggregate_branches(stack: "Stack") -> ToolResponse:
    """Aggregate results from all tracked branches.

    This tool collects the finish results from all branches that were
    created by create_branch and returns them for comparison.

    Args:
        stack: The stack to aggregate from

    Returns:
        ToolResponse with aggregated branch results
    """
    # Get the list of tracked branches from shared state
    tracked_branches: List[str] = stack.get_shared_state(
        key="tracked_branches",
        namespace="common",
        default=[],
    )

    if not tracked_branches:
        return ToolResponse(
            is_error=True,
            content={"error": "No branches were tracked"},
        )

    # Collect results from each branch
    branch_results: Dict[str, Any] = {}

    for branch_name in tracked_branches:
        # Find the TaskResult (finish) interaction for this branch
        branch_interactions = stack.get_branch_interactions(branch_name)

        # Look for TaskResult in the branch
        result = None
        for interaction in reversed(branch_interactions):
            if isinstance(interaction, TaskResult):
                result = {
                    "finish_type": interaction.finish_type,
                    "result": interaction.result,
                }
                break

        if result:
            branch_results[branch_name] = result
        else:
            branch_results[branch_name] = {
                "error": "No finish result found for this branch"
            }

    stack.set_shared_state(
        key="tracked_branches",
        value=[],
        namespace="common",
    )

    return ToolResponse(
        is_error=False,
        content={
            "branches_aggregated": len(branch_results),
            "results": branch_results,
            "message": f"Aggregated results from {len(branch_results)} branches. "
            "Review the results and provide your final recommendation.",
        },
    )
