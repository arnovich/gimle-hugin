"""Speak to Hugin tool for direct inter-agent communication."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def speak_to_hugin(
    world_id: str,
    target_name: str,
    message: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Send a message directly to another Hugin's mind.

    This tool allows direct communication between Hugins when they are
    adjacent (within 1 cell). The message is delivered to the target
    Hugin's agent using the message_agent() method.

    Args:
        world_id: The ID of the world
        target_name: Name of the Hugin to speak to
        message: The message to send to the other Hugin
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        ToolResponse with success status and delivery confirmation
    """
    if not stack:
        return ToolResponse(
            is_error=True, content={"error": "Stack not available"}
        )

    agent_id = stack.agent.id
    session = stack.agent.session

    # Get world from environment
    env_vars = stack.agent.environment.env_vars
    if "worlds" not in env_vars:
        raise ValueError("No worlds found in environment")

    worlds: Dict[str, Any] = env_vars.get("worlds", {})
    if world_id not in worlds:
        raise ValueError(f"World '{world_id}' not found")

    world = cast("World", worlds[world_id])

    # Get sender creature
    sender_creature = world.get_creature(agent_id)
    if not sender_creature:
        raise ValueError(f"Creature {agent_id} not found in world")

    # Get sender position
    sender_pos = world.get_creature_position(agent_id)
    if sender_pos is None:
        raise ValueError(f"Creature {agent_id} not found in world")

    x, y = sender_pos

    # Find the target creature
    target_creature = world.get_creature_by_name(target_name)
    if not target_creature:
        # List nearby creatures
        nearby = world.get_nearby_creatures(x, y, radius=3)
        nearby_names = [c.name for c in nearby]
        print(
            f"***** Hugin '{target_name}' not found nearby, nearby hugins: {nearby_names}"
        )
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Hugin '{target_name}' not found nearby",
                "nearby_hugins": nearby_names,
            },
        )

    # Check if target is adjacent (within 1 cell)
    tx, ty = target_creature.position
    distance = max(abs(tx - x), abs(ty - y))
    if distance > 1:
        print(
            f"***** Hugin '{target_name}' is too far away (distance: {distance} cells). You must be adjacent (within 1 cell) to speak directly to another Hugin."
        )
        return ToolResponse(
            is_error=True,
            content={
                "error": f"{target_name} is too far away (distance: {distance} cells). You must be adjacent (within 1 cell) to speak directly to another Hugin.",
                "target_position": (tx, ty),
                "your_position": (x, y),
            },
        )

    # Get the target agent from the session
    target_agent_id = target_creature.agent_id
    target_agent = None
    for agent in session.agents:
        if agent.id == target_agent_id:
            target_agent = agent
            break

    if not target_agent:
        raise ValueError(f"Could not find agent for {target_name}")

    # Format the message to include sender information
    formatted_message = (
        f"{sender_creature.name} speaks to you directly: '{message}'"
    )

    # Send the message to the target agent
    target_agent.message_agent(formatted_message)

    # Record this interaction in the world action log
    world.action_log.add_action(
        creature_name=sender_creature.name,
        agent_id=agent_id,
        action_type="speak_to_hugin",
        description=f"{sender_creature.name} speaks to {target_name}: '{message}'",
        timestamp=world.tick,
        location=sender_pos,
        details={"message": message, "target": target_name},
        reason=reason,
    )

    print(f"***** Message delivered to {target_name}")

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "sender": sender_creature.name,
            "target": target_name,
            "message": message,
            "delivery_status": "Message delivered to " + target_name,
            "message_display": f"{sender_creature.name} speaks directly to {target_name}: '{message}'",
        },
    )
