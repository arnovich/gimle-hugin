"""Move tool for creatures."""

from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from world.economy import (
    BRIDGE_ENERGY_COST,
    ENERGY_COST_MOVE,
    TERRAIN_ENERGY_COST,
)

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack


def move_tool(
    world_id: str,
    direction: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Move the creature in a direction (north, south, east, west, northeast, northwest, southeast, southwest).

    Args:
        world_id: The ID of the world
        direction: Direction to move (north, south, east, west, northeast, northwest, southeast, southwest)
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Dictionary with new position and what the creature sees
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
    current_pos = world.get_creature_position(agent_id)
    if current_pos is None:
        return ToolResponse(
            is_error=True,
            content={"error": f"Creature {agent_id} not found in world"},
        )

    x, y = current_pos

    # Calculate new position based on direction
    direction_lower = direction.lower()
    direction_map = {
        "north": (0, -1),
        "south": (0, 1),
        "east": (1, 0),
        "west": (-1, 0),
        "northeast": (1, -1),
        "northwest": (-1, -1),
        "southeast": (1, 1),
        "southwest": (-1, 1),
        "n": (0, -1),
        "s": (0, 1),
        "e": (1, 0),
        "w": (-1, 0),
        "ne": (1, -1),
        "nw": (-1, -1),
        "se": (1, 1),
        "sw": (-1, 1),
    }

    if direction_lower not in direction_map:
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    f"Invalid direction '{direction}'. "
                    "Valid directions: north, south, east, west, "
                    "northeast, northwest, southeast, southwest"
                )
            },
        )

    dx, dy = direction_map[direction_lower]
    new_x = x + dx
    new_y = y + dy

    # Check if new position is valid
    if not world.is_valid_position(new_x, new_y):
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Cannot move to ({new_x}, {new_y}) - out of bounds"
            },
        )

    # Determine terrain energy cost for target cell
    target_cell = world.get_cell(new_x, new_y)
    if not target_cell:
        return ToolResponse(
            is_error=True,
            content={"error": "Target cell not found"},
        )

    terrain_name = target_cell.terrain.value
    has_bridge = target_cell.structure == "bridge"
    base_cost = TERRAIN_ENERGY_COST.get(terrain_name, ENERGY_COST_MOVE)

    # Water is impassable unless there is a bridge
    if base_cost < 0:
        if has_bridge:
            energy_cost = BRIDGE_ENERGY_COST
        else:
            return ToolResponse(
                is_error=True,
                content={
                    "error": (
                        "Cannot move into water! "
                        "Build a bridge to cross water."
                    ),
                    "terrain": terrain_name,
                },
            )
    else:
        energy_cost = BRIDGE_ENERGY_COST if has_bridge else base_cost

    # Apply weather modifier to movement cost
    weather_mod = world.weather.get_energy_modifier()
    if weather_mod != 1.0:
        energy_cost = max(1, int(energy_cost * weather_mod))

    # Check energy before moving
    creature = world.get_creature(agent_id)
    if creature and creature.energy < energy_cost:
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    "Too tired to move. " "Eat food or rest to recover energy."
                ),
                "energy": creature.energy,
                "required": energy_cost,
                "terrain": terrain_name,
            },
        )

    # Move the creature
    success = world.move_creature(agent_id, new_x, new_y)
    if not success:
        return ToolResponse(
            is_error=True, content={"error": "Failed to move creature"}
        )

    # Deduct terrain-specific energy cost
    creature = world.get_creature(agent_id)
    if creature:
        creature.remove_energy(energy_cost)

    # Get view of new position
    view_cells = world.get_view(new_x, new_y, radius=1)
    view_data = []
    for cell in view_cells:
        cell_data = {
            "x": cell.x,
            "y": cell.y,
            "terrain": cell.terrain.value,
            "objects": [obj.to_dict() for obj in cell.objects],
        }
        view_data.append(cell_data)

    # Check if this is a new area (for exploration goals)
    creature = world.get_creature(agent_id)
    if creature:
        # Simple check: if we haven't been here recently, it's exploration
        recent_memories = [
            m
            for m in creature.memories
            if m.event_type == "visited_location"
            and m.location == (new_x, new_y)
        ]
        if not recent_memories:
            world.add_memory_to_creature(
                agent_id,
                "visited_location",
                f"Explored location ({new_x}, {new_y})",
                location=(new_x, new_y),
                importance=2,
            )

        # Log the action
        world.action_log.add_action(
            creature_name=creature.name,
            agent_id=agent_id,
            action_type="move",
            description=f"Moved {direction} from ({x}, {y}) to ({new_x}, {new_y})",
            timestamp=world.tick,
            location=(new_x, new_y),
            details={
                "direction": direction,
                "old_position": {"x": x, "y": y},
                "new_position": {"x": new_x, "y": new_y},
            },
            reason=reason,
        )

    # Get current energy for response
    current_energy = creature.energy if creature else 0

    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "old_position": {"x": x, "y": y},
            "new_position": {"x": new_x, "y": new_y},
            "direction": direction,
            "terrain": terrain_name,
            "energy_cost": energy_cost,
            "view": view_data,
            "energy": current_energy,
            "message": (
                f"You moved {direction} to ({new_x}, {new_y}) "
                f"[{terrain_name}, cost: {energy_cost} energy]"
            ),
        },
    )
