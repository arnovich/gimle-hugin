"""Crafting tool for creatures to combine items."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def craft_tool(
    world_id: str,
    recipe_name: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Craft a new item from ingredients in your inventory.

    Combines items according to a recipe to create something new.
    The ingredients are consumed in the process.

    Args:
        world_id: The ID of the world
        recipe_name: Name of the recipe to craft (e.g., 'basic_tool')
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Result of the crafting attempt
    """
    # Import here to avoid circular imports
    import sys

    sys.path.insert(0, "apps/the_hugins")
    from world.crafting import (
        craft_item,
        get_available_recipes,
        get_missing_ingredients,
        get_recipe,
    )
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

    # Check if recipe exists
    recipe = get_recipe(recipe_name)
    if not recipe:
        available = get_available_recipes(
            [item.name for item in creature.inventory]
        )
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Unknown recipe '{recipe_name}'.",
                "hint": "Use `list_recipes` to see available recipes.",
                "craftable_now": [r.name for r in available],
            },
        )

    # Get inventory item names
    inventory_names = [item.name for item in creature.inventory]

    # Check for missing ingredients
    missing = get_missing_ingredients(inventory_names, recipe_name)
    if missing:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Cannot craft '{recipe_name}'. Missing ingredients.",
                "missing": missing,
                "needed": recipe.ingredients,
                "your_inventory": inventory_names,
            },
        )

    # Attempt to craft
    result = craft_item(inventory_names, recipe_name)
    if not result:
        return ToolResponse(
            is_error=True,
            content={"error": "Crafting failed unexpectedly."},
        )

    crafted_name, crafted_desc, remaining = result

    # Remove used ingredients from creature's actual inventory
    for ingredient in recipe.ingredients:
        creature.remove_from_inventory(ingredient)

    # Create and add crafted item
    crafted_obj = Object(
        name=crafted_name,
        type=ObjectType.ITEM,
        description=crafted_desc,
        id=f"crafted_{crafted_name}_{world.tick}",
    )
    creature.add_to_inventory(crafted_obj)

    # Add memory of crafting
    creature.add_memory(
        type(creature).Memory(
            event_type="crafted_item",
            description=f"Crafted {crafted_name} from {recipe.ingredients}",
            importance=6,
            tick=world.tick,
        )
        if hasattr(type(creature), "Memory")
        else None
    )

    # Log action
    world.action_log.add_action(
        creature_name=creature.name,
        agent_id=agent_id,
        action_type="craft",
        description=f"Crafted {crafted_name} from {recipe.ingredients}",
        timestamp=world.tick,
        location=creature.position,
        details={
            "recipe": recipe_name,
            "result": crafted_name,
            "ingredients_used": recipe.ingredients,
        },
        reason=reason,
    )

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "crafted": crafted_name,
            "description": crafted_desc,
            "ingredients_used": recipe.ingredients,
            "inventory": [item.name for item in creature.inventory],
            "message": f"Successfully crafted {crafted_name}! {crafted_desc}",
        },
    )
