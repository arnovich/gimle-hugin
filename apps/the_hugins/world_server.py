#!/usr/bin/env python3
"""Web server for real-time world visualization."""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from world import World
    from gimle.hugin.agent.session import Session
    from gimle.hugin.storage.local import LocalStorage

from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)


class WorldHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for world visualization."""

    # Class-level storage for world and simulation thread
    _world: Optional["World"] = None
    _session: Optional["Session"] = None
    _storage: Optional["LocalStorage"] = None
    _simulation_thread: Optional[threading.Thread] = None
    _world_manager: Optional[Any] = None
    _world_dir: Optional[str] = None
    _simulation_paused: threading.Event = threading.Event()
    _max_steps: int = 1000

    def get_paths(self) -> Tuple[str, str]:
        """Get the paths for the world and session."""
        root_dir = self._world_dir or "./data"
        return (root_dir + "/worlds", root_dir + "/sessions")

    def __init__(
        self,
        world: Optional["World"] = None,
        world_manager: Optional[Any] = None,
        world_dir: Optional[str] = None,
        max_steps: int = 1000,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize the world HTTP request handler."""
        if world_manager:
            WorldHTTPRequestHandler._world_manager = world_manager
        if world:
            WorldHTTPRequestHandler._world = world
        if world_dir:
            WorldHTTPRequestHandler._world_dir = world_dir
        WorldHTTPRequestHandler._max_steps = max_steps
        super().__init__(*args, **kwargs)

    @property
    def world(self) -> Optional["World"]:
        """Get the current world."""
        return WorldHTTPRequestHandler._world

    @world.setter
    def world(self, value: Optional["World"]) -> None:
        """Set the current world."""
        WorldHTTPRequestHandler._world = value

    def do_GET(self) -> None:
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        # query_params: Dict[str, List[str]] = parse_qs(parsed_path.query)

        if path == "/" or path == "/index.html":
            # Check if world exists (loaded), otherwise show startup screen
            if self.world:
                self.serve_world_html()
            else:
                self.serve_startup_screen()
        elif path == "/api/sessions":
            self.serve_sessions_list()
        elif path == "/api/world":
            self.serve_world_json()
        elif path == "/api/creatures":
            self.serve_creatures_json()
        elif path == "/api/actions":
            self.serve_actions_json()
        elif path.startswith("/sprites/"):
            self.serve_sprite(path)
        elif path.startswith("/static/"):
            self.serve_static(path)
        else:
            self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        """Handle POST requests."""
        parsed_path = urlparse(self.path)
        path: str = parsed_path.path

        if path == "/api/create":
            self.handle_create_world()
        elif path == "/api/load":
            self.handle_load_world()
        elif path == "/api/delete":
            self.handle_delete_world()
        elif path == "/api/human_interaction":
            self.handle_human_interaction()
        elif path == "/api/pause_simulation":
            self.handle_pause_simulation()
        elif path == "/api/resume_simulation":
            self.handle_resume_simulation()
        elif path == "/api/move_creature":
            self.handle_move_creature()
        elif path == "/api/leave":
            self.handle_leave_world()
        else:
            self.send_error(404, "Not Found")

    def serve_world_html(self) -> None:
        """Serve the HTML visualization."""
        from world.html_renderer import generate_world_html

        if not self.world:
            self.send_error(404, "World not loaded")
            return

        html = generate_world_html(
            self.world,
            view_width=self.world.width,
            view_height=self.world.height,
            sprite_dir=str(Path(__file__).parent / "sprites"),
        )

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def serve_world_json(self) -> None:
        """Serve world state as JSON."""
        if not self.world:
            self.send_error(404, "World not loaded")
            return

        world_data = {
            "id": self.world.id,
            "width": self.world.width,
            "height": self.world.height,
            "tick": self.world.tick,
            "creatures": {
                agent_id: {
                    "name": creature.name,
                    "position": list(creature.position),
                    "personality": creature.personality,
                    "inventory": [
                        item.to_dict() for item in creature.inventory
                    ],
                }
                for agent_id, creature in self.world.creatures.items()
            },
        }

        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(json.dumps(world_data).encode("utf-8"))

    def serve_creatures_json(self) -> None:
        """Serve creatures state as JSON."""
        if not self.world:
            self.send_error(404, "World not loaded")
            return

        creatures_data = {}
        for agent_id, creature in self.world.creatures.items():
            # Get last action for this creature
            last_actions = self.world.action_log.get_actions_by_creature(
                creature.name, count=1
            )
            last_action = None
            if last_actions:
                a = last_actions[-1]
                last_action = {
                    "description": a.description,
                    "action_type": a.action_type,
                    "timestamp": a.timestamp,
                }
                if a.reason:
                    last_action["reason"] = a.reason

            creatures_data[agent_id] = {
                "name": creature.name,
                "description": creature.description,
                "position": list(creature.position),
                "personality": creature.personality,
                "inventory": [item.to_dict() for item in creature.inventory],
                "inventory_count": len(creature.inventory),
                "goals": [
                    {"type": g.type.value, "completed": g.completed}
                    for g in creature.goals
                ],
                "last_action": last_action,
                "energy": creature.energy,
                "money": creature.money,
                "pending_trades": [
                    t.to_dict() for t in creature.pending_trades
                ],
            }

        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(json.dumps(creatures_data).encode("utf-8"))

    def serve_actions_json(self) -> None:
        """Serve actions log as JSON."""
        if not self.world:
            self.send_error(404, "World not loaded")
            return

        parsed_path = urlparse(self.path)
        query_params: Dict[str, List[str]] = parse_qs(parsed_path.query)
        count = int(query_params.get("count", [15])[0])

        recent_actions = self.world.action_log.get_recent_actions(count)
        actions_data = [action.to_dict() for action in recent_actions]

        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(json.dumps(actions_data).encode("utf-8"))

    def serve_startup_screen(self) -> None:
        """Serve the startup screen for loading or creating worlds."""
        from world.startup_screen import (
            generate_startup_html,
            get_saved_sessions,
        )

        # Use correct paths
        WORLD_DIR, SESSION_DIR = self.get_paths()
        sessions = get_saved_sessions(
            save_dir=WORLD_DIR, storage_dir=SESSION_DIR
        )
        html = generate_startup_html(sessions)

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def handle_create_world(self) -> None:
        """Handle POST request to create a new world."""
        if self.world:
            self.send_response(400)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": "World already loaded"}).encode("utf-8")
            )
            return

        if not WorldHTTPRequestHandler._world_manager:
            self.send_response(500)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": "World manager not available"}).encode(
                    "utf-8"
                )
            )
            return

        # Parse optional config from POST body
        content_length = int(self.headers.get("Content-Length", 0))
        config = None
        if content_length > 0:
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                config = json.loads(body)
            except json.JSONDecodeError:
                pass

        try:
            world, session, storage = (
                WorldHTTPRequestHandler._world_manager.create_new_world(config)
            )
            WorldHTTPRequestHandler._world = world
            WorldHTTPRequestHandler._session = session
            WorldHTTPRequestHandler._storage = storage

            # Start simulation in background
            self._start_simulation()

            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "success": True,
                        "session_id": session.id,
                        "message": "World created successfully",
                    }
                ).encode("utf-8")
            )
        except Exception as e:
            logger.error(f"Error creating world: {e}", exc_info=True)
            self.send_response(500)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_load_world(self) -> None:
        """Handle POST request to load an existing world."""
        if self.world:
            self.send_response(400)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": "World already loaded"}).encode("utf-8")
            )
            return

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        try:
            data = json.loads(body)
            session_id = data.get("session_id")
            if not session_id:
                self.send_response(400)
                self.send_header(
                    "Content-type", "application/json; charset=utf-8"
                )
                self.end_headers()
                self.wfile.write(
                    json.dumps({"error": "Missing session_id"}).encode("utf-8")
                )
                return
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": "Invalid JSON"}).encode("utf-8")
            )
            return

        if not WorldHTTPRequestHandler._world_manager:
            self.send_response(500)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": "World manager not available"}).encode(
                    "utf-8"
                )
            )
            return

        try:
            world, session, storage = (
                WorldHTTPRequestHandler._world_manager.load_existing_world(
                    session_id
                )
            )
            WorldHTTPRequestHandler._world = world
            WorldHTTPRequestHandler._session = session
            WorldHTTPRequestHandler._storage = storage

            # Start simulation in background
            self._start_simulation()

            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "success": True,
                        "session_id": session.id,
                        "message": "World loaded successfully",
                    }
                ).encode("utf-8")
            )
        except Exception as e:
            logger.error(f"Error loading world: {e}", exc_info=True)
            self.send_response(500)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_delete_world(self) -> None:
        """Handle POST request to delete an existing world."""
        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        try:
            data = json.loads(body)
            session_id = data.get("session_id")
            if not session_id:
                self.send_response(400)
                self.send_header(
                    "Content-type", "application/json; charset=utf-8"
                )
                self.end_headers()
                self.wfile.write(
                    json.dumps({"error": "Missing session_id"}).encode("utf-8")
                )
                return
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": "Invalid JSON"}).encode("utf-8")
            )
            return

        try:
            # Get paths
            WORLD_DIR, SESSION_DIR = self.get_paths()

            # Delete world file
            world_file = Path(WORLD_DIR) / f"world_{session_id}.json"
            if world_file.exists():
                world_file.unlink()
                logger.info(f"Deleted world file: {world_file}")

            # Delete session file
            session_file = Path(SESSION_DIR) / session_id
            if session_file.exists():
                session_file.unlink()
                logger.info(f"Deleted session file: {session_file}")

            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "success": True,
                        "message": "World deleted successfully",
                    }
                ).encode("utf-8")
            )
        except Exception as e:
            logger.error(f"Error deleting world: {e}", exc_info=True)
            self.send_response(500)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def _start_simulation(self) -> None:
        """Start the simulation loop in a background thread."""
        # Wait for any previous simulation thread to finish
        old_thread = WorldHTTPRequestHandler._simulation_thread
        if old_thread and old_thread.is_alive():
            old_thread.join(timeout=5.0)

        def run_simulation() -> None:
            import time

            max_steps = WorldHTTPRequestHandler._max_steps
            step_delay = 0.1

            world = WorldHTTPRequestHandler._world
            session = WorldHTTPRequestHandler._session
            storage = WorldHTTPRequestHandler._storage

            if not all([world, session, storage]):
                return

            # Type narrowing: we've checked all are not None
            assert world is not None
            assert session is not None
            assert storage is not None

            WORLD_DIR, _ = self.get_paths()
            world_save_path = Path(WORLD_DIR) / f"world_{session.id}.json"
            world_save_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                for step in range(max_steps):
                    # Exit if world was cleared (user left)
                    if WorldHTTPRequestHandler._world is not world:
                        return

                    # Check if simulation is paused
                    if WorldHTTPRequestHandler._simulation_paused.is_set():
                        # Wait until resumed or world cleared
                        while (
                            WorldHTTPRequestHandler._simulation_paused.is_set()
                        ):
                            if WorldHTTPRequestHandler._world is not world:
                                return
                            time.sleep(0.2)

                    any_activity = session.step()
                    world.tick_world()

                    # Save after each step
                    if storage.base_path:
                        storage.save_session(session)
                        world.save(str(world_save_path))

                    if step_delay > 0:
                        time.sleep(step_delay)

                    if not any_activity:
                        time.sleep(1.0)
                        continue
            except Exception as e:
                logger.error(f"Simulation error: {e}", exc_info=True)

        WorldHTTPRequestHandler._simulation_thread = threading.Thread(
            target=run_simulation, daemon=True
        )
        WorldHTTPRequestHandler._simulation_thread.start()

    def serve_sessions_list(self) -> None:
        """Serve list of available sessions."""
        from world.startup_screen import get_saved_sessions

        # Use correct paths
        WORLD_DIR, SESSION_DIR = self.get_paths()
        sessions = get_saved_sessions(
            save_dir=WORLD_DIR, storage_dir=SESSION_DIR
        )

        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(sessions).encode("utf-8"))

    def serve_sprite(self, sprite_path: str) -> None:
        """Serve sprite images."""
        # Extract sprite filename from path
        sprite_filename = sprite_path.replace("/sprites/", "")

        # Get sprite directory (relative to world_server.py location)
        sprite_dir = Path(__file__).parent / "sprites"
        sprite_file = sprite_dir / sprite_filename

        if not sprite_file.exists() or not sprite_file.is_file():
            self.send_error(404, "Sprite not found")
            return

        # Determine content type
        content_type = "image/png"
        if sprite_filename.endswith(".jpg") or sprite_filename.endswith(
            ".jpeg"
        ):
            content_type = "image/jpeg"
        elif sprite_filename.endswith(".gif"):
            content_type = "image/gif"

        try:
            with open(sprite_file, "rb") as f:
                sprite_data = f.read()

            self.send_response(200)
            self.send_header("Content-type", content_type)
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(sprite_data)
        except Exception as e:
            logger.error(f"Error serving sprite {sprite_path}: {e}")
            self.send_error(500, "Error serving sprite")

    def serve_static(self, static_path: str) -> None:
        """Serve static files (CSS, JS, SVG)."""
        # Extract relative path from /static/...
        relative_path = static_path.replace("/static/", "", 1)

        # Get static directory (relative to world_server.py location)
        static_dir = Path(__file__).parent / "static"
        static_file = static_dir / relative_path

        # Security: ensure the resolved path is within static_dir
        try:
            static_file = static_file.resolve()
            static_dir_resolved = static_dir.resolve()
            if not str(static_file).startswith(str(static_dir_resolved)):
                self.send_error(403, "Forbidden")
                return
        except (OSError, ValueError):
            self.send_error(400, "Bad request")
            return

        if not static_file.exists() or not static_file.is_file():
            self.send_error(404, "Static file not found")
            return

        # Determine content type
        content_types = {
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".svg": "image/svg+xml; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }
        suffix = static_file.suffix.lower()
        content_type = content_types.get(suffix, "application/octet-stream")

        try:
            with open(static_file, "rb") as f:
                file_data = f.read()

            self.send_response(200)
            self.send_header("Content-type", content_type)
            self.send_header(
                "Cache-Control",
                "no-cache, no-store, must-revalidate",
            )
            self.end_headers()
            self.wfile.write(file_data)
        except Exception as e:
            logger.error(f"Error serving static file {static_path}: {e}")
            self.send_error(500, "Error serving static file")

    def handle_human_interaction(self) -> None:
        """Handle POST request for human interaction with a creature."""
        if not self.world or not WorldHTTPRequestHandler._session:
            self.send_response(400)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": "World or session not loaded"}).encode(
                    "utf-8"
                )
            )
            return

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        try:
            data = json.loads(body)
            agent_id = data.get("agent_id")
            message = data.get("message")

            if not agent_id or not message:
                self.send_response(400)
                self.send_header(
                    "Content-type", "application/json; charset=utf-8"
                )
                self.end_headers()
                self.wfile.write(
                    json.dumps({"error": "Missing agent_id or message"}).encode(
                        "utf-8"
                    )
                )
                return

            # Get agent from session
            session = WorldHTTPRequestHandler._session
            agent = session.get_agent(agent_id)

            if not agent:
                self.send_response(404)
                self.send_header(
                    "Content-type", "application/json; charset=utf-8"
                )
                self.end_headers()
                self.wfile.write(
                    json.dumps({"error": f"Agent {agent_id} not found"}).encode(
                        "utf-8"
                    )
                )
                return

            # Insert human interaction into the agent's stack
            agent.message_agent(message=message)

            # Resume simulation after interaction is added
            WorldHTTPRequestHandler._simulation_paused.clear()

            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "success": True,
                        "message": "External input added successfully",
                    }
                ).encode("utf-8")
            )
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": "Invalid JSON"}).encode("utf-8")
            )
        except Exception as e:
            logger.error(
                f"Error handling human interaction: {e}", exc_info=True
            )
            self.send_response(500)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_pause_simulation(self) -> None:
        """Handle POST request to pause the simulation."""
        WorldHTTPRequestHandler._simulation_paused.set()
        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(
            json.dumps(
                {"success": True, "message": "Simulation paused"}
            ).encode("utf-8")
        )

    def handle_resume_simulation(self) -> None:
        """Handle POST request to resume the simulation."""
        WorldHTTPRequestHandler._simulation_paused.clear()
        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(
            json.dumps(
                {"success": True, "message": "Simulation resumed"}
            ).encode("utf-8")
        )

    def handle_leave_world(self) -> None:
        """Handle POST request to leave the current world and return to menu."""
        try:
            # Pause the simulation
            WorldHTTPRequestHandler._simulation_paused.set()

            # Save current state
            world = self.world
            session = WorldHTTPRequestHandler._session
            storage = WorldHTTPRequestHandler._storage
            if world and session and storage:
                world_dir, _ = self.get_paths()
                world_save_path = Path(world_dir) / f"world_{session.id}.json"
                if storage.base_path:
                    storage.save_session(session)
                    world.save(str(world_save_path))

            # Clear world so next GET / shows startup screen
            WorldHTTPRequestHandler._world = None
            WorldHTTPRequestHandler._session = None
            WorldHTTPRequestHandler._storage = None
            # Clear paused flag so next simulation starts unpaused
            WorldHTTPRequestHandler._simulation_paused.clear()

            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
        except Exception as e:
            logger.error(f"Error leaving world: {e}", exc_info=True)
            self.send_response(500)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_move_creature(self) -> None:
        """Handle POST request to move a creature and notify the agent."""
        if not self.world or not WorldHTTPRequestHandler._session:
            self.send_response(400)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": "World or session not loaded"}).encode(
                    "utf-8"
                )
            )
            return

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        try:
            data = json.loads(body)
            agent_id = data.get("agent_id")
            new_x = data.get("x")
            new_y = data.get("y")

            if agent_id is None or new_x is None or new_y is None:
                self.send_response(400)
                self.send_header(
                    "Content-type", "application/json; charset=utf-8"
                )
                self.end_headers()
                self.wfile.write(
                    json.dumps({"error": "Missing agent_id, x, or y"}).encode(
                        "utf-8"
                    )
                )
                return

            # Get creature's current position for the message
            creature = self.world.creatures.get(agent_id)
            if not creature:
                self.send_response(404)
                self.send_header(
                    "Content-type", "application/json; charset=utf-8"
                )
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"error": f"Creature {agent_id} not found"}
                    ).encode("utf-8")
                )
                return

            old_x, old_y = creature.position

            # Move creature in the world
            success = self.world.move_creature(agent_id, int(new_x), int(new_y))
            if not success:
                self.send_response(400)
                self.send_header(
                    "Content-type", "application/json; charset=utf-8"
                )
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {
                            "error": f"Failed to move creature to ({new_x}, {new_y})"
                        }
                    ).encode("utf-8")
                )
                return

            # Send message to the agent about being moved
            session = WorldHTTPRequestHandler._session
            agent = session.get_agent(agent_id)

            if agent:
                move_message = (
                    f"You have been moved by an external force! "
                    f"You were at position ({old_x}, {old_y}) and are now "
                    f"at position ({new_x}, {new_y}). "
                    f"Take a moment to observe your new surroundings."
                )
                agent.message_agent(message=move_message)

            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "success": True,
                        "message": "Creature moved and notified",
                        "old_position": [old_x, old_y],
                        "new_position": [new_x, new_y],
                    }
                ).encode("utf-8")
            )
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": "Invalid JSON"}).encode("utf-8")
            )
        except Exception as e:
            logger.error(f"Error moving creature: {e}", exc_info=True)
            self.send_response(500)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        """Override to suppress default logging."""
        # Suppress default HTTP server logging for cleaner output
        pass


def create_world_handler(
    world: Optional["World"] = None,
    world_manager: Optional[Any] = None,
    world_dir: Optional[str] = None,
    max_steps: int = 1000,
) -> type[WorldHTTPRequestHandler]:
    """Create a request handler class bound to a world."""

    class Handler(WorldHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(
                world, world_manager, world_dir, max_steps, *args, **kwargs
            )

    return Handler


def run_world_server(
    world: Optional["World"] = None,
    world_manager: Optional[Any] = None,
    port: int = 8000,
    host: str = "localhost",
    world_dir: Optional[str] = None,
    max_steps: int = 1000,
    on_ready: Optional[Callable] = None,
) -> None:
    """
    Run a web server for world visualization.

    Args:
        world: The world to visualize (optional, can be loaded via browser)
        world_manager: World manager instance for creating/loading worlds
        port: Port to run the server on
        host: Host to bind to
        world_dir: Directory for world data
        max_steps: Maximum number of simulation steps (default: 1000)
        on_ready: Optional callback invoked once the server is listening
    """
    handler_class = create_world_handler(
        world, world_manager, world_dir, max_steps
    )
    server = HTTPServer((host, port), handler_class)

    if on_ready:
        on_ready()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
