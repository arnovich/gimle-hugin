"""Text renderer for the world."""

from typing import Dict, Optional

from world.world import World


def render_world_text(
    world: World,
    view_x: Optional[int] = None,
    view_y: Optional[int] = None,
    view_width: int = 20,
    view_height: int = 20,
) -> str:
    """
    Render a portion of the world as text.

    Args:
        world: The world to render
        view_x: Optional x coordinate for center of view (defaults to center of world)
        view_y: Optional y coordinate for center of view (defaults to center of world)
        view_width: Width of the view in cells
        view_height: Height of the view in cells

    Returns:
        String representation of the world
    """
    # Determine view bounds
    if view_x is None:
        view_x = world.width // 2
    if view_y is None:
        view_y = world.height // 2

    start_x = max(0, view_x - view_width // 2)
    end_x = min(world.width, view_x + view_width // 2)
    start_y = max(0, view_y - view_height // 2)
    end_y = min(world.height, view_y + view_height // 2)

    # Terrain symbols
    terrain_symbols: Dict[str, str] = {
        "grass": ".",
        "water": "~",
        "stone": "#",
        "sand": ":",
        "dirt": ",",
        "forest": "T",
    }

    lines = []
    lines.append(f"World: {world.id} (Tick: {world.tick})")
    lines.append(f"View: ({start_x}, {start_y}) to ({end_x-1}, {end_y-1})")
    lines.append("")

    # Create a grid representation
    for y in range(start_y, end_y):
        line_parts = []
        for x in range(start_x, end_x):
            cell = world.get_cell(x, y)
            if not cell:
                line_parts.append(" ")
                continue

            # Determine what to display
            symbol = terrain_symbols.get(cell.terrain.value, "?")

            # Check for creatures
            creatures_here = [
                obj for obj in cell.objects if obj.type.value == "creature"
            ]
            items_here = [
                obj for obj in cell.objects if obj.type.value == "item"
            ]

            if creatures_here:
                # Show first creature's initial
                creature_obj = creatures_here[0]
                symbol = creature_obj.name[0].upper()
            elif items_here:
                # Show item count
                symbol = str(len(items_here)) if len(items_here) < 10 else "*"

            line_parts.append(symbol)

        lines.append("".join(line_parts))

    # Add legend
    lines.append("")
    lines.append("Legend:")
    lines.append(
        "  . = grass, ~ = water, # = stone, : = sand, , = dirt, T = forest"
    )
    lines.append(
        "  Numbers = item count, Letters = creatures (first letter of name)"
    )

    # Add creature info
    lines.append("")
    lines.append("Creatures:")
    for creature in world.creatures.values():
        x, y = creature.position
        inventory_str = (
            f" (carrying: {', '.join([item.name for item in creature.inventory])})"
            if creature.inventory
            else ""
        )
        lines.append(f"  {creature.name} at ({x}, {y}){inventory_str}")

    return "\n".join(lines)


def render_world_minimap(
    world: World,
    width: int = 50,
    height: int = 50,
) -> str:
    """
    Render a minimap of the entire world.

    Args:
        world: The world to render
        width: Width of minimap (will scale world to fit)
        height: Height of minimap (will scale world to fit)

    Returns:
        String representation of the minimap
    """
    terrain_symbols: Dict[str, str] = {
        "grass": ".",
        "water": "~",
        "stone": "#",
        "sand": ":",
        "dirt": ",",
        "forest": "T",
    }

    lines = []
    lines.append(f"World Minimap: {world.id} ({world.width}x{world.height})")
    lines.append("")

    # Scale factor
    scale_x = world.width / width
    scale_y = world.height / height

    for display_y in range(height):
        line_parts = []
        for display_x in range(width):
            # Map display coordinates to world coordinates
            world_x = int(display_x * scale_x)
            world_y = int(display_y * scale_y)

            cell = world.get_cell(world_x, world_y)
            if not cell:
                line_parts.append(" ")
                continue

            symbol = terrain_symbols.get(cell.terrain.value, "?")

            # Check for creatures (show as *)
            creatures_here = [
                obj for obj in cell.objects if obj.type.value == "creature"
            ]
            if creatures_here:
                symbol = "*"

            line_parts.append(symbol)

        lines.append("".join(line_parts))

    lines.append("")
    lines.append(
        "Legend: . = grass, ~ = water, # = stone, : = sand, , = dirt, T = forest, * = creature"
    )

    return "\n".join(lines)
