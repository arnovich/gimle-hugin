"""Drop tool for dropping items."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from world.structures import STORAGE_CAPACITY

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def drop_tool(
    world_id: str,
    object_name: str,
    x: Optional[int] = None,
    y: Optional[int] = None,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Drop an object from your inventory to the current cell or a specified cell.

    Args:
        world_id: The ID of the world
        object_name: Name of the object to drop
        x: Optional x coordinate (defaults to creature's position)
        y: Optional y coordinate (defaults to creature's position)
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Dictionary with success status and updated inventory
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

    # Get creature position if x, y not specified
    if x is None or y is None:
        position = world.get_creature_position(agent_id)
        if position is None:
            return ToolResponse(
                is_error=True,
                content={"error": f"Creature {agent_id} not found in world"},
            )
        x, y = position

    # Check if position is valid
    if not world.is_valid_position(x, y):
        return ToolResponse(
            is_error=True, content={"error": f"Invalid position ({x}, {y})"}
        )

    # Check if creature is at this position or adjacent
    creature_pos = world.get_creature_position(agent_id)
    if creature_pos:
        cx, cy = creature_pos
        if abs(cx - x) > 1 or abs(cy - y) > 1:
            return ToolResponse(
                is_error=True,
                content={
                    "error": f"Position ({x}, {y}) is too far away. You can only drop objects at your current cell or adjacent cells."
                },
            )

    # Remove from inventory
    obj = creature.remove_from_inventory(object_name)
    if obj is None:
        inventory_names = [item.name for item in creature.get_inventory()]
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Object '{object_name}' not in your inventory",
                "inventory": inventory_names,
            },
        )

    # Add to cell
    cell = world.get_cell(x, y)
    if not cell:
        # Put item back in inventory since we already removed it
        creature.add_to_inventory(obj)
        return ToolResponse(
            is_error=True,
            content={"error": f"Cell at ({x}, {y}) not found"},
        )

    # Enforce storage capacity on storage cells
    if cell.structure == "storage":
        item_count = sum(1 for o in cell.objects if o.type.value == "item")
        if item_count >= STORAGE_CAPACITY:
            creature.add_to_inventory(obj)
            return ToolResponse(
                is_error=True,
                content={
                    "error": (
                        f"Storage is full ({item_count}/"
                        f"{STORAGE_CAPACITY} items)."
                    ),
                    "hint": "Take some items out first.",
                },
            )

    cell.add_object(obj)

    # Log the action
    world.action_log.add_action(
        creature_name=creature.name,
        agent_id=agent_id,
        action_type="drop",
        description=f"Dropped {object_name} at ({x}, {y})",
        timestamp=world.tick,
        location=(x, y),
        details={"item": object_name, "item_id": obj.id},
        reason=reason,
    )

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "object": obj.to_dict(),
            "message": f"You dropped {object_name} at ({x}, {y})",
            "inventory": [item.to_dict() for item in creature.get_inventory()],
        },
    )
