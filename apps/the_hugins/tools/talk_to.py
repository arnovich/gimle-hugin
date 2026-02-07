"""Talk to tool for initiating conversations with other creatures."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def talk_to_tool(
    world_id: str,
    creature_name: str,
    message: Optional[str] = None,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Initiate a conversation with another creature.

    Args:
        world_id: The ID of the world
        creature_name: Name of the creature to talk to
        message: Optional message to say to the creature
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Dictionary with conversation status
    """
    if not stack:
        return ToolResponse(
            is_error=True, content={"error": "Stack not available"}
        )

    agent_id = stack.agent.id

    # Get world from environment
    env_vars = stack.agent.environment.env_vars
    if "worlds" not in env_vars:
        return ToolResponse(
            is_error=True, content={"error": "No worlds found in environment"}
        )

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

    # Get position
    position = world.get_creature_position(agent_id)
    if position is None:
        return ToolResponse(
            is_error=True,
            content={"error": f"Creature {agent_id} not found in world"},
        )

    x, y = position

    # Find the target creature
    target_creature = world.get_creature_by_name(creature_name)
    if not target_creature:
        # List nearby creatures
        nearby = world.get_nearby_creatures(x, y, radius=3)
        nearby_names = [c.name for c in nearby]
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Creature '{creature_name}' not found nearby",
                "nearby_creatures": nearby_names,
            },
        )

    # Check if target is nearby (within 2 cells)
    tx, ty = target_creature.position
    distance = max(abs(tx - x), abs(ty - y))
    if distance > 2:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"{creature_name} is too far away (distance: {distance} cells). You can only talk to creatures within 2 cells.",
            },
        )

    # Talking improves sentiment for both parties
    creature.update_relationship(creature_name, "known", 1)
    target_creature.update_relationship(creature.name, "known", 1)

    # Log the action
    world.action_log.add_action(
        creature_name=creature.name,
        agent_id=agent_id,
        action_type="talk_to",
        description=(
            f"Talked to {creature_name}" + (f": '{message}'" if message else "")
        ),
        timestamp=world.tick,
        location=(x, y),
        details={
            "target": creature_name,
            "message": message,
        },
        reason=reason,
    )

    # If message provided, it's like saying something to them
    if message:
        return ToolResponse(
            is_error=False,
            content={
                "success": True,
                "speaker": creature.name,
                "target": creature_name,
                "message": message,
                "message_display": (
                    f"{creature.name} says to" f" {creature_name}: '{message}'"
                ),
            },
        )
    else:
        return ToolResponse(
            is_error=False,
            content={
                "success": True,
                "speaker": creature.name,
                "target": creature_name,
                "target_description": target_creature.description,
                "target_personality": target_creature.personality,
                "message_display": (
                    f"{creature.name} approaches {creature_name}"
                ),
            },
        )
