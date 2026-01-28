"""Crafting system for The Hugins."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class Recipe:
    """A crafting recipe."""

    name: str
    ingredients: List[str]  # Item names required (can have duplicates)
    result: str  # Name of crafted item
    result_description: str
    category: str = "general"  # Category for grouping recipes


# All available recipes
RECIPES: Dict[str, Recipe] = {
    # Tools
    "basic_tool": Recipe(
        name="basic_tool",
        ingredients=["stick", "stone"],
        result="basic_tool",
        result_description="A simple tool made from stick and stone. "
        "Useful for digging and building.",
        category="tools",
    ),
    "torch": Recipe(
        name="torch",
        ingredients=["stick", "herbs"],
        result="torch",
        result_description="A torch that provides light in dark areas.",
        category="tools",
    ),
    # Accessories
    "flower_crown": Recipe(
        name="flower_crown",
        ingredients=["flower", "flower", "leaf"],
        result="flower_crown",
        result_description="A beautiful crown made of flowers. "
        "Makes you look friendly and approachable.",
        category="accessories",
    ),
    "feather_charm": Recipe(
        name="feather_charm",
        ingredients=["feather", "feather", "stick"],
        result="feather_charm",
        result_description="A charm made of feathers. "
        "Said to bring good luck when exploring.",
        category="accessories",
    ),
    # Containers
    "seed_pouch": Recipe(
        name="seed_pouch",
        ingredients=["leaf", "leaf", "seed"],
        result="seed_pouch",
        result_description="A pouch containing seeds ready for planting.",
        category="containers",
    ),
    "berry_basket": Recipe(
        name="berry_basket",
        ingredients=["stick", "stick", "leaf"],
        result="berry_basket",
        result_description="A small basket for carrying berries and small items.",
        category="containers",
    ),
    # Consumables
    "herb_bundle": Recipe(
        name="herb_bundle",
        ingredients=["herbs", "herbs", "leaf"],
        result="herb_bundle",
        result_description="A bundle of healing herbs. "
        "Can be used to feel better.",
        category="consumables",
    ),
    "mushroom_stew": Recipe(
        name="mushroom_stew",
        ingredients=["mushroom", "mushroom", "herbs"],
        result="mushroom_stew",
        result_description="A nutritious stew made from mushrooms and herbs.",
        category="consumables",
    ),
    # Building materials
    "rope": Recipe(
        name="rope",
        ingredients=["leaf", "leaf", "leaf"],
        result="rope",
        result_description="A strong rope made from woven leaves. "
        "Useful for building.",
        category="materials",
    ),
    "stone_pile": Recipe(
        name="stone_pile",
        ingredients=["stone", "stone", "pebble"],
        result="stone_pile",
        result_description="A pile of stones ready for construction.",
        category="materials",
    ),
}


def get_available_recipes(inventory_names: List[str]) -> List[Recipe]:
    """
    Get recipes that can be crafted with the current inventory.

    Args:
        inventory_names: List of item names in inventory

    Returns:
        List of recipes that can be crafted
    """
    available = []

    for recipe in RECIPES.values():
        inventory_copy = inventory_names.copy()
        can_craft = True

        for ingredient in recipe.ingredients:
            if ingredient in inventory_copy:
                inventory_copy.remove(ingredient)
            else:
                can_craft = False
                break

        if can_craft:
            available.append(recipe)

    return available


def get_all_recipes() -> List[Recipe]:
    """Get all recipes, grouped by category."""
    return list(RECIPES.values())


def get_recipe(recipe_name: str) -> Optional[Recipe]:
    """Get a specific recipe by name."""
    return RECIPES.get(recipe_name)


def craft_item(
    inventory_names: List[str], recipe_name: str
) -> Optional[Tuple[str, str, List[str]]]:
    """
    Attempt to craft an item.

    Args:
        inventory_names: List of item names in inventory
        recipe_name: Name of the recipe to craft

    Returns:
        Tuple of (result_item_name, description, remaining_inventory)
        or None if crafting failed
    """
    if recipe_name not in RECIPES:
        return None

    recipe = RECIPES[recipe_name]
    inventory_copy = inventory_names.copy()

    # Check and remove ingredients
    for ingredient in recipe.ingredients:
        if ingredient in inventory_copy:
            inventory_copy.remove(ingredient)
        else:
            return None  # Missing ingredient

    return (recipe.result, recipe.result_description, inventory_copy)


def get_missing_ingredients(
    inventory_names: List[str], recipe_name: str
) -> List[str]:
    """
    Get list of missing ingredients for a recipe.

    Args:
        inventory_names: List of item names in inventory
        recipe_name: Name of the recipe

    Returns:
        List of missing ingredient names
    """
    if recipe_name not in RECIPES:
        return []

    recipe = RECIPES[recipe_name]
    inventory_copy = inventory_names.copy()
    missing = []

    for ingredient in recipe.ingredients:
        if ingredient in inventory_copy:
            inventory_copy.remove(ingredient)
        else:
            missing.append(ingredient)

    return missing
