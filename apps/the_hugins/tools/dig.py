"""Tool for creatures to dig holes in the ground."""

import random
from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def dig_tool(
    world_id: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Dig a hole at your current location.

    Requires a basic_tool in your inventory. Digging on certain terrain
    may reveal buried items!

    Args:
        world_id: The ID of the world
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Result of digging, including any items found
    """
    # Import here to avoid circular imports
    import sys

    sys.path.insert(0, "apps/the_hugins")
    from world.cell import TerrainType
    from world.object import Object, ObjectType

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

    # Check for basic_tool in inventory
    has_tool = any(item.name == "basic_tool" for item in creature.inventory)
    if not has_tool:
        return ToolResponse(
            is_error=True,
            content={
                "error": "You need a basic_tool to dig.",
                "hint": "Craft a basic_tool from stick + stone.",
            },
        )

    # Get current cell
    x, y = creature.position
    cell = world.get_cell(x, y)
    if not cell:
        return ToolResponse(
            is_error=True, content={"error": "Current cell not found"}
        )

    # Check if terrain is diggable
    undiggable = {TerrainType.WATER, TerrainType.STONE, TerrainType.HOLE}
    if cell.terrain in undiggable:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Cannot dig in {cell.terrain.value}.",
                "hint": "Try digging in grass, dirt, sand, or forest.",
            },
        )

    # Dig the hole
    original_terrain = cell.terrain
    cell.terrain = TerrainType.HOLE

    # Chance to find buried items
    found_items = []
    if random.random() < 0.3:  # 30% chance to find something
        buried_items = ["stone", "pebble", "seed", "acorn", "bone"]
        item_name = random.choice(buried_items)
        item = Object(
            name=item_name,
            type=ObjectType.ITEM,
            description=f"A {item_name} found while digging",
            id=f"buried_{item_name}_{x}_{y}_{world.tick}",
        )
        cell.add_object(item)
        found_items.append(item_name)

    # Log action
    world.action_log.add_action(
        creature_name=creature.name,
        agent_id=agent_id,
        action_type="dig",
        description=f"Dug a hole at ({x}, {y})"
        + (f", found {found_items}" if found_items else ""),
        timestamp=world.tick,
        location=(x, y),
        details={
            "original_terrain": original_terrain.value,
            "found_items": found_items,
        },
        reason=reason,
    )

    result_msg = f"You dug a hole in the {original_terrain.value}."
    if found_items:
        result_msg += f" You found: {', '.join(found_items)}!"

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "position": {"x": x, "y": y},
            "original_terrain": original_terrain.value,
            "found_items": found_items,
            "message": result_msg,
        },
    )
