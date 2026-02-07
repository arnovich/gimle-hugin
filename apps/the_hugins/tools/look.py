"""Look tool for creatures to see their surroundings."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from world.economy import BRIDGE_ENERGY_COST, TERRAIN_ENERGY_COST
from world.structures import STRUCTURE_EFFECTS

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def look_tool(
    world_id: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Look around and see a 3x3 grid of cells centered on your position.

    Args:
        world_id: The ID of the world
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Dictionary with a 3x3 view of cells around the creature
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

    # Get current position
    position = world.get_creature_position(agent_id)
    if position is None:
        return ToolResponse(
            is_error=True,
            content={"error": f"Creature {agent_id} not found in world"},
        )

    x, y = position

    # Marker extends vision to 5x5
    current_cell = world.get_cell(x, y)
    radius = 1
    if current_cell and current_cell.structure in STRUCTURE_EFFECTS:
        override = STRUCTURE_EFFECTS[current_cell.structure].get("look_radius")
        if override:
            radius = override

    # Weather may reduce visibility (e.g. fog)
    radius = max(1, radius + world.weather.get_visibility_modifier())

    view_cells = world.get_view(x, y, radius=radius)

    # Organize cells into a grid for easier visualization
    view_data = []
    for cell in view_cells:
        terrain_name = cell.terrain.value
        has_bridge = cell.structure == "bridge"
        base_cost = TERRAIN_ENERGY_COST.get(terrain_name, 1)
        if base_cost < 0:
            move_cost = BRIDGE_ENERGY_COST if has_bridge else "impassable"
        else:
            move_cost = BRIDGE_ENERGY_COST if has_bridge else base_cost

        cell_data = {
            "x": cell.x,
            "y": cell.y,
            "terrain": terrain_name,
            "energy_cost": move_cost,
            "objects": [obj.to_dict() for obj in cell.objects],
            "is_you": cell.x == x and cell.y == y,
        }
        if cell.structure:
            cell_data["structure"] = cell.structure
            effects = STRUCTURE_EFFECTS.get(cell.structure, {})
            if "description" in effects:
                cell_data["structure_effect"] = effects["description"]
        view_data.append(cell_data)

    # Create a text description
    description_parts = []
    for cell in view_cells:
        terrain_name = cell.terrain.value
        has_bridge = cell.structure == "bridge"
        base_cost = TERRAIN_ENERGY_COST.get(terrain_name, 1)
        if base_cost < 0:
            cost_str = (
                f" (bridge, cost:{BRIDGE_ENERGY_COST})"
                if has_bridge
                else " (impassable)"
            )
        else:
            cost = BRIDGE_ENERGY_COST if has_bridge else base_cost
            cost_str = f" (cost:{cost})" if cost > 1 else ""

        if cell.x == x and cell.y == y:
            location = "You are here"
            description_parts.append(f"{location}: {terrain_name}")
        else:
            dx = cell.x - x
            dy = cell.y - y
            if dx == 0 and dy == -1:
                location = "North"
            elif dx == 0 and dy == 1:
                location = "South"
            elif dx == 1 and dy == 0:
                location = "East"
            elif dx == -1 and dy == 0:
                location = "West"
            elif dx == 1 and dy == -1:
                location = "Northeast"
            elif dx == -1 and dy == -1:
                location = "Northwest"
            elif dx == 1 and dy == 1:
                location = "Southeast"
            elif dx == -1 and dy == 1:
                location = "Southwest"
            else:
                location = f"({cell.x}, {cell.y})"

            description_parts.append(f"{location}: {terrain_name}{cost_str}")

        if cell.structure:
            effects = STRUCTURE_EFFECTS.get(cell.structure, {})
            effect_note = (
                f" - {effects['description']}"
                if "description" in effects
                else ""
            )
            description_parts.append(
                f"  Structure: {cell.structure}{effect_note}"
            )
        if cell.objects:
            obj_names = [obj.name for obj in cell.objects]
            description_parts.append(f"  Objects: {', '.join(obj_names)}")

    # Log the action (optional - might be too verbose)
    creature = world.get_creature(agent_id)
    if creature:
        world.action_log.add_action(
            creature_name=creature.name,
            agent_id=agent_id,
            action_type="look",
            description=f"Looked around at ({x}, {y})",
            timestamp=world.tick,
            location=(x, y),
            reason=reason,
        )

    grid_size = radius * 2 + 1
    return ToolResponse(
        is_error=False,
        content={
            "position": {"x": x, "y": y},
            "view_radius": radius,
            "view_size": f"{grid_size}x{grid_size}",
            "view": view_data,
            "description": (
                "\n".join(description_parts)
                if description_parts
                else "You see nothing around you."
            ),
        },
    )
