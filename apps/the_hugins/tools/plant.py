"""Tool for creatures to plant seeds."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


# Seeds and their growth times (in world ticks)
SEED_GROWTH_TIME = {
    "seed": 10,
    "herb_seed": 8,
    "flower_seed": 6,
    "berry_seed": 12,
    "mushroom_spore": 5,
    "acorn": 15,
}

# Items that can be planted
PLANTABLE_ITEMS = list(SEED_GROWTH_TIME.keys())


def plant_tool(
    world_id: str,
    seed_name: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Plant a seed from your inventory at your current location.

    The seed will grow into a harvestable item after some time.
    You can only plant in tilled soil or holes.

    Args:
        world_id: The ID of the world
        seed_name: Name of the seed to plant from your inventory
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Result of planting
    """
    # Import here to avoid circular imports
    import sys

    sys.path.insert(0, "apps/the_hugins")
    from world.cell import TerrainType

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

    # Check if seed is plantable
    if seed_name not in PLANTABLE_ITEMS:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"'{seed_name}' cannot be planted.",
                "plantable_items": PLANTABLE_ITEMS,
            },
        )

    # Check if creature has the seed
    has_seed = any(item.name == seed_name for item in creature.inventory)
    if not has_seed:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"You don't have a '{seed_name}' in your inventory.",
                "your_inventory": [item.name for item in creature.inventory],
            },
        )

    # Get current cell
    x, y = creature.position
    cell = world.get_cell(x, y)
    if not cell:
        return ToolResponse(
            is_error=True, content={"error": "Current cell not found"}
        )

    # Check if terrain is plantable
    plantable_terrain = {
        TerrainType.TILLED,
        TerrainType.HOLE,
        TerrainType.DIRT,
        TerrainType.GRASS,
    }
    if cell.terrain not in plantable_terrain:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Cannot plant in {cell.terrain.value}.",
                "hint": "Try planting in dirt, grass, tilled soil, or a hole.",
            },
        )

    # Check if something is already planted
    if cell.planted_seed:
        return ToolResponse(
            is_error=True,
            content={
                "error": "Something is already planted here.",
                "planted": cell.planted_seed,
            },
        )

    # Remove seed from inventory
    creature.remove_from_inventory(seed_name)

    # Plant the seed
    cell.planted_seed = seed_name
    cell.terrain = TerrainType.PLANTED
    growth_time = SEED_GROWTH_TIME.get(seed_name, 10)
    cell.plant_growth_tick = world.tick + growth_time

    # Log action
    world.action_log.add_action(
        creature_name=creature.name,
        agent_id=agent_id,
        action_type="plant",
        description=f"Planted {seed_name} at ({x}, {y})",
        timestamp=world.tick,
        location=(x, y),
        details={
            "seed": seed_name,
            "growth_tick": cell.plant_growth_tick,
            "growth_time": growth_time,
        },
        reason=reason,
    )

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "planted": seed_name,
            "position": {"x": x, "y": y},
            "will_grow_at_tick": cell.plant_growth_tick,
            "ticks_until_ready": growth_time,
            "message": f"Planted {seed_name}! It will be ready in {growth_time} ticks.",
        },
    )
