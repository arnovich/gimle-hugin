"""Tool for creatures to use items from their inventory."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


# Item effects when used
USABLE_ITEMS = {
    "herb_bundle": {
        "effect": "healing",
        "description": "You feel rejuvenated and healthy!",
        "consumed": True,
    },
    "mushroom_stew": {
        "effect": "nourishment",
        "description": "The stew warms you and gives you energy!",
        "consumed": True,
    },
    "torch": {
        "effect": "light",
        "description": "The torch illuminates your surroundings.",
        "consumed": False,
    },
    "potion": {
        "effect": "mystery",
        "description": "You feel strange but invigorated...",
        "consumed": True,
    },
    "flower_crown": {
        "effect": "charm",
        "description": "You put on the flower crown. You look delightful!",
        "consumed": False,
    },
    "feather_charm": {
        "effect": "luck",
        "description": "You hold the charm. It feels lucky!",
        "consumed": False,
    },
    "apple": {
        "effect": "snack",
        "description": "Delicious! The apple refreshes you.",
        "consumed": True,
    },
    "berry": {
        "effect": "snack",
        "description": "Sweet berries! A tasty treat.",
        "consumed": True,
    },
}


def use_item_tool(
    world_id: str,
    item_name: str,
    target: Optional[str] = None,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Use an item from your inventory.

    Different items have different effects. Some are consumed when used,
    others can be used multiple times.

    Args:
        world_id: The ID of the world
        item_name: Name of the item to use
        target: Optional target (self, ground, or a creature name)
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Result of using the item
    """
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

    # Check if creature has the item
    has_item = any(item.name == item_name for item in creature.inventory)
    if not has_item:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"You don't have '{item_name}' in your inventory.",
                "your_inventory": [item.name for item in creature.inventory],
            },
        )

    # Check if item is usable
    if item_name not in USABLE_ITEMS:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"'{item_name}' cannot be used directly.",
                "hint": "Some items are materials for crafting or planting.",
                "usable_items": list(USABLE_ITEMS.keys()),
            },
        )

    item_info = USABLE_ITEMS[item_name]

    # Use the item
    if item_info["consumed"]:
        creature.remove_from_inventory(item_name)

    # Log action
    world.action_log.add_action(
        creature_name=creature.name,
        agent_id=agent_id,
        action_type="use_item",
        description=f"Used {item_name}" + (f" on {target}" if target else ""),
        timestamp=world.tick,
        location=creature.position,
        details={
            "item": item_name,
            "effect": item_info["effect"],
            "consumed": item_info["consumed"],
            "target": target,
        },
        reason=reason,
    )

    # Add memory of using item
    world.add_memory_to_creature(
        agent_id=agent_id,
        event_type="used_item",
        description=f"Used {item_name}: {item_info['description']}",
        location=creature.position,
        related_item=item_name,
        importance=4,
    )

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "item": item_name,
            "effect": item_info["effect"],
            "description": item_info["description"],
            "consumed": item_info["consumed"],
            "remaining_inventory": [item.name for item in creature.inventory],
            "message": item_info["description"],
        },
    )
