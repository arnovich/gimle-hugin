"""HTML renderer for the world with isometric projection."""

import html
import json
from typing import Any, Dict, List, Optional, Tuple

from world.world import World


def world_to_isometric(
    x: int, y: int, tile_size: int = 32
) -> Tuple[float, float]:
    """
    Convert grid coordinates to isometric screen coordinates.

    Args:
        x: Grid x coordinate
        y: Grid y coordinate
        tile_size: Size of tiles in pixels

    Returns:
        Tuple of (screen_x, screen_y) in isometric coordinates
    """
    # Isometric projection: 45-degree rotation
    iso_x = (x - y) * (tile_size / 2)
    iso_y = (x + y) * (tile_size / 4)
    return (iso_x, iso_y)


def generate_world_html(
    world: World,
    view_x: Optional[int] = None,
    view_y: Optional[int] = None,
    view_width: int = 30,
    view_height: int = 30,
    tile_size: int = 64,
    canvas_width: int = 1400,
    canvas_height: int = 1000,
    use_sprites: bool = True,
    sprite_dir: str = "./sprites",
) -> str:
    """
    Generate HTML with canvas-based isometric world visualization.

    Args:
        world: The world to render
        view_x: Optional x coordinate for center of view
        view_y: Optional y coordinate for center of view
        view_width: Width of the view in cells
        view_height: Height of the view in cells
        tile_size: Size of tiles in pixels
        canvas_width: Canvas width in pixels
        canvas_height: Canvas height in pixels

    Returns:
        Complete HTML page as string
    """
    # Determine view bounds - start at (0, 0) so world origin is at top-left
    if view_x is None:
        view_x = 0  # Start at world origin
    if view_y is None:
        view_y = 0  # Start at world origin

    start_x = max(0, view_x)
    end_x = min(world.width, view_x + view_width)
    start_y = max(0, view_y)
    end_y = min(world.height, view_y + view_height)

    # Terrain colors - prettier, more vibrant
    terrain_colors: Dict[str, str] = {
        "grass": "#8bc34a",  # Brighter green
        "water": "#03a9f4",  # Brighter blue
        "stone": "#b0bec5",  # Lighter gray
        "sand": "#ffeb3b",  # Bright yellow
        "dirt": "#a1887f",  # Warmer brown
        "forest": "#4caf50",  # Vibrant green
    }

    # Load sprite manager if using sprites
    sprite_paths: Dict[str, str] = {}
    if use_sprites:
        try:
            from world.sprite_manager import get_sprite_manager

            sprite_manager = get_sprite_manager(sprite_dir)

            # Get sprite paths for terrain
            for terrain_type in terrain_colors.keys():
                sprite_path = sprite_manager.get_terrain_sprite(
                    terrain_type, use_http_url=True
                )
                if sprite_path:
                    sprite_paths[f"terrain_{terrain_type}"] = sprite_path

            # Get sprite paths for creatures
            for creature in world.creatures.values():
                sprite_path = sprite_manager.get_creature_sprite(
                    creature.name,
                    use_http_url=True,
                    description=creature.description,
                    personality=creature.personality,
                )
                if sprite_path:
                    sprite_paths[f"creature_{creature.name.lower()}"] = (
                        sprite_path
                    )
        except Exception as e:
            # If sprite loading fails, continue without sprites
            import logging

            logging.warning(f"Sprite loading failed: {e}")
            use_sprites = False

    # Get last action for each creature
    creature_last_actions: Dict[str, Dict[str, Any]] = {}
    for agent_id, creature in world.creatures.items():
        # Get most recent action by this creature
        creature_actions = world.action_log.get_actions_by_creature(
            creature.name, count=1
        )
        if creature_actions:
            last_action = creature_actions[-1]
            creature_last_actions[agent_id] = {
                "description": last_action.description,
                "action_type": last_action.action_type,
                "timestamp": last_action.timestamp,
                "reason": last_action.reason,
            }

    # Collect all cells, creatures, and items to render
    cells_data: List[Dict[str, Any]] = []
    creatures_data: List[Dict[str, Any]] = []
    items_data: List[Dict[str, Any]] = []

    for y_pos in range(start_y, end_y):
        for x_pos in range(start_x, end_x):
            cell = world.get_cell(x_pos, y_pos)
            if not cell:
                continue

            # Calculate relative position within view window
            rel_x = x_pos - start_x
            rel_y = y_pos - start_y

            # Convert to isometric coordinates
            iso_x, iso_y = world_to_isometric(rel_x, rel_y, tile_size)

            # Position so that (start_x, start_y) appears at top-left
            screen_x = iso_x + (canvas_width // 4)
            screen_y = iso_y + (canvas_height // 8)

            # Terrain
            terrain_color = terrain_colors.get(cell.terrain.value, "#cccccc")

            # Get neighbor terrain info for transitions
            neighbors: Dict[str, Optional[Dict[str, str]]] = {}
            for direction, (dx, dy) in [
                ("north", (0, -1)),
                ("south", (0, 1)),
                ("east", (1, 0)),
                ("west", (-1, 0)),
            ]:
                neighbor_cell = world.get_cell(x_pos + dx, y_pos + dy)
                if neighbor_cell:
                    neighbor_terrain = neighbor_cell.terrain.value
                    neighbor_color = terrain_colors.get(
                        neighbor_terrain, "#cccccc"
                    )
                    neighbors[direction] = {
                        "terrain": neighbor_terrain,
                        "color": neighbor_color,
                    }
                else:
                    neighbors[direction] = None

            cell_entry = {
                "x": screen_x,
                "y": screen_y,
                "terrain": cell.terrain.value,
                "color": terrain_color,
                "world_x": x_pos,
                "world_y": y_pos,
                "structure": cell.structure,
                "neighbors": neighbors,
            }
            if cell.lit:
                cell_entry["lit"] = True
            if cell.structure == "storage":
                cell_entry["item_count"] = sum(
                    1 for o in cell.objects if o.type.value == "item"
                )
            cells_data.append(cell_entry)

            # Items
            for obj in cell.objects:
                if obj.type.value == "item":
                    items_data.append(
                        {
                            "x": screen_x,
                            "y": screen_y - 10,
                            "name": obj.name,
                            "world_x": x_pos,
                            "world_y": y_pos,
                        }
                    )
                elif obj.type.value == "creature":
                    creature_state = world.get_creature(obj.id)
                    if creature_state is not None:
                        cx, cy = creature_state.position
                        creature_rel_x = cx - start_x
                        creature_rel_y = cy - start_y
                        creature_iso_x, creature_iso_y = world_to_isometric(
                            creature_rel_x,
                            creature_rel_y,
                            tile_size,
                        )
                        creature_screen_x = creature_iso_x + (canvas_width // 4)
                        creature_screen_y = creature_iso_y + (
                            canvas_height // 8
                        )

                        creature_last_action: Optional[Dict[str, Any]] = (
                            creature_last_actions.get(creature_state.agent_id)
                        )
                        creatures_data.append(
                            {
                                "x": creature_screen_x,
                                "y": creature_screen_y - 15,
                                "name": creature_state.name,
                                "agent_id": creature_state.agent_id,
                                "world_x": cx,
                                "world_y": cy,
                                "color": get_creature_color(
                                    creature_state.name
                                ),
                                "last_action": creature_last_action,
                                "energy": creature_state.energy,
                                "max_energy": 100,
                                "money": creature_state.money,
                                "warmth": creature_state.warmth,
                                "mood": creature_state.mood,
                            }
                        )

    # Serialize dynamic data for embedding in inline script
    world_data_json = json.dumps(
        {
            "cells": cells_data,
            "creatures": creatures_data,
            "items": items_data,
            "spritePaths": sprite_paths,
            "useSprites": use_sprites,
            "worldTick": world.tick,
            "dayPhase": world.get_day_phase(),
            "temperature": world.get_temperature(),
            "weather": world.weather.current.value,
            "viewCenterX": view_x,
            "viewCenterY": view_y,
            "viewStartX": start_x,
            "viewStartY": start_y,
            "worldWidth": world.width,
            "worldHeight": world.height,
            "tileSize": tile_size,
            "canvasWidth": canvas_width,
            "canvasHeight": canvas_height,
        }
    ).replace("</script>", r"<\/script>")

    # Generate HTML with external CSS/JS and inline data
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Hugins: {world.id}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/world.css">
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>The Hugins</h1>
            <div class="header-info">
                <span>Size: {world.width}&times;{world.height}</span>
                <span>Tick: <span id="tick">{world.tick}</span></span>
                <span id="dayPhaseDisplay">{world.get_day_phase().capitalize()}</span>
                <span id="temperatureDisplay">{world.get_temperature()}&deg;C</span>
                <span id="weatherDisplay">{world.weather.current.value.capitalize()}</span>
                <span>Creatures: {len(world.creatures)}</span>
            </div>
            <button class="leave-btn" onclick="leaveWorld()">Leave World</button>
        </div>

        <div class="shortcuts-bar">
            <span><kbd>+</kbd> <kbd>-</kbd> Zoom</span>
            <span><kbd>&#8592;</kbd><kbd>&#8593;</kbd><kbd>&#8595;</kbd><kbd>&#8594;</kbd> Pan</span>
            <span>Click creature to talk</span>
            <span>Drag creature to move</span>
            <span><kbd>M</kbd> Minimap</span>
            <span><kbd>?</kbd> All shortcuts</span>
            <span class="speed-control">
                Speed: <input type="range" id="speedSlider" min="0.1" max="5" value="1" step="0.1" oninput="updateSpeed(this.value)">
                <span id="speedValue">1.0s</span>
            </span>
            <span class="legend-toggle" onclick="toggleLegend()">Legend &#9660;</span>
        </div>
        <div class="legend-bar" id="legendBar" style="display: none;">
            {generate_legend_html(terrain_colors)}
        </div>

        <div class="main-content">
            <div class="canvas-container">
                <canvas id="worldCanvas"></canvas>
                <canvas id="minimapCanvas" width="150" height="150"></canvas>
                <div class="tooltip" id="tooltip"></div>
                <div class="simulation-paused" id="simulationPaused">
                    Simulation Paused &mdash; Waiting for human interaction
                </div>
            </div>

            <div class="sidebar">
                <h2>Creatures</h2>
                <div id="creaturesList">
                    {generate_creatures_html(world)}
                </div>

                <div class="actions-log">
                    <h2>Recent Actions</h2>
                    <div class="action-filters" id="actionFilters"></div>
                    <div id="actionsList">
                        {generate_actions_html(world, count=30)}
                    </div>
                </div>

            </div>
        </div>
    </div>

    <!-- Interaction Modal -->
    <div class="interaction-modal" id="interactionModal">
        <div class="interaction-bubble">
            <h3 id="interactionCreatureName">Interact with Creature</h3>
            <p id="interactionPrompt">What would you like to say?</p>
            <textarea id="interactionInput" placeholder="Type your message here..."></textarea>
            <div class="button-group">
                <button class="btn-cancel" onclick="cancelInteraction()">Cancel</button>
                <button class="btn-send" onclick="sendInteraction()">Send</button>
            </div>
        </div>
    </div>

    <!-- Help Overlay -->
    <div id="helpOverlay" class="help-overlay" style="display: none;">
        <div class="help-content">
            <h2>Keyboard Controls</h2>
            <div class="help-section">
                <h3>Navigation</h3>
                <div class="help-row"><kbd>&#8593;</kbd><kbd>&#8595;</kbd><kbd>&#8592;</kbd><kbd>&#8594;</kbd> or <kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> Pan the map</div>
                <div class="help-row"><kbd>Shift</kbd> + movement keys: Fast pan</div>
            </div>
            <div class="help-section">
                <h3>Zoom</h3>
                <div class="help-row"><kbd>+</kbd> / <kbd>=</kbd> Zoom in</div>
                <div class="help-row"><kbd>-</kbd> / <kbd>_</kbd> Zoom out</div>
            </div>
            <div class="help-section">
                <h3>Creatures</h3>
                <div class="help-row">Click creature: Talk to them</div>
                <div class="help-row">Drag creature: Move them (they get notified!)</div>
            </div>
            <div class="help-section">
                <h3>Other</h3>
                <div class="help-row"><kbd>M</kbd> Toggle minimap</div>
                <div class="help-row"><kbd>R</kbd> or <kbd>Home</kbd> Reset view</div>
                <div class="help-row"><kbd>?</kbd> Toggle this help</div>
            </div>
            <button class="help-close" onclick="toggleHelp()">Close (or press ?)</button>
        </div>
    </div>

    <!-- Dynamic world data -->
    <script>
        window.WORLD_DATA = {world_data_json};
    </script>
    <!-- External JS -->
    <script src="/static/js/world.js"></script>
</body>
</html>
"""

    return html


def get_creature_color(name: str) -> str:
    """Get a color for a creature based on its name."""
    colors = [
        "#e74c3c",
        "#3498db",
        "#2ecc71",
        "#f39c12",
        "#9b59b6",
        "#1abc9c",
        "#e67e22",
        "#34495e",
        "#c0392b",
        "#16a085",
    ]
    hash_val = hash(name) % len(colors)
    return colors[abs(hash_val)]


def generate_creatures_html(world: World) -> str:
    """Generate HTML for creatures sidebar."""
    html_parts = []
    for creature in world.creatures.values():
        x, y = creature.position

        # Generate inventory HTML
        if creature.inventory:
            inventory_items = "".join(
                [
                    f'<div class="inventory-item">{html.escape(item.name)}</div>'
                    for item in creature.inventory
                ]
            )
            inventory_html = (
                f'<div class="inventory-items">{inventory_items}</div>'
            )
        else:
            inventory_html = '<div class="inventory-empty">Empty</div>'

        goals_html = ""
        for goal in creature.goals:
            done = " (done)" if goal.completed else ""
            goals_html += f'<div class="creature-detail">- {html.escape(goal.type.value)}{done}</div>'

        last_action_html = ""
        last_actions = world.action_log.get_actions_by_creature(
            creature.name, count=1
        )
        if last_actions:
            la = last_actions[-1]
            reason_html = (
                f'<div class="creature-detail action-reason"><em>{html.escape(la.reason)}</em></div>'
                if la.reason
                else ""
            )
            last_action_html = f'<div class="creature-detail" style="margin-top:6px;"><strong>Last Action:</strong> {html.escape(la.description)}</div>{reason_html}'

        # Energy bar color based on percentage
        energy_percent = creature.energy / 100
        if energy_percent > 0.5:
            energy_color = "#4caf50"  # Green
        elif energy_percent > 0.25:
            energy_color = "#ff9800"  # Orange
        else:
            energy_color = "#f44336"  # Red

        # Pending trades info
        trades_count = len(creature.pending_trades)
        trades_html = ""
        if trades_count > 0:
            trades_html = f'<div class="creature-detail" style="color: #2196f3;"><strong>Pending Trades:</strong> {trades_count}</div>'

        html_parts.append(
            f"""
            <div class="creature-info" onclick="toggleCreature(this, '{html.escape(creature.agent_id)}')">
                <h3>{html.escape(creature.name)} <span class="expand-indicator">&#9654;</span></h3>
                <div class="creature-stats">
                    <div class="stat-bar">
                        <span class="stat-label">Energy</span>
                        <div class="stat-bar-bg">
                            <div class="stat-bar-fill" style="width: {creature.energy}%; background: {energy_color};"></div>
                        </div>
                        <span class="stat-value">{creature.energy}</span>
                    </div>
                    <div class="stat-bar">
                        <span class="stat-label">Warmth</span>
                        <div class="stat-bar-bg">
                            <div class="stat-bar-fill" style="width: {creature.warmth * 5}%; background: #ff9800;"></div>
                        </div>
                        <span class="stat-value">{creature.warmth}</span>
                    </div>
                    <div class="stat-row">
                        <div class="stat-money">
                            <span style="color: #ffd700;">$</span> {creature.money}
                        </div>
                        <div class="stat-mood">
                            Mood: {creature.mood.capitalize()}
                        </div>
                    </div>
                </div>
                <div class="creature-detail"><strong>Position:</strong> ({x}, {y})</div>
                <div class="creature-details-full">
                    {last_action_html}
                    {trades_html}
                    <div class="creature-detail"><strong>Description:</strong> {html.escape(creature.description)}</div>
                    <div class="creature-detail"><strong>Personality:</strong> {html.escape(creature.personality)}</div>
                    {f'<div class="creature-detail" style="margin-top:6px;"><strong>Goals:</strong></div>{goals_html}' if goals_html else ''}
                    <div class="inventory">
                        <div class="creature-detail"><strong>Inventory ({len(creature.inventory)}):</strong></div>
                        {inventory_html}
                    </div>
                </div>
            </div>
        """
        )
    return "".join(html_parts)


def generate_actions_html(world: World, count: int = 15) -> str:
    """Generate HTML for actions log."""
    recent_actions = world.action_log.get_recent_actions(count)
    if not recent_actions:
        return "<div class='action-item'>No actions yet...</div>"

    html_parts = []
    for action in reversed(recent_actions):  # Most recent first
        reason_html = (
            f'<div class="action-reason"><em>{html.escape(action.reason)}</em></div>'
            if action.reason
            else ""
        )
        html_parts.append(
            f"""
            <div class="action-item {html.escape(action.action_type)}">
                <div>
                    <span class="action-creature">{html.escape(action.creature_name)}</span>
                    <span class="action-description">{html.escape(action.description)}</span>
                </div>
                {reason_html}
                <div class="action-time">Tick {action.timestamp}</div>
            </div>
        """
        )
    return "".join(html_parts)


def generate_legend_html(terrain_colors: Dict[str, str]) -> str:
    """Generate HTML for terrain legend."""
    html_parts = []
    for terrain, color in terrain_colors.items():
        html_parts.append(
            f"""
            <div class="legend-item">
                <div class="legend-color" style="background: {color};"></div>
                <span>{terrain.capitalize()}</span>
            </div>
        """
        )
    return "".join(html_parts)
