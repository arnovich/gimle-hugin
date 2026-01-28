#!/usr/bin/env python3
"""Run The Hugins with web server for visualization."""

import argparse
import logging
import os
import random
import sys
import threading
from pathlib import Path

from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.cli.helpers import (
    configure_logging,
    open_in_browser,
    start_monitor_dashboard,
)
from gimle.hugin.storage.local import LocalStorage

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from world.goals import GoalType  # noqa: E402
from world.world import World  # noqa: E402
from world_server import run_world_server  # noqa: E402

# Configure logging - minimal output
logging.basicConfig(
    level=logging.WARNING,  # Only show warnings and errors
    format="%(message)s",
)

logger = logging.getLogger(__name__)


# Use centralized storage (consistent with examples)
APP_DIR = Path(__file__).parent
SAVE_DIR = "./storage/the_hugins"
WORLD_DIR = f"{SAVE_DIR}/worlds"
SESSION_DIR = SAVE_DIR


def load_existing_world(
    session_id: str, storage: LocalStorage
) -> tuple[World, Session]:
    """Load an existing world and session."""
    world_save_path = Path(WORLD_DIR) / f"world_{session_id}.json"

    if not world_save_path.exists():
        raise FileNotFoundError(
            f"World file not found for session {session_id}"
        )

    # Load world
    world = World.load(str(world_save_path))

    # Load environment
    env = Environment.load(
        str(Path(__file__).parent),
        storage=storage,
        env_vars={"worlds": {world.id: world}},
    )

    # Load session
    session = storage.load_session(session_id, environment=env)

    # Re-link agents to world creatures
    for agent in session.agents:
        if agent.id in world.creatures:
            # Agent is already linked via agent_id
            pass

    return world, session


def create_new_world(
    config: dict | None = None,
) -> tuple[World, Session, LocalStorage]:
    """Create a new world and session.

    Args:
        config: Optional configuration dict with keys:
            - world_width (int): Width of the world grid (default: 50)
            - world_height (int): Height of the world grid (default: 50)
            - seed (int|None): Random seed (default: 42)
            - num_items (int): Number of items to place (default: 30)
    """
    if config is None:
        config = {}

    width = config.get("world_width", 50)
    height = config.get("world_height", 50)
    seed = config.get("seed", 42)
    num_items = config.get("num_items", 30)

    world = World(id="world_1", width=width, height=height)
    world.initialize(seed=seed)

    world.add_items_to_world(num_items=num_items)

    storage = LocalStorage(base_path=SESSION_DIR)
    env = Environment.load(
        str(Path(__file__).parent),
        storage=storage,
        env_vars={"worlds": {"world_1": world}},
    )

    session = Session(environment=env)

    return world, session, storage


CREATURE_POOL = [
    {
        "name": "Fluffy",
        "description": "A friendly bunny that loves to explore",
        "personality": (
            "Curious, adventurous, friendly. You love exploring "
            "new places and meeting other creatures. You're always "
            "eager to see what's around the next corner."
        ),
        "goals": ["explore", "meet"],
    },
    {
        "name": "Spike",
        "description": "A cautious hedgehog who thinks before acting",
        "personality": (
            "Cautious, thoughtful, methodical. You prefer to "
            "observe your surroundings carefully before making "
            "decisions. You value safety and planning."
        ),
        "goals": ["explore", "collect"],
    },
    {
        "name": "Bloom",
        "description": "A cheerful flower sprite who radiates positivity",
        "personality": (
            "Optimistic, social, nurturing. You love helping "
            "others and spreading joy wherever you go."
        ),
        "goals": ["meet", "explore"],
    },
    {
        "name": "Grit",
        "description": "A determined beetle who never gives up",
        "personality": (
            "Stubborn, resourceful, brave. You tackle every "
            "challenge head-on and never back down."
        ),
        "goals": ["collect", "reach"],
    },
    {
        "name": "Wisp",
        "description": "A mysterious firefly drawn to hidden places",
        "personality": (
            "Quiet, perceptive, enigmatic. You seek out secrets "
            "and hidden corners of the world."
        ),
        "goals": ["explore", "avoid"],
    },
    {
        "name": "Chomp",
        "description": "A hungry caterpillar always searching for food",
        "personality": (
            "Eager, single-minded, friendly. You are always on "
            "the lookout for tasty items to collect."
        ),
        "goals": ["collect", "explore"],
    },
]


