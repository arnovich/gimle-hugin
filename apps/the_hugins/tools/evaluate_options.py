"""Tool for creatures to evaluate explored options and make a decision."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.interaction.task_result import TaskResult
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def evaluate_options_tool(
    world_id: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Evaluate all explored option branches and see the results.

    Use this after `explore_options` to compare the outcomes of
    different choices and make an informed decision.

    Args:
        world_id: The ID of the world
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Summary of all explored options with their evaluations
    """
    if not stack:
        return ToolResponse(
            is_error=True, content={"error": "Stack not available"}
        )

    branches = stack.get_active_branches()
    results = []
    in_progress = []

    for branch_name in branches:
        if branch_name is None:
            continue  # Skip main branch

        # Only look at option branches
        if not branch_name.startswith("option_"):
            continue

        branch_interactions = stack.get_branch_interactions(branch_name)
        is_complete = stack.is_branch_complete(branch_name)

        if is_complete:
            last = stack.get_last_interaction_for_branch(branch_name)
            status = "completed"

            if isinstance(last, TaskResult):
                # Try to get the finish message/summary
                status = last.finish_type or "completed"

            # Extract the option name from branch name
            option_parts = branch_name.replace("option_", "").split("_", 1)
            if len(option_parts) > 1:
                option_name = option_parts[1].replace("_", " ")
            else:
                option_name = branch_name

            results.append(
                {
                    "branch": branch_name,
                    "option": option_name,
                    "status": status,
                    "interactions": len(branch_interactions),
                    "completed": True,
                }
            )
        else:
            in_progress.append(branch_name)

    # Build comparison text
    if not results and not in_progress:
        return ToolResponse(
            is_error=False,
            content={
                "found": False,
                "message": "No option branches found. Use `explore_options` first "
                "to create branches for different choices.",
                "results": [],
            },
        )

    comparison_parts = ["## Option Evaluation Results\n"]

    if results:
        comparison_parts.append("### Completed Evaluations:")
        for r in results:
            comparison_parts.append(
                f"- **{r['option']}**: {r['status']} "
                f"({r['interactions']} interactions)"
            )
        comparison_parts.append("")

    if in_progress:
        comparison_parts.append("### Still Evaluating:")
        for b in in_progress:
            comparison_parts.append(f"- {b}")
        comparison_parts.append(
            "\n*Wait for all branches to complete before deciding.*"
        )

    if results and not in_progress:
        comparison_parts.append(
            "\n### Ready to Decide\n"
            "All options have been evaluated. Consider which option "
            "aligns best with your goals and personality, then take action!"
        )

    # Log action if world available
    agent_id = stack.agent.id
    env_vars = stack.agent.environment.env_vars
    worlds: Dict[str, Any] = env_vars.get("worlds", {})
    world = cast("World", worlds.get(world_id))

    if world:
        creature = world.get_creature(agent_id)
        if creature:
            world.action_log.add_action(
                creature_name=creature.name,
                agent_id=agent_id,
                action_type="evaluate_options",
                description=f"Evaluated {len(results)} options",
                timestamp=world.tick,
                location=creature.position,
                details={
                    "completed": len(results),
                    "in_progress": len(in_progress),
                },
                reason=reason,
            )

    return ToolResponse(
        is_error=False,
        content={
            "found": True,
            "results": results,
            "in_progress": in_progress,
            "all_complete": len(in_progress) == 0,
            "comparison": "\n".join(comparison_parts),
            "message": f"Evaluated {len(results)} completed option(s), "
            f"{len(in_progress)} still in progress.",
        },
    )
