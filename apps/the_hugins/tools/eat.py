"""Eat tool for consuming food to restore energy."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse
from world.economy import FOOD_ENERGY, MAX_ENERGY

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def eat_tool(
    world_id: str,
    item_name: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Eat a food item from inventory to restore energy.

    Args:
        world_id: The ID of the world
        item_name: Name of the food item to eat
        reason: Why you are performing this action
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Dictionary with success status and energy information
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

    # Check if item is food
    if item_name not in FOOD_ENERGY:
        available_foods = [
            f"{name} (+{energy})"
            for name, energy in FOOD_ENERGY.items()
        ]
        return ToolResponse(
            is_error=True,
            content={
                "error": f"'{item_name}' is not edible food.",
                "edible_items": available_foods,
            },
        )

    # Check if creature has item in inventory
    item = creature.remove_from_inventory(item_name)
    if not item:
        inventory_names = [obj.name for obj in creature.inventory]
        food_in_inventory = [n for n in inventory_names if n in FOOD_ENERGY]
        return ToolResponse(
            is_error=True,
            content={
                "error": f"You don't have '{item_name}' in your inventory.",
                "food_in_inventory": food_in_inventory,
                "all_inventory": inventory_names,
            },
        )

    # Restore energy
    energy_value = FOOD_ENERGY[item_name]
    old_energy = creature.energy
    actual_gained = creature.add_energy(energy_value)

    # Add memory
    world.add_memory_to_creature(
        agent_id,
        "ate_food",
        f"Ate {item_name} and gained {actual_gained} energy",
        location=creature.position,
        related_item=item_name,
        importance=3,
    )

    # Log the action
    world.action_log.add_action(
        creature_name=creature.name,
        agent_id=agent_id,
        action_type="eat",
        description=f"Ate {item_name} and gained {actual_gained} energy",
        timestamp=world.tick,
        location=creature.position,
        details={
            "item": item_name,
            "energy_value": energy_value,
            "energy_gained": actual_gained,
            "old_energy": old_energy,
            "new_energy": creature.energy,
        },
        reason=reason,
    )

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "item_eaten": item_name,
            "energy_value": energy_value,
            "energy_gained": actual_gained,
            "old_energy": old_energy,
            "new_energy": creature.energy,
            "max_energy": MAX_ENERGY,
            "message": (
                f"You ate the {item_name} and gained {actual_gained} energy. "
                f"Energy: {creature.energy}/{MAX_ENERGY}"
            ),
        },
    )
