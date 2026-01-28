"""Tool for creatures to see available crafting recipes."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def list_recipes_tool(
    world_id: str,
    category: Optional[str] = None,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    List crafting recipes and see what you can make.

    Shows all recipes, highlighting which ones you can craft right now
    with your current inventory.

    Args:
        world_id: The ID of the world
        category: Optional filter by category (tools, accessories,
                  containers, consumables, materials)
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        List of recipes with ingredients and what you can craft now
    """
    # Import here to avoid circular imports
    import sys

    sys.path.insert(0, "apps/the_hugins")
    from world.crafting import get_all_recipes, get_available_recipes

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

    # Get inventory
    inventory_names = [item.name for item in creature.inventory]

    # Get all recipes and filter by category if specified
    all_recipes = get_all_recipes()
    if category:
        category = category.lower()
        all_recipes = [r for r in all_recipes if r.category == category]

    # Get recipes we can craft now
    craftable = get_available_recipes(inventory_names)
    craftable_names = {r.name for r in craftable}

    # Format recipes
    recipes_list = []
    categories_found = set()

    for recipe in all_recipes:
        categories_found.add(recipe.category)
        can_craft = recipe.name in craftable_names

        recipes_list.append(
            {
                "name": recipe.name,
                "ingredients": recipe.ingredients,
                "result": recipe.result,
                "description": recipe.result_description,
                "category": recipe.category,
                "can_craft_now": can_craft,
            }
        )

    # Build text summary
    summary_parts = ["## Crafting Recipes\n"]

    if not recipes_list:
        if category:
            summary_parts.append(
                f"No recipes found in category '{category}'.\n"
                f"Available categories: tools, accessories, containers, "
                "consumables, materials"
            )
        else:
            summary_parts.append("No recipes available.")
    else:
        # Group by craftable/not craftable
        craftable_list = [r for r in recipes_list if r["can_craft_now"]]
        other_list = [r for r in recipes_list if not r["can_craft_now"]]

        if craftable_list:
            summary_parts.append("### You Can Craft Now:")
            for r in craftable_list:
                ingredients = " + ".join(r["ingredients"])
                summary_parts.append(
                    f"- **{r['name']}**: {ingredients} → {r['description'][:50]}..."
                )
            summary_parts.append("")

        if other_list:
            summary_parts.append("### Other Recipes (need more ingredients):")
            for r in other_list:
                ingredients = " + ".join(r["ingredients"])
                summary_parts.append(f"- {r['name']}: {ingredients}")

    summary_parts.append(f"\nYour inventory: {inventory_names or '(empty)'}")

    return ToolResponse(
        is_error=False,
        content={
            "recipes": recipes_list,
            "total": len(recipes_list),
            "craftable_count": len(
                [r for r in recipes_list if r["can_craft_now"]]
            ),
            "categories": list(categories_found),
            "your_inventory": inventory_names,
            "summary": "\n".join(summary_parts),
        },
    )
