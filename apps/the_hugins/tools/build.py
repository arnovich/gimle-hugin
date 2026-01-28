"""Tool for creatures to build structures."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


# Structures and their required materials
STRUCTURES = {
    "shelter": {
        "materials": ["stick", "stick", "leaf", "leaf"],
        "description": "A simple shelter that provides protection from the elements.",
    },
    "marker": {
        "materials": ["stone", "stick"],
        "description": "A marker to help remember this location.",
    },
    "bridge": {
        "materials": ["stick", "stick", "stick", "rope"],
        "description": "A small bridge that can span water or holes.",
    },
    "storage": {
        "materials": ["stick", "leaf", "leaf", "berry_basket"],
        "description": "A storage area for keeping items safe.",
    },
    "campfire": {
        "materials": ["stone", "stone", "stick", "stick"],
        "description": "A campfire for warmth and light.",
    },
}


def build_tool(
    world_id: str,
    structure_type: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Build a structure at your current location.

    Requires specific materials in your inventory. The materials
    are consumed when building.

    Args:
        world_id: The ID of the world
        structure_type: Type of structure to build
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Result of building
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

    # Check if structure type is valid
    structure_type = structure_type.lower()
    if structure_type not in STRUCTURES:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Unknown structure type '{structure_type}'.",
                "available_structures": list(STRUCTURES.keys()),
            },
        )

    structure_info = STRUCTURES[structure_type]
    required_materials = structure_info["materials"]

    # Check if creature has required materials
    inventory_names = [item.name for item in creature.inventory]
    missing = []
    temp_inventory = inventory_names.copy()

    for material in required_materials:
        if material in temp_inventory:
            temp_inventory.remove(material)
        else:
            missing.append(material)

    if missing:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Missing materials to build {structure_type}.",
                "required": required_materials,
                "missing": missing,
                "your_inventory": inventory_names,
            },
        )

    # Get current cell
    x, y = creature.position
    cell = world.get_cell(x, y)
    if not cell:
        return ToolResponse(
            is_error=True, content={"error": "Current cell not found"}
        )

    # Check if structure already exists
    if cell.structure:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"A {cell.structure} already exists here.",
                "hint": "Find a different location to build.",
            },
        )

    # Check terrain (can't build on water)
    if cell.terrain == TerrainType.WATER:
        # Bridge can be built on water
        if structure_type != "bridge":
            return ToolResponse(
                is_error=True,
                content={
                    "error": "Cannot build on water.",
                    "hint": "Only bridges can be built over water.",
                },
            )

    # Remove materials from inventory
    for material in required_materials:
        creature.remove_from_inventory(material)

    # Build the structure
    cell.structure = structure_type

    # Log action
    world.action_log.add_action(
        creature_name=creature.name,
        agent_id=agent_id,
        action_type="build",
        description=f"Built {structure_type} at ({x}, {y})",
        timestamp=world.tick,
        location=(x, y),
        details={
            "structure": structure_type,
            "materials_used": required_materials,
        },
        reason=reason,
    )

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "structure": structure_type,
            "description": structure_info["description"],
            "position": {"x": x, "y": y},
            "materials_used": required_materials,
            "message": f"Built a {structure_type}! {structure_info['description']}",
        },
    )


def list_structures_tool(
    world_id: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    List available structures and their required materials.

    Args:
        world_id: The ID of the world
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        List of structures with their materials
    """
    if not stack:
        return ToolResponse(
            is_error=True, content={"error": "Stack not available"}
        )

    agent_id = stack.agent.id
    env_vars = stack.agent.environment.env_vars
    worlds: Dict[str, Any] = env_vars.get("worlds", {})
    world = cast("World", worlds.get(world_id))

    # Get creature inventory for comparison
    inventory_names: List[str] = []
    if world:
        creature = world.get_creature(agent_id)
        if creature:
            inventory_names = [item.name for item in creature.inventory]

    structures_list = []
    for name, info in STRUCTURES.items():
        # Check if can build
        temp_inv = inventory_names.copy()
        can_build = True
        for mat in info["materials"]:
            if mat in temp_inv:
                temp_inv.remove(mat)
            else:
                can_build = False
                break

        structures_list.append(
            {
                "name": name,
                "materials": info["materials"],
                "description": info["description"],
                "can_build_now": can_build,
            }
        )

    return ToolResponse(
        is_error=False,
        content={
            "structures": structures_list,
            "your_inventory": inventory_names,
        },
    )
