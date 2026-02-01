"""Give tool for gifting items to other creatures."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def give_tool(
    world_id: str,
    creature_name: str,
    item_name: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Give an item from your inventory to a nearby creature for free.

    Args:
        world_id: The ID of the world
        creature_name: Name of the creature to give the item to
        item_name: Name of the item to give
        reason: Why you are performing this action
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Dictionary with gift result
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

    # Get giver creature
    giver = world.get_creature(agent_id)
    if not giver:
        return ToolResponse(
            is_error=True,
            content={"error": f"Creature {agent_id} not found in world"},
        )

    # Get recipient creature
    recipient = world.get_creature_by_name(creature_name)
    if not recipient:
        return ToolResponse(
            is_error=True,
            content={"error": f"Creature '{creature_name}' not found"},
        )

    # Can't give to yourself
    if recipient.agent_id == agent_id:
        return ToolResponse(
            is_error=True,
            content={"error": "You cannot give items to yourself."},
        )

    # Check if recipient is nearby (within 2 cells)
    gx, gy = giver.position
    rx, ry = recipient.position
    if abs(gx - rx) > 2 or abs(gy - ry) > 2:
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    f"'{creature_name}' is too far away. "
                    "You can only give items to creatures within 2 cells."
                ),
                "your_position": {"x": gx, "y": gy},
                "their_position": {"x": rx, "y": ry},
            },
        )

    # Check if giver has the item
    item = giver.remove_from_inventory(item_name)
    if not item:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"You don't have '{item_name}' in your inventory.",
                "your_inventory": [obj.name for obj in giver.inventory],
            },
        )

    # Give the item
    recipient.add_to_inventory(item)

    # Log the action
    world.action_log.add_action(
        creature_name=giver.name,
        agent_id=agent_id,
        action_type="give",
        description=f"Gave {item_name} to {creature_name}",
        timestamp=world.tick,
        location=giver.position,
        details={
            "item": item_name,
            "recipient": creature_name,
        },
        reason=reason,
    )

    # Add memories for both creatures
    world.add_memory_to_creature(
        agent_id,
        "gave_gift",
        f"Gave {item_name} to {creature_name}",
        location=giver.position,
        related_creature=creature_name,
        related_item=item_name,
        importance=6,
    )

    # Update relationships - giving improves sentiment
    giver.update_relationship(creature_name, "friend", 3)
    recipient.update_relationship(giver.name, "friend", 3)

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "item": item_name,
            "recipient": creature_name,
            "message": f"You gave {item_name} to {creature_name}.",
        },
    )
