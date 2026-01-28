"""Tool for creatures to create multi-step plans."""

import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def make_plan_tool(
    world_id: str,
    plan_name: str,
    plan_description: str,
    steps: List[Dict[str, Any]],
    priority: int = 5,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Create a multi-step plan to achieve a goal.

    Plans help you break down complex goals into actionable steps
    that you can track and execute one by one.

    Args:
        world_id: The ID of the world
        plan_name: Short name for the plan (e.g., "Collect apples")
        plan_description: What you want to achieve with this plan
        steps: List of step dictionaries with 'description' and optional
               'success_condition' and 'required_tools'
        priority: How important this plan is (1-10, default 5)
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        The created plan with ID for tracking
    """
    # Import here to avoid circular imports
    import sys

    sys.path.insert(0, "apps/the_hugins")
    from world.goals import Plan, PlanStep, StepStatus

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

    # Validate steps
    if not steps or len(steps) == 0:
        return ToolResponse(
            is_error=True,
            content={
                "error": "A plan must have at least one step.",
                "hint": "Each step should have a 'description' field.",
            },
        )

    if len(steps) > 10:
        return ToolResponse(
            is_error=True,
            content={
                "error": "Plans cannot have more than 10 steps.",
                "hint": "Break very complex plans into multiple smaller plans.",
            },
        )

    # Create plan steps
    plan_steps = []
    for i, step_data in enumerate(steps):
        # Validate step is a dict (defensive check for LLM-generated input)
        step_dict = step_data if isinstance(step_data, dict) else {}
        if not step_dict:
            return ToolResponse(
                is_error=True,
                content={
                    "error": f"Step {i + 1} must be a dictionary.",
                    "hint": "Format: {'description': '...', 'success_condition': '...'}",
                },
            )

        description = step_dict.get("description", "")
        if not description:
            return ToolResponse(
                is_error=True,
                content={
                    "error": f"Step {i + 1} is missing a description.",
                },
            )

        step = PlanStep(
            id=str(uuid.uuid4())[:8],
            description=description,
            required_tools=step_dict.get("required_tools", []),
            success_condition=step_dict.get("success_condition"),
            status=StepStatus.PENDING if i > 0 else StepStatus.IN_PROGRESS,
            order=i,
        )
        plan_steps.append(step)

    # Create the plan
    plan = Plan(
        id=str(uuid.uuid4())[:8],
        name=plan_name,
        description=plan_description,
        steps=plan_steps,
        current_step_index=0,
        created_tick=world.tick,
        priority=max(1, min(10, priority)),
    )

    # Add plan to creature
    creature.add_plan(plan)

    # Log action
    world.action_log.add_action(
        creature_name=creature.name,
        agent_id=agent_id,
        action_type="make_plan",
        description=f"Created plan: {plan_name}",
        timestamp=world.tick,
        location=creature.position,
        details={
            "plan_id": plan.id,
            "plan_name": plan_name,
            "num_steps": len(plan_steps),
        },
        reason=reason,
    )

    # Format steps for response
    formatted_steps = []
    for step in plan_steps:
        formatted_steps.append(
            {
                "step_number": step.order + 1,
                "description": step.description,
                "status": step.status.value,
            }
        )

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "plan_id": plan.id,
            "plan_name": plan_name,
            "description": plan_description,
            "priority": plan.priority,
            "steps": formatted_steps,
            "current_step": plan_steps[0].description if plan_steps else None,
            "message": f"Created plan '{plan_name}' with {len(plan_steps)} steps. "
            f"Start with: {plan_steps[0].description}",
        },
    )
