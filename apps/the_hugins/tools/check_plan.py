"""Tool for creatures to check their plan progress."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def check_plan_tool(
    world_id: str,
    plan_id: Optional[str] = None,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Check the progress of a plan.

    If no plan_id is given, shows the highest priority active plan.

    Args:
        world_id: The ID of the world
        plan_id: Optional specific plan ID to check
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Plan progress information including current step
    """
    if not stack:
        return ToolResponse(
            is_error=True, content={"error": "Stack not available"}
        )

    agent_id = stack.agent.id

    # Get world from environment
    env_vars = stack.agent.environment.env_vars
    worlds: Dict[str, Any] = env_vars.get("worlds", {})
    if world_id not in worlds:
        return ToolResponse(
            is_error=True, content={"error": f"World '{world_id}' not found"}
        )

    world = cast("World", worlds[world_id])

    # Get creature
    creature = world.get_creature(agent_id)
    if not creature:
        return ToolResponse(
            is_error=True,
            content={"error": f"Creature {agent_id} not found in world"},
        )

    # Get the plan
    if plan_id:
        plan = creature.get_plan_by_id(plan_id)
        if not plan:
            return ToolResponse(
                is_error=True,
                content={
                    "error": f"Plan '{plan_id}' not found.",
                    "hint": "Check your plan IDs with get_goals.",
                },
            )
    else:
        plan = creature.get_active_plan()
        if not plan:
            # Check if there are any plans at all
            if creature.plans:
                return ToolResponse(
                    is_error=False,
                    content={
                        "message": "No active plans. All plans are completed or failed.",
                        "total_plans": len(creature.plans),
                        "plans": [
                            {
                                "id": p.id,
                                "name": p.name,
                                "status": p.status.value,
                            }
                            for p in creature.plans
                        ],
                    },
                )
            return ToolResponse(
                is_error=False,
                content={
                    "message": "You have no plans. Use make_plan to create one.",
                },
            )

    # Get current step
    current_step = plan.get_current_step()

    # Format steps with status
    formatted_steps = []
    for step in plan.steps:
        step_info: Dict[str, Any] = {
            "step_number": step.order + 1,
            "description": step.description,
            "status": step.status.value,
        }
        if step.success_condition:
            step_info["success_condition"] = step.success_condition
        if step.notes:
            step_info["notes"] = step.notes
        formatted_steps.append(step_info)

    progress = plan.get_progress()
    progress_percent = int(progress * 100)

    return ToolResponse(
        is_error=False,
        content={
            "plan_id": plan.id,
            "plan_name": plan.name,
            "description": plan.description,
            "status": plan.status.value,
            "priority": plan.priority,
            "progress": f"{progress_percent}%",
            "current_step": current_step.description if current_step else None,
            "current_step_number": plan.current_step_index + 1,
            "total_steps": len(plan.steps),
            "steps": formatted_steps,
            "message": (
                f"Plan '{plan.name}' is {progress_percent}% complete. "
                f"Current step: {current_step.description}"
                if current_step
                else f"Plan '{plan.name}' is {plan.status.value}."
            ),
        },
    )