def _generate_creatures(num: int) -> list[dict]:
    """Generate a list of creature configs from the preset pool."""
    creatures = []
    pool = list(CREATURE_POOL)
    random.shuffle(pool)
    for i in range(num):
        base = pool[i % len(pool)].copy()
        # Deduplicate names when wrapping around
        if i >= len(pool):
            base["name"] = f"{base['name']} {i + 1}"
        # Positions will be auto-assigned by _setup_creatures
        base["x"] = None
        base["y"] = None
        creatures.append(base)
    return creatures


class WorldManager:
    """Manages world creation and loading for the server."""

    def __init__(self, world_dir: str, session_dir: str):
        """Initialize the world manager."""
        self.world_dir = world_dir
        self.session_dir = session_dir
        self.load_existing_world_func = load_existing_world
        self.create_new_world_func = create_new_world

    def create_new_world(
        self,
        config: dict | None = None,
    ) -> tuple[World, Session, LocalStorage]:
        """Create a new world and session."""
        world, session, storage = self.create_new_world_func(config)

        # Create creatures for new world
        cfg = config or {}
        creatures_config = cfg.get("creatures")
        if not creatures_config and "num_creatures" in cfg:
            creatures_config = _generate_creatures(cfg["num_creatures"])
        self._setup_creatures(world, session, creatures_config)

        # Save initial state
        world_save_path = Path(self.world_dir) / f"world_{session.id}.json"
        if storage and storage.base_path:
            storage.save_session(session)
            world.save(str(world_save_path))

        return world, session, storage

    def load_existing_world(
        self, session_id: str
    ) -> tuple[World, Session, LocalStorage]:
        """Load an existing world and session."""
        storage = LocalStorage(base_path=self.session_dir)
        world, session = self.load_existing_world_func(session_id, storage)
        return world, session, storage

    def _setup_creatures(
        self,
        world: World,
        session: Session,
        creatures_config: list[dict] | None = None,
    ) -> None:
        """Set up creatures for a new world.

        Args:
            world: The world to add creatures to.
            session: The session to create agents in.
            creatures_config: Optional list of creature dicts with keys:
                - name (str), description (str), personality (str)
                - x (int|None), y (int|None)
                - goals (list[str]): goal type names
        """
        env = session.environment
        config = env.config_registry.get("creature")
        task_template = env.task_registry.get("live")

        # Default creatures if none provided
        if not creatures_config:
            creatures_config = [
                {
                    "name": "Fluffy",
                    "description": ("A friendly bunny that loves to explore"),
                    "personality": (
                        "Curious, adventurous, friendly. You love "
                        "exploring new places and meeting other "
                        "creatures. You're always eager to see what's "
                        "around the next corner."
                    ),
                    "x": None,
                    "y": None,
                    "goals": ["explore", "meet"],
                },
                {
                    "name": "Spike",
                    "description": (
                        "A cautious hedgehog who thinks before acting"
                    ),
                    "personality": (
                        "Cautious, thoughtful, methodical. You prefer "
                        "to observe your surroundings carefully before "
                        "making decisions. You value safety and "
                        "planning."
                    ),
                    "x": None,
                    "y": None,
                    "goals": ["explore", "collect"],
                },
            ]

        # Auto-assign or clamp positions to world bounds
        num_creatures = len(creatures_config)
        for i, creature_cfg in enumerate(creatures_config):
            if creature_cfg.get("x") is None or creature_cfg.get("y") is None:
                # Spread evenly across the map, always within bounds
                creature_cfg["x"] = int(
                    (i + 1) * world.width / (num_creatures + 1)
                )
                creature_cfg["y"] = int(
                    (i + 1) * world.height / (num_creatures + 1)
                )

            # Clamp to valid world coordinates
            creature_cfg["x"] = max(0, min(creature_cfg["x"], world.width - 1))
            creature_cfg["y"] = max(0, min(creature_cfg["y"], world.height - 1))

        # Goal description defaults per type
        goal_descriptions: dict[str, str] = {
            "explore": "Explore the world and discover new places",
            "collect": "Collect useful items",
            "meet": "Meet and interact with other creatures",
            "avoid": "Avoid dangerous things",
            "reach": "Reach a specific destination",
            "custom": "Pursue a personal goal",
        }

        for creature_cfg in creatures_config:
            name = creature_cfg["name"]
            description = creature_cfg["description"]
            personality = creature_cfg["personality"]
            x = creature_cfg["x"]
            y = creature_cfg["y"]
            goals = creature_cfg.get("goals", ["explore"])

            task = task_template.set_input_parameters(
                {
                    "world_id": "world_1",
                    "creature_name": name,
                    "creature_description": description,
                    "personality": personality,
                    "initial_x": x,
                    "initial_y": y,
                }
            )

            session.create_agent_from_task(config, task)
            agent = session.agents[-1]
            added = world.add_creature(
                agent_id=agent.id,
                name=name,
                description=description,
                personality=personality,
                x=x,
                y=y,
            )
            if not added:
                logger.warning(
                    f"Failed to place {name} at ({x}, {y}) "
                    f"- outside world bounds ({world.width}x{world.height})"
                )

            # Add goals
            for priority, goal_name in enumerate(reversed(goals), start=5):
                goal_type = GoalType(goal_name)
                world.add_goal_to_creature(
                    agent.id,
                    goal_type,
                    goal_descriptions.get(goal_name, f"{goal_name} goal"),
                    priority=priority,
                )


