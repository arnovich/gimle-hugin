"""Tool for creatures to update their plan progress."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def update_plan_tool(
    world_id: str,
    plan_id: str,
    action: str,
    notes: Optional[str] = None,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Update the progress of a plan.

    Actions:
    - complete_step: Mark current step as completed, advance to next
    - fail_step: Mark current step as failed (plan becomes failed)
    - skip_step: Skip current step, advance to next
    - abandon: Abandon the entire plan

    Args:
        world_id: The ID of the world
        plan_id: The plan ID to update
        action: Action to take (complete_step, fail_step, skip_step, abandon)
        notes: Optional notes about this update
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Updated plan status
    """
    # Import here to avoid circular imports
    import sys

    sys.path.insert(0, "apps/the_hugins")
    from world.goals import PlanStatus, StepStatus

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
    plan = creature.get_plan_by_id(plan_id)
    if not plan:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Plan '{plan_id}' not found.",
                "hint": "Check your plan IDs with get_goals.",
            },
        )

    # Validate action
    valid_actions = ["complete_step", "fail_step", "skip_step", "abandon"]
    if action not in valid_actions:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Invalid action '{action}'.",
                "valid_actions": valid_actions,
            },
        )

    # Check if plan is still active
    if plan.status != PlanStatus.ACTIVE:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Plan '{plan.name}' is {plan.status.value}, "
                "cannot update.",
                "hint": "Only active plans can be updated.",
            },
        )

    current_step = plan.get_current_step()
    result_message = ""

    if action == "complete_step":
        if not current_step:
            return ToolResponse(
                is_error=True,
                content={"error": "No current step to complete."},
            )

        if notes:
            current_step.notes = notes

        plan.advance_step()
        next_step = plan.get_current_step()

        if plan.status == PlanStatus.COMPLETED:
            result_message = (
                f"Completed step '{current_step.description}'. "
                f"Plan '{plan.name}' is now complete!"
            )
        else:
            result_message = (
                f"Completed step '{current_step.description}'. "
                f"Next step: {next_step.description if next_step else 'None'}"
            )

    elif action == "fail_step":
        if not current_step:
            return ToolResponse(
                is_error=True,
                content={"error": "No current step to fail."},
            )

        plan.fail_current_step(notes or "")
        result_message = (
            f"Step '{current_step.description}' failed. "
            f"Plan '{plan.name}' is now failed."
        )

    elif action == "skip_step":
        if not current_step:
            return ToolResponse(
                is_error=True,
                content={"error": "No current step to skip."},
            )

        current_step.status = StepStatus.SKIPPED
        if notes:
            current_step.notes = notes
        plan.current_step_index += 1

        if plan.current_step_index >= len(plan.steps):
            plan.status = PlanStatus.COMPLETED
            result_message = (
                f"Skipped step '{current_step.description}'. "
                f"Plan '{plan.name}' is now complete!"
            )
        else:
            next_step = plan.get_current_step()
            if next_step:
                next_step.status = StepStatus.IN_PROGRESS
            result_message = (
                f"Skipped step '{current_step.description}'. "
                f"Next step: {next_step.description if next_step else 'None'}"
            )

    elif action == "abandon":
        plan.status = PlanStatus.ABANDONED
        if current_step:
            current_step.status = StepStatus.SKIPPED
            if notes:
                current_step.notes = notes
        result_message = f"Abandoned plan '{plan.name}'."

    # Log action
    world.action_log.add_action(
        creature_name=creature.name,
        agent_id=agent_id,
        action_type="update_plan",
        description=f"{action} on plan: {plan.name}",
        timestamp=world.tick,
        location=creature.position,
        details={
            "plan_id": plan.id,
            "plan_name": plan.name,
            "action": action,
            "new_status": plan.status.value,
        },
        reason=reason,
    )

    progress = plan.get_progress()
    progress_percent = int(progress * 100)
    current_step_now = plan.get_current_step()

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "plan_id": plan.id,
            "plan_name": plan.name,
            "plan_status": plan.status.value,
            "progress": f"{progress_percent}%",
            "current_step": (
                current_step_now.description if current_step_now else None
            ),
            "message": result_message,
        },
    )
