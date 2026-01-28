"""Tool for creatures to view their goals and plans."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def get_goals_tool(
    world_id: str,
    include_completed: bool = False,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Get all goals and plans for the creature.

    Args:
        world_id: The ID of the world
        include_completed: Whether to include completed goals/plans
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        List of goals and plans with their status
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

    # Collect goals
    goals_list: List[Dict[str, Any]] = []
    for goal in creature.goals:
        if not include_completed and goal.completed:
            continue
        goal_info: Dict[str, Any] = {
            "type": goal.type.value,
            "description": goal.description,
            "priority": goal.priority,
            "completed": goal.completed,
            "progress": f"{int(goal.progress * 100)}%",
        }
        if goal.target:
            goal_info["target"] = goal.target
        goals_list.append(goal_info)

    # Collect plans
    plans_list: List[Dict[str, Any]] = []
    for plan in creature.plans:
        if not include_completed and plan.status.value in [
            "completed",
            "failed",
            "abandoned",
        ]:
            continue

        current_step = plan.get_current_step()
        progress = plan.get_progress()

        plan_info: Dict[str, Any] = {
            "id": plan.id,
            "name": plan.name,
            "description": plan.description,
            "status": plan.status.value,
            "priority": plan.priority,
            "progress": f"{int(progress * 100)}%",
            "current_step": current_step.description if current_step else None,
            "total_steps": len(plan.steps),
        }
        plans_list.append(plan_info)

    # Sort by priority
    goals_list.sort(key=lambda g: g["priority"], reverse=True)
    plans_list.sort(key=lambda p: p["priority"], reverse=True)

    # Build summary message
    active_goals = len([g for g in goals_list if not g["completed"]])
    active_plans = len([p for p in plans_list if p["status"] == "active"])

    if not goals_list and not plans_list:
        message = (
            "You have no goals or plans. "
            "Use make_plan to create a plan for achieving something."
        )
    else:
        message = f"You have {active_goals} active goal(s) and {active_plans} active plan(s)."

    return ToolResponse(
        is_error=False,
        content={
            "goals": goals_list,
            "plans": plans_list,
            "summary": {
                "active_goals": active_goals,
                "active_plans": active_plans,
                "total_goals": len(creature.goals),
                "total_plans": len(creature.plans),
            },
            "message": message,
        },
    )
