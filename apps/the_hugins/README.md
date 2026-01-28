# The Hugins - Autonomous Creature World

A multi-agent simulation where autonomous creatures live in a shared 2D grid world. Each creature is a Hugin agent that can perceive its environment, move around, pick up items, and interact with other creatures.

## Quick Start

```bash
# Basic run - opens world visualization automatically
uv run hugin app the_hugins

# With agent monitor for debugging creature behavior
uv run hugin app the_hugins -- --monitor

# Custom ports
uv run hugin app the_hugins -- --monitor --world-port 8000 --monitor-port 8001
```

The world visualization opens at `http://localhost:8000/` where you can create a new world or load an existing session. With `--monitor`, an agent monitor opens at `http://localhost:8001/` showing creature decision-making, tool calls, and LLM interactions.

## How It Works

A 50x50 grid world is generated with mixed terrain (grass, water, stone, sand, dirt, forest) and scattered items. Multiple creatures spawn into the world, each with their own personality and goals. Creatures:

- **See** a 3x3 grid around them
- **Move** in 8 directions (including diagonals)
- **Pick up and drop** items
- **Talk** to nearby creatures (within 2 cells)
- **Remember** past events and locations
- **Form relationships** based on interactions

All creature actions go through tools, making them fully observable in the agent monitor.

## Tools

| Tool | Description |
|------|-------------|
| `get_position` | Get current (x, y) coordinates |
| `look` | See 3x3 grid of terrain, objects, and creatures |
| `move` | Move in a direction (n/s/e/w/ne/nw/se/sw) |
| `take` | Pick up an item from current or adjacent cell |
| `drop` | Drop an item from inventory |
| `say` | Say something heard by creatures within 2 cells |
| `talk_to` | Talk directly to a nearby creature |

## Visualization

Creatures get **procedurally generated SVG avatars** based on their name and personality -- no image files needed. Terrain can optionally use custom PNG sprites placed in a `sprites/` directory (named `terrain_grass.png`, `terrain_water.png`, etc.).

## Architecture

Creatures share the world via `environment.env_vars["worlds"]`. Each creature is an agent with its own stack, config, and task. The world model tracks positions, inventories, goals, memory, and relationships. State is shared across all agents in the session.

## CLI Options

```
--load LOAD              Load existing session by ID
--monitor                Also run agent monitor for debugging
--monitor-port PORT      Agent monitor port (default: 8001)
--world-port PORT        World visualization port (default: 8000)
```

## Best Practice Examples

This app demonstrates patterns from the `examples/` directory:

- **`examples/shared_state/`** - World state shared across creature agents via `env_vars`
- **`examples/artifacts/`** - Creature memory using the remember/recall pattern
