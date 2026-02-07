"""World model for The Hugins."""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from world.action_log import ActionLog
from world.cell import Cell, TerrainType
from world.creature_state import CreatureState
from world.economy import (
    SPAWN_COUNT,
    SPAWN_INTERVAL_TICKS,
    SPAWN_WEIGHTS,
    STARTING_ENERGY,
    STARTING_MONEY,
    TradeOffer,
)
from world.goals import Goal, GoalType, Memory, Relationship
from world.noise import fractal_noise, make_noise_context
from world.object import Object, ObjectType


@dataclass
class World:
    """The world containing all cells, creatures, and objects."""

    id: str
    width: int
    height: int
    cells: Dict[Tuple[int, int], Cell] = field(default_factory=dict)
    creatures: Dict[str, CreatureState] = field(
        default_factory=dict
    )  # agent_id -> state
    tick: int = 0
    action_log: ActionLog = field(
        default_factory=lambda: ActionLog(max_actions=200)
    )

    def __post_init__(self) -> None:
        """Initialize the world after creation."""
        if not self.cells:
            self.initialize()

    def initialize(self, seed: Optional[int] = None) -> None:
        """Initialize the world with noise-based biome terrain."""
        if seed is None:
            seed = random.randint(0, 2**31)
        random.seed(seed)

        # Create noise contexts for different layers
        grads_elev, perm_elev = make_noise_context(seed)
        grads_moist, perm_moist = make_noise_context(seed + 100)

        # Scale factor: lower = larger biome regions
        scale = 0.12

        for y in range(self.height):
            for x in range(self.width):
                # Elevation noise (base biome)
                elev = fractal_noise(
                    x * scale,
                    y * scale,
                    octaves=3,
                    gradients=grads_elev,
                    perm=perm_elev,
                )
                # Moisture noise (sub-biome variation)
                moist = fractal_noise(
                    x * scale * 1.5,
                    y * scale * 1.5,
                    octaves=2,
                    gradients=grads_moist,
                    perm=perm_moist,
                )

                terrain = self._terrain_from_noise(elev, moist)
                cell = Cell(terrain=terrain, x=x, y=y)
                self.cells[(x, y)] = cell

        # Post-process: add sand beaches around water
        self._add_beaches()

    @staticmethod
    def _terrain_from_noise(elevation: float, moisture: float) -> TerrainType:
        """Map noise values to terrain type.

        Thresholds chosen so that:
        - Low elevation = water
        - Mid-low with moisture = dirt/grass
        - Mid = grass (most common)
        - Mid-high with moisture = forest
        - High = stone
        """
        if elevation < -0.25:
            return TerrainType.WATER
        elif elevation < -0.1:
            return TerrainType.DIRT if moisture < 0 else TerrainType.SAND
        elif elevation < 0.25:
            if moisture > 0.2:
                return TerrainType.FOREST
            return TerrainType.GRASS
        elif elevation < 0.45:
            return TerrainType.FOREST if moisture > 0 else TerrainType.DIRT
        else:
            return TerrainType.STONE

    def _add_beaches(self) -> None:
        """Convert land cells adjacent to water into sand."""
        sand_candidates = []
        for (x, y), cell in self.cells.items():
            if cell.terrain == TerrainType.WATER:
                continue
            # Check 4-neighbors for water
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                neighbor = self.cells.get((x + dx, y + dy))
                if neighbor and neighbor.terrain == TerrainType.WATER:
                    sand_candidates.append((x, y))
                    break
        for x, y in sand_candidates:
            self.cells[(x, y)].terrain = TerrainType.SAND

    def get_cell(self, x: int, y: int) -> Optional[Cell]:
        """Get a cell at the given coordinates."""
        if not self.is_valid_position(x, y):
            return None
        return self.cells.get((x, y))

    def is_valid_position(self, x: int, y: int) -> bool:
        """Check if coordinates are within world bounds."""
        return 0 <= x < self.width and 0 <= y < self.height

    def add_creature(
        self,
        agent_id: str,
        name: str,
        description: str,
        personality: str,
        x: int,
        y: int,
    ) -> bool:
        """Add a creature to the world at the given position."""
        if not self.is_valid_position(x, y):
            return False

        cell = self.get_cell(x, y)
        if cell and cell.terrain == TerrainType.WATER:
            return False

        if agent_id in self.creatures:
            # Update existing creature position
            self.creatures[agent_id].position = (x, y)
        else:
            # Create new creature
            creature_state = CreatureState(
                agent_id=agent_id,
                position=(x, y),
                name=name,
                description=description,
                personality=personality,
            )
            self.creatures[agent_id] = creature_state

        # Add creature object to cell
        cell = self.get_cell(x, y)
        if cell:
            # Remove existing creature object if present
            cell.objects = [obj for obj in cell.objects if obj.id != agent_id]
            # Add new creature object
            creature_obj = Object(
                name=name,
                type=ObjectType.CREATURE,
                description=description,
                id=agent_id,
            )
            cell.add_object(creature_obj)

        return True

    def move_creature(self, agent_id: str, new_x: int, new_y: int) -> bool:
        """Move a creature to a new position."""
        if agent_id not in self.creatures:
            return False

        if not self.is_valid_position(new_x, new_y):
            return False

        creature = self.creatures[agent_id]
        old_x, old_y = creature.position

        # Remove creature from old cell
        old_cell = self.get_cell(old_x, old_y)
        if old_cell:
            old_cell.objects = [
                obj for obj in old_cell.objects if obj.id != agent_id
            ]

        # Update creature position
        creature.position = (new_x, new_y)

        # Add creature to new cell
        new_cell = self.get_cell(new_x, new_y)
        if new_cell:
            creature_obj = Object(
                name=creature.name,
                type=ObjectType.CREATURE,
                description=creature.description,
                id=agent_id,
            )
            new_cell.add_object(creature_obj)

        return True

    def get_creature_position(self, agent_id: str) -> Optional[Tuple[int, int]]:
        """Get the position of a creature."""
        if agent_id not in self.creatures:
            return None
        position: Tuple[int, int] = self.creatures[agent_id].position
        return position

    def get_view(self, x: int, y: int, radius: int = 1) -> List[Cell]:
        """Get a view of cells around a position (3x3 grid by default)."""
        view = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                view_x = x + dx
                view_y = y + dy
                cell = self.get_cell(view_x, view_y)
                if cell:
                    view.append(cell)
        return view

    def add_object(self, x: int, y: int, obj: Object) -> bool:
        """Add an object to a cell."""
        cell = self.get_cell(x, y)
        if not cell:
            return False
        cell.add_object(obj)
        return True

    def remove_object(self, x: int, y: int, obj_name: str) -> Optional[Object]:
        """Remove an object from a cell."""
        cell = self.get_cell(x, y)
        if not cell:
            return None
        return cell.remove_object(obj_name)

    def get_creature(self, agent_id: str) -> Optional[CreatureState]:
        """Get a creature by agent_id."""
        return self.creatures.get(agent_id)

    def get_creature_by_name(self, name: str) -> Optional[CreatureState]:
        """Get a creature by name."""
        for creature in self.creatures.values():
            if creature.name == name:
                return creature
        return None

    def get_nearby_creatures(
        self, x: int, y: int, radius: int = 1
    ) -> List[CreatureState]:
        """Get creatures within radius of a position."""
        nearby = []
        for creature in self.creatures.values():
            cx, cy = creature.position
            if abs(cx - x) <= radius and abs(cy - y) <= radius:
                if not (cx == x and cy == y):  # Exclude self
                    nearby.append(creature)
        return nearby

    def add_items_to_world(self, num_items: int = 20) -> None:
        """Add random items to the world."""
        item_names = [
            "apple",
            "berry",
            "stone",
            "stick",
            "flower",
            "mushroom",
            "leaf",
            "feather",
            "pebble",
            "acorn",
            "seed",
            "herb",
        ]

        for _ in range(num_items):
            # Find a non-water cell
            for _attempt in range(50):
                x = random.randint(0, self.width - 1)
                y = random.randint(0, self.height - 1)
                cell = self.get_cell(x, y)
                if cell and cell.terrain != TerrainType.WATER:
                    break
            else:
                continue

            item_name = random.choice(item_names)
            item_id = (
                f"item_{x}_{y}_{self.tick}" f"_{random.randint(1000, 9999)}"
            )

            item = Object(
                name=item_name,
                type=ObjectType.ITEM,
                description=f"A {item_name}",
                id=item_id,
            )
            self.add_object(x, y, item)

    def tick_world(self) -> None:
        """Advance the world by one tick."""
        self.tick += 1

        # Process plant growth
        for cell in self.cells.values():
            if (
                cell.planted_seed
                and cell.terrain == TerrainType.PLANTED
                and cell.plant_growth_tick <= self.tick
            ):
                self._grow_plant(cell)

        # Spawn resources periodically
        if self.tick % SPAWN_INTERVAL_TICKS == 0:
            self._spawn_resources(num_items=SPAWN_COUNT)

        # Update goal progress, decay memories, etc.
        for creature in self.creatures.values():
            # Update goal progress based on actions
            for goal in creature.goals:
                if not goal.completed:
                    # Simple progress update - can be enhanced
                    pass

    def _grow_plant(self, cell: Cell) -> None:
        """Grow a planted seed into a harvestable item."""
        # Mapping of seed types to what they grow into
        seed_to_plant = {
            "seed": "apple",
            "herb_seed": "herbs",
            "flower_seed": "flower",
            "berry_seed": "berry",
            "mushroom_spore": "mushroom",
        }

        result = seed_to_plant.get(cell.planted_seed or "", "plant")

        # Create the grown item
        plant_obj = Object(
            name=result,
            type=ObjectType.ITEM,
            description=f"A {result} that grew from a planted seed",
            id=f"grown_{result}_{cell.x}_{cell.y}_{self.tick}",
        )
        cell.add_object(plant_obj)

        # Reset cell state
        cell.planted_seed = None
        cell.plant_growth_tick = 0
        cell.terrain = TerrainType.GRASS  # Return to grass after harvest

    def _spawn_resources(self, num_items: int = 3) -> None:
        """Spawn random resources in the world."""
        item_names = list(SPAWN_WEIGHTS.keys())
        weights = list(SPAWN_WEIGHTS.values())

        spawned_items = []
        for _ in range(num_items):
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)

            # Skip cells with water terrain
            cell = self.get_cell(x, y)
            if cell and cell.terrain == TerrainType.WATER:
                continue

            # Weighted random selection
            item_name = random.choices(item_names, weights=weights, k=1)[0]
            item_id = f"spawn_{x}_{y}_{self.tick}_{random.randint(1000, 9999)}"

            item = Object(
                name=item_name,
                type=ObjectType.ITEM,
                description=f"A {item_name}",
                id=item_id,
            )
            self.add_object(x, y, item)
            spawned_items.append((item_name, x, y))

        # Log spawn event
        if spawned_items:
            items_summary = ", ".join(
                f"{name} at ({x},{y})" for name, x, y in spawned_items
            )
            self.action_log.add_action(
                creature_name="World",
                agent_id="world",
                action_type="spawn",
                description=f"Resources spawned: {items_summary}",
                timestamp=self.tick,
                location=None,
                details={"items": spawned_items},
            )

    def add_goal_to_creature(
        self,
        agent_id: str,
        goal_type: GoalType,
        description: str,
        priority: int = 5,
    ) -> bool:
        """Add a goal to a creature."""
        if agent_id not in self.creatures:
            return False

        goal = Goal(
            type=goal_type,
            description=description,
            priority=priority,
        )
        self.creatures[agent_id].add_goal(goal)
        return True

    def add_memory_to_creature(
        self,
        agent_id: str,
        event_type: str,
        description: str,
        location: Optional[Tuple[int, int]] = None,
        related_creature: Optional[str] = None,
        related_item: Optional[str] = None,
        importance: int = 5,
    ) -> bool:
        """Add a memory to a creature."""
        if agent_id not in self.creatures:
            return False

        memory = Memory(
            event_type=event_type,
            description=description,
            location=location,
            related_creature=related_creature,
            related_item=related_item,
            timestamp=self.tick,
            importance=importance,
        )
        self.creatures[agent_id].add_memory(memory)
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize world to dictionary."""
        return {
            "id": self.id,
            "width": self.width,
            "height": self.height,
            "tick": self.tick,
            "cells": {
                f"{x}_{y}": cell.to_dict()
                for (x, y), cell in self.cells.items()
            },
            "creatures": {
                agent_id: state.to_dict()
                for agent_id, state in self.creatures.items()
            },
            "action_log": self.action_log.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "World":
        """Deserialize world from dictionary."""
        from world.action_log import Action, ActionLog
        from world.cell import Cell, TerrainType
        from world.creature_state import CreatureState

        world = cls(
            id=data["id"],
            width=data["width"],
            height=data["height"],
        )
        world.tick = data.get("tick", 0)

        # Deserialize cells
        cells_data = data.get("cells", {})
        for key, cell_data in cells_data.items():
            x, y = map(int, key.split("_"))
            terrain = TerrainType(cell_data["terrain"])
            cell = Cell(terrain=terrain, x=x, y=y)

            for obj_data in cell_data.get("objects", []):
                obj = Object(
                    name=obj_data["name"],
                    type=ObjectType(obj_data["type"]),
                    description=obj_data["description"],
                    id=obj_data["id"],
                )
                cell.add_object(obj)

            world.cells[(x, y)] = cell

        # Deserialize creatures
        creatures_data = data.get("creatures", {})
        for agent_id, creature_data in creatures_data.items():
            # Deserialize inventory
            inventory = []
            for obj_data in creature_data.get("inventory", []):
                inventory.append(
                    Object(
                        name=obj_data["name"],
                        type=ObjectType(obj_data["type"]),
                        description=obj_data["description"],
                        id=obj_data["id"],
                    )
                )

            # Deserialize goals
            goals = []
            for goal_data in creature_data.get("goals", []):
                goal = Goal(
                    type=GoalType(goal_data["type"]),
                    description=goal_data["description"],
                    priority=goal_data.get("priority", 5),
                    target=goal_data.get("target"),
                    target_position=(
                        tuple(goal_data["target_position"])
                        if goal_data.get("target_position")
                        else None
                    ),
                    completed=goal_data.get("completed", False),
                    progress=goal_data.get("progress", 0.0),
                )
                goals.append(goal)

            # Deserialize memories
            memories = []
            for memory_data in creature_data.get("memories", []):
                memory = Memory(
                    event_type=memory_data["event_type"],
                    description=memory_data["description"],
                    location=(
                        tuple(memory_data["location"])
                        if memory_data.get("location")
                        else None
                    ),
                    related_creature=memory_data.get("related_creature"),
                    related_item=memory_data.get("related_item"),
                    timestamp=memory_data.get("timestamp", 0),
                    importance=memory_data.get("importance", 5),
                )
                memories.append(memory)

            # Deserialize relationships
            relationships = {}
            for name, rel_data in creature_data.get(
                "relationships", {}
            ).items():
                relationships[name] = Relationship(
                    other_creature_name=rel_data["other_creature_name"],
                    relationship_type=rel_data["relationship_type"],
                    interactions=rel_data.get("interactions", 0),
                    last_interaction_tick=rel_data.get(
                        "last_interaction_tick", 0
                    ),
                    sentiment=rel_data.get("sentiment", 5),
                )

            # Deserialize pending trades
            pending_trades = []
            for trade_data in creature_data.get("pending_trades", []):
                pending_trades.append(TradeOffer.from_dict(trade_data))

            creature_state = CreatureState(
                agent_id=agent_id,
                position=tuple(creature_data["position"]),
                name=creature_data["name"],
                description=creature_data["description"],
                personality=creature_data["personality"],
                inventory=inventory,
                goals=goals,
                memories=memories,
                relationships=relationships,
                energy=creature_data.get("energy", STARTING_ENERGY),
                money=creature_data.get("money", STARTING_MONEY),
                pending_trades=pending_trades,
            )
            world.creatures[agent_id] = creature_state

            # Add creature object to cell
            x, y = creature_state.position
            target_cell: Optional[Cell] = world.get_cell(x, y)
            if target_cell is not None:
                creature_obj = Object(
                    name=creature_state.name,
                    type=ObjectType.CREATURE,
                    description=creature_state.description,
                    id=agent_id,
                )
                target_cell.add_object(creature_obj)

        # Deserialize action log
        action_log_data = data.get("action_log", {})
        action_log = ActionLog(
            max_actions=action_log_data.get("total_actions", 200)
        )
        for action_data in action_log_data.get("actions", []):
            action = Action(
                creature_name=action_data["creature_name"],
                agent_id=action_data["agent_id"],
                action_type=action_data["action_type"],
                description=action_data["description"],
                timestamp=action_data["timestamp"],
                location=(
                    tuple(action_data["location"])
                    if action_data.get("location")
                    else None
                ),
                details=action_data.get("details", {}),
            )
            action_log.actions.append(action)
        world.action_log = action_log

        return world

    def save(self, filepath: str) -> None:
        """Save world to a JSON file."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> "World":
        """Load world from a JSON file."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"World file not found: {filepath}")

        with open(path, "r") as f:
            data = json.load(f)

        return cls.from_dict(data)
