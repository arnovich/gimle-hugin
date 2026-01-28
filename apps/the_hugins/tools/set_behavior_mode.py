"""Tool for creatures to switch behavior modes."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


VALID_MODES = ["exploring", "collecting", "socializing", "planning"]


def set_behavior_mode_tool(
    world_id: str,
    mode: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Switch the creature's behavior mode.

    This tool triggers a state machine transition to change the creature's
    available tools and focus area.

    Args:
        world_id: The ID of the world
        mode: One of 'exploring', 'collecting', 'socializing', 'planning'
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Confirmation of mode switch with new mode details
    """
    if not stack:
        return ToolResponse(
            is_error=True, content={"error": "Stack not available"}
        )

    mode = mode.lower().strip()
    if mode not in VALID_MODES:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Invalid mode '{mode}'. Choose from: {VALID_MODES}",
                "valid_modes": VALID_MODES,
            },
        )

    # Set shared state to trigger state machine transition
    stack.set_shared_state("target_behavior_mode", mode)

    agent_id = stack.agent.id

    # Get world from environment
    env_vars = stack.agent.environment.env_vars
    worlds: Dict[str, Any] = env_vars.get("worlds", {})
    if world_id not in worlds:
        return ToolResponse(
            is_error=True, content={"error": f"World '{world_id}' not found"}
        )

    world = cast("World", worlds[world_id])

    # Log the mode switch action
    creature = world.get_creature(agent_id)
    if creature:
        world.action_log.add_action(
            creature_name=creature.name,
            agent_id=agent_id,
            action_type="set_behavior_mode",
            description=f"Switched to {mode} mode",
            timestamp=world.tick,
            location=creature.position,
            details={"new_mode": mode},
            reason=reason,
        )

    mode_descriptions = {
        "exploring": "Focus on discovering new places and understanding "
        "the environment",
        "collecting": "Focus on gathering items and resources",
        "socializing": "Focus on interacting with other creatures",
        "planning": "Focus on thinking about goals and deciding next steps",
    }

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "new_mode": mode,
            "config_name": f"creature_{mode}",
            "description": mode_descriptions[mode],
            "message": f"Successfully switched to {mode} mode. "
            f"Your available tools and focus have changed.",
        },
    )
