"""Take tool for picking up items."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def take_tool(
    world_id: str,
    object_name: str,
    x: Optional[int] = None,
    y: Optional[int] = None,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Take an object from the current cell or a specified cell.

    Args:
        world_id: The ID of the world
        object_name: Name of the object to take
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
                    "error": f"Object at ({x}, {y}) is too far away. You can only take objects from your current cell or adjacent cells."
                },
            )

    # Get cell and find object
    cell = world.get_cell(x, y)
    if not cell:
        return ToolResponse(
            is_error=True, content={"error": f"Cell at ({x}, {y}) not found"}
        )

    # Find the object (exclude creatures)
    obj = None
    for item in cell.objects:
        if item.name == object_name and item.type.value == "item":
            obj = item
            break

    if obj is None:
        available_items = [
            item.name for item in cell.objects if item.type.value == "item"
        ]
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Object '{object_name}' not found at ({x}, {y})",
                "available_items": available_items,
            },
        )

    # Remove object from cell
    cell.remove_object(object_name)

    # Add to creature inventory
    creature = world.get_creature(agent_id)
    if creature:
        creature.add_to_inventory(obj)
        # Add memory
        world.add_memory_to_creature(
            agent_id,
            "found_item",
            f"Picked up {object_name}",
            location=(x, y),
            related_item=object_name,
            importance=3,
        )

        # Log the action
        world.action_log.add_action(
            creature_name=creature.name,
            agent_id=agent_id,
            action_type="take",
            description=f"Picked up {object_name} at ({x}, {y})",
            timestamp=world.tick,
            location=(x, y),
            details={"item": object_name, "item_id": obj.id},
            reason=reason,
        )

    # Note storage remaining capacity
    storage_info = None
    if cell and cell.structure == "storage":
        remaining = sum(1 for o in cell.objects if o.type.value == "item")
        storage_info = f"Storage has {remaining} items remaining."

    msg = f"You picked up {object_name}"
    if storage_info:
        msg += f" ({storage_info})"

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "object": obj.to_dict(),
            "message": msg,
            "inventory": (
                [item.to_dict() for item in creature.get_inventory()]
                if creature
                else []
            ),
        },
    )
