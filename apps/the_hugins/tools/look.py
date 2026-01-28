"""Look tool for creatures to see their surroundings."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

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

    # Get 3x3 view (radius=1 means 1 cell in each direction)
    view_cells = world.get_view(x, y, radius=1)

    # Organize cells into a grid for easier visualization
    view_data = []
    for cell in view_cells:
        cell_data = {
            "x": cell.x,
            "y": cell.y,
            "terrain": cell.terrain.value,
            "objects": [obj.to_dict() for obj in cell.objects],
            "is_you": cell.x == x and cell.y == y,
        }
        view_data.append(cell_data)

    # Create a text description
    description_parts = []
    for cell in view_cells:
        if cell.x == x and cell.y == y:
            location = "You are here"
            description_parts.append(f"{location}: {cell.terrain.value}")
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

            description_parts.append(f"{location}: {cell.terrain.value}")

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

    return ToolResponse(
        is_error=False,
        content={
            "position": {"x": x, "y": y},
            "view": view_data,
            "description": (
                "\n".join(description_parts)
                if description_parts
                else "You see nothing around you."
            ),
        },
    )
