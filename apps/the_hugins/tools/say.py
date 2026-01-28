"""Say tool for creatures to communicate."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def say_tool(
    world_id: str,
    message: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Say something that can be heard by nearby creatures.

    Args:
        world_id: The ID of the world
        message: The message to say
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Dictionary with the message and who heard it
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

    # Find nearby creatures (within 2 cells)
    nearby_creatures = world.get_nearby_creatures(x, y, radius=2)
    heard_by = [creature.name for creature in nearby_creatures]

    # Add memory for speaker and listeners
    world.add_memory_to_creature(
        agent_id,
        "said_something",
        f"Said: '{message}'",
        location=(x, y),
        importance=3,
    )

    for nearby in nearby_creatures:
        # Update relationships
        creature.update_relationship(nearby.name, "known", sentiment_change=1)
        nearby.update_relationship(creature.name, "known", sentiment_change=1)

        # Add memory for listeners
        world.add_memory_to_creature(
            nearby.agent_id,
            "heard_something",
            f"Heard {creature.name} say: '{message}'",
            location=(x, y),
            related_creature=creature.name,
            importance=4,
        )

    # Log the action
    world.action_log.add_action(
        creature_name=creature.name,
        agent_id=agent_id,
        action_type="say",
        description=f"Said: '{message}'",
        timestamp=world.tick,
        location=(x, y),
        details={"message": message, "heard_by": heard_by},
        reason=reason,
    )

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "speaker": creature.name,
            "message": message,
            "heard_by": heard_by,
            "message_display": f"{creature.name} says: '{message}'",
        },
    )