def main() -> int:
    """Run The Hugins simulation with web server."""
    parser = argparse.ArgumentParser(description="Run The Hugins simulation")
    parser.add_argument(
        "--load",
        type=str,
        help="Load an existing session by session ID (legacy, use browser instead)",
    )
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Also run agent monitor for debugging (default: False)",
    )
    parser.add_argument(
        "--monitor-port",
        type=int,
        default=8001,
        help="Agent monitor port (default: 8001)",
    )
    parser.add_argument(
        "--world-port",
        type=int,
        default=8000,
        help="World visualization port (default: 8000)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=1000,
        help="Maximum number of simulation steps (default: 1000)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="WARNING",
        help="Set the logging level (default: WARNING)",
    )
    args = parser.parse_args()

    # Configure logging based on command line argument
    configure_logging(args.log_level)

    os.makedirs(SAVE_DIR, exist_ok=True)
    os.makedirs(WORLD_DIR, exist_ok=True)

    # Legacy support: if --load is provided, load it directly
    world = None
    if args.load:
        storage = LocalStorage(base_path=SESSION_DIR)
        try:
            world, session = load_existing_world(args.load, storage)
            print(f"✅ Loaded session: {session.id}")
        except Exception as e:
            print(f"❌ Error loading session: {e}")
            return 1

    # Create world manager
    world_manager = WorldManager(WORLD_DIR, SESSION_DIR)

    # Start agent monitor if requested
    monitor_process = None
    if args.monitor:
        print(
            f"🌐 Starting agent monitor at http://localhost:{args.monitor_port}/"
        )
        print()

        # Start the agent monitor using helper
        print("⏳ Waiting for agent monitor to start...")
        monitor_process = start_monitor_dashboard(
            SESSION_DIR, args.monitor_port
        )

    # Start web server (world can be None, will be loaded via browser)
    print("=" * 60)
    print("🌍 The Hugins Simulation")
    print("=" * 60)
    if world:
        print(f"World: {world.width}x{world.height} grid")
        print(f"Creatures: {len(world.creatures)}")
    else:
        print("No world loaded - use browser to create or load a world")
    print()
    print(f"🌐 World visualization: http://localhost:{args.world_port}/")
    if args.monitor:
        print(f"🔍 Agent monitor: http://localhost:{args.monitor_port}/")
    print()
    print("Opening world visualization in browser...")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()

    # Start server in a thread so we can open browsers after it's ready
    server_ready = threading.Event()

    def _run_server() -> None:
        run_world_server(
            world=world,
            world_manager=world_manager,
            world_dir=SAVE_DIR,
            port=args.world_port,
            host="localhost",
            max_steps=args.max_steps,
            on_ready=server_ready.set,
        )

    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    # Wait for the server to be ready before opening browsers
    server_ready.wait(timeout=10)

    open_in_browser(f"http://localhost:{args.world_port}/")
    if args.monitor:
        open_in_browser(f"http://localhost:{args.monitor_port}/", delay=1)

    # Block on server thread
    try:
        server_thread.join()
    except KeyboardInterrupt:
        print("\n\nShutting down server...")
        if monitor_process:
            print("Stopping agent monitor...")
            monitor_process.terminate()
            monitor_process.wait()
        print("Goodbye!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
