#!/usr/bin/env python3
"""Web server for monitoring active agents.

This monitor provides live updates through two mechanisms:

1. File watching (default): Monitors the storage directory for file changes.
   Used when agents run in separate processes from the monitor.

2. Direct callbacks: When agents run in the same process, they can use
   LocalStorage with get_monitor_callback() for immediate updates without
   file system polling.

Example with direct callback:
    from gimle.hugin.cli.monitor_agents import get_monitor_callback
    from gimle.hugin.storage.local import LocalStorage

    # Create storage with monitor callback
    callback = get_monitor_callback()
    storage = LocalStorage(base_path="./storage", callback=callback)
    # Now any saves will immediately trigger monitor updates
"""

import argparse
import json
import logging
import queue
import threading
import time
import webbrowser
from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.environment import Environment
from gimle.hugin.artifacts.feedback import ArtifactFeedback
from gimle.hugin.storage.local import LocalStorage
from gimle.hugin.ui.components import ComponentRegistry
from gimle.hugin.ui.static import (
    get_mime_type,
    render_template,
    serve_static_file,
)

logger = logging.getLogger(__name__)


# Track which extension paths have been loaded to avoid reloading
_loaded_extension_paths: set = set()


def load_extensions_from_storage(storage_path: Path) -> bool:
    """Load custom artifact types and UI components from storage metadata.

    Checks for .hugin_metadata.json in the storage directory and loads
    any extensions specified by the package_paths field.

    Tracks loaded paths to avoid reloading on subsequent calls.

    Args:
        storage_path: Path to the storage directory

    Returns:
        True if any new extensions were loaded, False otherwise
    """
    metadata_path = storage_path / ".hugin_metadata.json"
    new_extensions_loaded = False

    if not metadata_path.exists():
        logger.debug(f"No metadata file found at {metadata_path}")
        return False

    try:
        with open(metadata_path) as f:
            package_paths = json.load(f).get("package_paths", [])

        for package_path in package_paths:
            if package_path in _loaded_extension_paths:
                continue  # Already loaded

            logger.info(f"Loading extensions from: {package_path}")
            print(f"  Loading extensions from: {package_path}")
            try:
                Environment._load_extensions(package_path)
                _loaded_extension_paths.add(package_path)
                new_extensions_loaded = True
            except Exception as e:
                logger.warning(
                    f"Failed to load extensions from {package_path}: {e}"
                )

        if new_extensions_loaded:
            from gimle.hugin.ui.components.base import ComponentRegistry

            registered = ComponentRegistry.list_registered_types()
            print(f"  Registered UI components: {registered}")

    except Exception as e:
        logger.warning(f"Failed to read metadata file: {e}")

    return new_extensions_loaded


# Global queue for storage update events
_update_queue: "queue.Queue[Dict[str, str]]" = queue.Queue()

# Cache for discover_agents results (to avoid repeated slow disk reads)
_agents_cache_lock = threading.Lock()
_agents_cache_data: List[Dict[str, Any]] = []
_agents_cache_timestamp: float = 0.0
_agents_cache_ttl: float = 3.0  # Cache TTL in seconds


def to_jsonable(value: Any) -> Any:
    """Convert common framework objects into JSON-serializable structures."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    # Common containers
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, set):
        return [to_jsonable(v) for v in value]

    # pathlib / bytes
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return str(value)

    # datetime-like
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:
            pass

    # dataclasses (instances only, not classes)
    if is_dataclass(value) and not isinstance(value, type):
        return to_jsonable(asdict(value))

    # Framework objects often provide to_dict()
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return to_jsonable(to_dict())
        except Exception:
            pass

    # Fallback
    return str(value)


def _storage_update_callback(obj_type: str, obj_id: str) -> None:
    """For storage updates - pushes to update queue.

    Note: We no longer invalidate the cache here. The cache TTL (3 seconds)
    provides natural rate limiting. This prevents cache thrashing when an
    agent is actively creating many interactions.
    """
    update = {"type": "update", "object_type": obj_type, "object_id": obj_id}
    _update_queue.put(update)
    logger.debug(f"Storage update: {obj_type} {obj_id}")


def get_monitor_callback() -> Callable[[str, str], None]:
    """Get the callback function for storage updates.

    Use this when creating a LocalStorage instance that should trigger
    live updates in the monitor (when running in the same process).

    Returns:
        Callable[[str, str], None]: Callback function that takes
            (object_type, object_id) as parameters.

    Example:
        storage = LocalStorage(base_path="./storage",
                             callback=get_monitor_callback())
    """
    return _storage_update_callback


def _watch_storage_directory(
    storage_path: Path, stop_event: threading.Event
) -> None:
    """Watch storage directory for file changes and trigger callbacks.

    This provides live updates when agents are running in separate processes.
    When agents run in the same process, they can use LocalStorage with
    _storage_update_callback directly for more immediate updates.
    """
    # Track file modification times
    file_mtimes: Dict[Path, float] = {}
    did_initial_scan = False

    def scan_directory() -> None:
        """Scan directory and detect new or modified files."""
        if not storage_path.exists():
            return

        # Scan subdirectories: sessions/, agents/, interactions/, artifacts/
        subdirs = ["sessions", "agents", "interactions", "artifacts"]
        type_by_subdir = {
            "sessions": "session",
            "agents": "agent",
            "interactions": "interaction",
            "artifacts": "artifact",
        }
        for subdir in subdirs:
            subdir_path = storage_path / subdir
            if not subdir_path.exists():
                continue

            for file_path in subdir_path.glob("*"):
                if not file_path.is_file():
                    continue

                try:
                    mtime = file_path.stat().st_mtime
                    uuid = file_path.name

                    # Check if file is new or modified
                    if (
                        file_path not in file_mtimes
                        or file_mtimes[file_path] < mtime
                    ):
                        file_mtimes[file_path] = mtime

                        # Don't spam events for existing files on initial scan
                        if not did_initial_scan:
                            continue

                        # Infer object type from subdirectory (more reliable than file content)
                        obj_type = type_by_subdir.get(subdir, "unknown")
                        _storage_update_callback(obj_type, uuid)
                except Exception as e:
                    logger.debug(f"Error checking file {file_path}: {e}")

    # Initial scan
    scan_directory()
    did_initial_scan = True

    # Watch for changes every second
    while not stop_event.is_set():
        scan_directory()
        stop_event.wait(1.0)


class AgentMonitorHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for agent monitoring."""

    _storage_path: Optional[str] = None
    _config_path: Optional[str] = None
    _environment: Optional["Environment"] = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the agent monitor HTTP request handler."""
        super().__init__(*args, **kwargs)

    @property
    def storage_path(self) -> Path:
        """Get the storage path."""
        if not AgentMonitorHTTPRequestHandler._storage_path:
            return Path("./storage")
        return Path(AgentMonitorHTTPRequestHandler._storage_path)

    @property
    def config_path(self) -> Optional[str]:
        """Get the config path."""
        return AgentMonitorHTTPRequestHandler._config_path

    def log_message(self, format: str, *args: Any) -> None:
        """Override to use logger instead of stderr."""
        logger.info(f"{self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query_params: Dict[str, List[str]] = parse_qs(parsed_path.query)

        if path == "/" or path == "/index.html":
            self.serve_main_page()
        elif path.startswith("/static/"):
            self.serve_static(path[8:])  # Remove '/static/' prefix
        elif path == "/api/agents":
            self.serve_agents_list()
        elif path == "/api/session":
            session_id = query_params.get("id", [None])[0]
            if session_id:
                self.serve_session_data(session_id)
            else:
                self.send_error(400, "Missing session id parameter")
        elif path == "/api/agent":
            agent_id = query_params.get("id", [None])[0]
            if agent_id:
                self.serve_agent_data(agent_id)
            else:
                self.send_error(400, "Missing agent id parameter")
        elif path == "/api/artifact":
            artifact_id = query_params.get("id", [None])[0]
            if artifact_id:
                self.serve_artifact_data(artifact_id)
            else:
                self.send_error(400, "Missing artifact id parameter")
        elif path == "/api/feedback":
            artifact_id = query_params.get("artifact_id", [None])[0]
            if artifact_id:
                self.serve_feedback_list(artifact_id)
            else:
                self.send_error(400, "Missing artifact_id parameter")
        elif path == "/api/artifact-download":
            artifact_id = query_params.get("id", [None])[0]
            if artifact_id:
                self.serve_artifact_download(artifact_id)
            else:
                self.send_error(400, "Missing artifact id parameter")
        elif path == "/api/interaction":
            interaction_id = query_params.get("id", [None])[0]
            if interaction_id:
                self.serve_interaction_detail(interaction_id)
            else:
                self.send_error(400, "Missing interaction id parameter")
        elif path == "/api/updates":
            logger.info("Client connecting to updates stream")
            self.serve_updates_stream()
        elif path == "/artifact-viewer":
            artifact_id = query_params.get("id", [None])[0]
            if artifact_id:
                self.serve_artifact_viewer(artifact_id)
            else:
                self.send_error(400, "Missing artifact id parameter")
        else:
            self.send_error(404, "Not Found")

    def do_DELETE(self) -> None:
        """Handle DELETE requests."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query_params: Dict[str, List[str]] = parse_qs(parsed_path.query)

        if path == "/api/session":
            session_id = query_params.get("id", [None])[0]
            if session_id:
                self.delete_session(session_id)
            else:
                self.send_error(400, "Missing session id parameter")
        else:
            self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        """Handle POST requests."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        if path == "/api/feedback":
            self.handle_submit_feedback()
        else:
            self.send_error(404, "Not Found")

    def serve_feedback_list(self, artifact_id: str) -> None:
        """Serve all feedback for an artifact as JSON."""
        try:
            storage = LocalStorage(base_path=str(self.storage_path))
            fb_ids = storage.list_feedback(artifact_id=artifact_id)

            feedback_list = []
            for fb_id in fb_ids:
                try:
                    fb = storage.load_feedback(fb_id)
                    feedback_list.append(fb.to_dict())
                except Exception:
                    continue

            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(feedback_list).encode("utf-8"))
        except Exception as e:
            logger.error("Error loading feedback: %s", e)
            self.send_error(500, "Internal server error")

    def handle_submit_feedback(self) -> None:
        """Handle POST /api/feedback to submit human rating."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            artifact_id = data.get("artifact_id")
            rating = data.get("rating")
            comment = data.get("comment")

            if not artifact_id or rating is None:
                self.send_error(400, "Missing artifact_id or rating")
                return

            # Validate rating type and range
            if not isinstance(rating, (int, float)):
                self.send_error(400, "Rating must be a number")
                return
            if isinstance(rating, float) and rating != int(rating):
                self.send_error(400, "Rating must be an integer")
                return
            rating = int(rating)
            if rating < 1 or rating > 5:
                self.send_error(400, "Rating must be between 1 and 5")
                return

            # Validate comment length server-side
            if comment and len(comment) > 200:
                self.send_error(400, "Comment exceeds 200 characters")
                return

            storage = LocalStorage(base_path=str(self.storage_path))

            # Verify artifact exists
            try:
                storage.load_artifact(artifact_id)
            except Exception:
                self.send_error(404, f"Artifact {artifact_id} not found")
                return

            # Check for existing human feedback on this artifact
            for fb_id in storage.list_feedback(artifact_id):
                try:
                    existing = storage.load_feedback(fb_id)
                    if existing.source == "human":
                        self.send_error(409, "Already rated this artifact")
                        return
                except (ValueError, OSError):
                    continue

            feedback = ArtifactFeedback(
                artifact_id=artifact_id,
                rating=rating,
                comment=comment or None,
                agent_id=None,
                source="human",
            )
            storage.save_feedback(feedback)

            response = {
                "success": True,
                "feedback_id": feedback.id,
            }
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))

            logger.info(
                "Saved human feedback %s for artifact %s " "(rating=%d)",
                feedback.id,
                artifact_id,
                rating,
            )
        except (ValueError, TypeError) as e:
            self.send_error(400, f"Invalid feedback: {e}")
        except Exception as e:
            logger.error("Error saving feedback: %s", e)
            self.send_error(500, "Internal server error")

    def serve_static(self, path: str) -> None:
        """Serve a static file."""
        content = serve_static_file(path)
        if content is None:
            self.send_error(404, "Static file not found")
            return

        mime_type = get_mime_type(path)
        self.send_response(200)
        self.send_header("Content-type", mime_type)
        self.send_header("Content-Length", str(len(content)))
        # Avoid stale JS/CSS during development
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(content)

    def delete_session(self, session_id: str) -> None:
        """Delete a session and all its components."""
        try:
            storage = LocalStorage(base_path=str(self.storage_path))
            environment = Environment(storage=storage)

            # Load the session
            session = storage.load_session(session_id, environment=environment)

            # Delete the session (cascades to agents, interactions, artifacts)
            storage.delete_session(session)

            # Send success response
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            response = {
                "success": True,
                "message": "Session deleted successfully",
            }
            self.wfile.write(json.dumps(response).encode("utf-8"))

            logger.info(f"Deleted session: {session_id}")
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            self.send_error(500, f"Error deleting session: {str(e)}")

    def discover_agents(self) -> List[Dict[str, Any]]:
        """Discover all agents from storage.

        Uses lightweight file reading instead of full deserialization to avoid
        loading all interactions. Thread-safe with lock to prevent thundering
        herd problem.
        """
        global _agents_cache_data, _agents_cache_timestamp

        # Quick check without lock first
        now = time.time()
        if (
            _agents_cache_data
            and (now - _agents_cache_timestamp) < _agents_cache_ttl
        ):
            logger.debug("Returning cached agents list")
            return _agents_cache_data

        # Try to acquire lock - if another thread is refreshing, return stale
        acquired = _agents_cache_lock.acquire(blocking=False)
        if not acquired:
            # Another thread is refreshing, return stale cache if available
            logger.debug("Cache refresh in progress, returning stale data")
            return _agents_cache_data if _agents_cache_data else []

        try:
            # Double-check cache after acquiring lock
            now = time.time()
            if (
                _agents_cache_data
                and (now - _agents_cache_timestamp) < _agents_cache_ttl
            ):
                logger.debug("Cache was refreshed while waiting for lock")
                return _agents_cache_data

            agents: List[Dict[str, Any]] = []
            storage_path = self.storage_path

            if not storage_path.exists():
                # Update cache even for empty result
                _agents_cache_data = agents
                _agents_cache_timestamp = time.time()
                return agents

            try:
                start_time = time.time()
                logger.debug(f"Discovering agents in {storage_path}")

                # Read session files directly (lightweight)
                sessions_dir = storage_path / "sessions"
                agents_dir = storage_path / "agents"

                if not sessions_dir.exists():
                    # Update cache even for empty result
                    _agents_cache_data = agents
                    _agents_cache_timestamp = time.time()
                    return agents

                for session_file in sessions_dir.iterdir():
                    if not session_file.is_file():
                        continue

                    try:
                        session_id = session_file.name
                        with open(session_file, "r") as f:
                            session_data = json.load(f)

                        session_created_at = session_data.get("created_at")
                        agent_uuids = session_data.get("agents", [])

                        # Get session last modified time
                        session_mtime = session_file.stat().st_mtime

                        for agent_uuid in agent_uuids:
                            agent_file = agents_dir / agent_uuid
                            if not agent_file.exists():
                                continue

                            try:
                                with open(agent_file, "r") as f:
                                    agent_data = json.load(f)

                                config_data = agent_data.get("config", {})
                                config_name = config_data.get("name", "Unknown")
                                stack_data = agent_data.get("stack", {})

                                # Count interactions/artifacts from UUIDs
                                # (don't load full interaction data)
                                interaction_uuids = stack_data.get(
                                    "interactions", []
                                )
                                artifact_uuids = stack_data.get("artifacts", [])

                                # Get agent file mtime
                                agent_mtime = agent_file.stat().st_mtime
                                last_modified = max(session_mtime, agent_mtime)

                                agents.append(
                                    {
                                        "id": agent_uuid,
                                        "session_id": session_id,
                                        "config_name": config_name,
                                        "num_interactions": len(
                                            interaction_uuids
                                        ),
                                        "num_artifacts": len(artifact_uuids),
                                        "last_modified": last_modified,
                                        "created_at": agent_data.get(
                                            "created_at"
                                        ),
                                        "session_created_at": session_created_at,
                                    }
                                )
                            except Exception as e:
                                logger.debug(
                                    f"Skipping agent {agent_uuid}: {e}"
                                )
                                continue
                    except Exception as e:
                        logger.debug(
                            f"Skipping session {session_file.name}: {e}"
                        )
                        continue

            except Exception as e:
                logger.error(f"Error discovering agents: {e}")

            # Sort by created_at (newest first)
            agents.sort(
                key=lambda x: x.get("created_at") or x.get("last_modified", 0),
                reverse=True,
            )
            elapsed = time.time() - start_time
            logger.info(f"Discovered {len(agents)} agent(s) in {elapsed:.2f}s")

            # Update cache
            _agents_cache_data = agents
            _agents_cache_timestamp = time.time()

            return agents
        finally:
            _agents_cache_lock.release()

    def load_agent(self, agent_id: str) -> Optional["Agent"]:
        """Load an agent by ID - searches through sessions."""
        try:
            from gimle.hugin.agent.session import Session

            logger.info(f"Loading agent {agent_id}")
            storage = LocalStorage(base_path=str(self.storage_path))
            environment = Environment(storage=storage)

            # First check if it's an agent file directly
            agent_ids = storage.list_agents()
            if agent_id in agent_ids:
                logger.info(f"Found agent file: {agent_id}")
                temp_session = Session(environment=environment)
                agent = storage.load_agent(agent_id, session=temp_session)
                logger.info(f"Loaded agent: {agent.config.name}")
                return agent

            # Search through sessions to find the agent
            session_ids = storage.list_sessions()
            count = len(session_ids)
            logger.info(f"Scanning {count} session(s) to find agent")

            for session_id in session_ids:
                try:
                    logger.debug(f"Loading session: {session_id}")
                    session = storage.load_session(
                        session_id, environment=environment
                    )
                    logger.debug(
                        f"Loaded session with {len(session.agents)} agent(s)"
                    )

                    for agent in session.agents:
                        if agent.id == agent_id:
                            sid = session.id
                            logger.info(f"Found agent {agent_id} in {sid}")
                            return agent

                except Exception as e:
                    logger.debug(f"Skipping session {session_id}: {e}")
                    continue

            logger.warning(f"Agent {agent_id} not found in any session")
            return None

        except Exception as e:
            logger.error(f"Error loading agent {agent_id}: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return None

    def load_agent_lightweight(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Load agent with interaction metadata only (no artifact content).

        This is a fast alternative to load_agent() that reads JSON files
        directly without full deserialization. Used for monitor timeline
        rendering where we need interaction metadata but not artifact content.

        Returns a dictionary with agent info and interaction summaries,
        or None if agent not found.
        """
        agents_dir = self.storage_path / "agents"
        agent_file = agents_dir / agent_id

        if not agent_file.exists():
            logger.debug(f"Agent file not found: {agent_id}")
            return None

        try:
            start_time = time.time()

            # Read agent JSON directly
            with open(agent_file, "r") as f:
                agent_data = json.load(f)

            # Load interaction metadata (not full interactions with artifacts)
            storage = LocalStorage(base_path=str(self.storage_path))
            interaction_summaries = []

            stack_data = agent_data.get("stack", {})
            interaction_uuids = stack_data.get("interactions", [])

            for int_uuid in interaction_uuids:
                try:
                    raw = storage.load_interaction_metadata(int_uuid)
                    # Interaction JSON is wrapped: {"type": "...", "data": {...}}
                    int_type = raw.get("type")
                    int_data = raw.get("data", {})

                    # Load artifact metadata (lightweight - no full rendering)
                    artifact_ids = int_data.get("artifacts", [])
                    artifacts_metadata = []
                    for artifact_id in artifact_ids:
                        try:
                            artifact_meta = storage.load_artifact_metadata(
                                artifact_id
                            )
                            artifacts_metadata.append(artifact_meta)
                        except Exception as e:
                            logger.debug(
                                f"Skipping artifact {artifact_id}: {e}"
                            )
                            # Include placeholder for missing artifacts
                            artifacts_metadata.append(
                                {
                                    "id": artifact_id,
                                    "type": "Unknown",
                                    "preview": "Failed to load",
                                }
                            )

                    # Extract only what we need for timeline/flowchart
                    task_data = int_data.get("task")
                    summary = {
                        "id": int_uuid,
                        "type": int_type,
                        "created_at": int_data.get("created_at"),
                        "branch": int_data.get("branch"),
                        "artifact_ids": artifact_ids,
                        "artifacts": artifacts_metadata,  # Lightweight metadata
                        # Type-specific fields for rendering
                        "tool": int_data.get("tool"),
                        "tool_name": int_data.get("tool_name"),
                        "task_name": (
                            task_data.get("name") if task_data else None
                        ),
                        "finish_type": int_data.get("finish_type"),
                        "summary": int_data.get("summary"),
                        "is_error": int_data.get("is_error"),
                        "config_name": (
                            int_data.get("config", {}).get("name")
                            if int_data.get("config")
                            else None
                        ),
                        "next_task_name": int_data.get("next_task_name"),
                        "include_in_context": int_data.get(
                            "include_in_context", True
                        ),
                    }
                    interaction_summaries.append(summary)
                except Exception as e:
                    logger.debug(f"Skipping interaction {int_uuid}: {e}")
                    continue

            elapsed = time.time() - start_time
            logger.info(
                f"Loaded agent {agent_id} lightweight: "
                f"{len(interaction_summaries)} interactions in {elapsed:.2f}s"
            )

            return {
                "id": agent_id,
                "config": agent_data.get("config", {}),
                "interactions": interaction_summaries,
                "created_at": agent_data.get("created_at"),
                "stack": {
                    "artifacts": stack_data.get("artifacts", []),
                },
            }

        except Exception as e:
            logger.error(f"Error loading agent lightweight {agent_id}: {e}")
            return None

    def serve_main_page(self) -> None:
        """Serve the main monitoring page."""
        html = self.generate_monitor_page()
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def serve_agents_list(self) -> None:
        """Serve list of available agents."""
        agents = self.discover_agents()
        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(agents).encode("utf-8"))

    def _render_agent_html_lightweight(self, agent_data: Dict[str, Any]) -> str:
        """Render agent HTML from lightweight data (no artifact loading).

        This generates the same timeline/flowchart HTML as generate_agent_page()
        but works with interaction metadata instead of full Interaction objects.
        """
        from gimle.hugin.ui.static import render_template

        interactions = agent_data.get("interactions", [])
        config = agent_data.get("config", {})

        # Generate compact config header
        config_html = ""
        if config:
            config_items = []
            config_items.append(
                f"<strong>{config.get('name', 'Unknown')}</strong>"
            )
            if config.get("llm_model"):
                config_items.append(f"Model: {config['llm_model']}")
            if config.get("system_template"):
                config_items.append(f"Template: {config['system_template']}")
            if config.get("tools"):
                tools = config["tools"]
                tools_list = (
                    ", ".join(tools[:3]) if len(tools) > 3 else ", ".join(tools)
                )
                if len(tools) > 3:
                    tools_list += f" (+{len(tools) - 3} more)"
                config_items.append(f"Tools: {tools_list}")
            config_html = (
                "<div class='compact-header'>"
                f"<div class='compact-config'>{' • '.join(config_items)}</div>"
                "</div>\n"
            )

        # Build timeline HTML
        timeline_html = self._render_timeline_lightweight(interactions)

        # Build flowchart HTML
        flowchart_html = self._render_flowchart_lightweight(interactions)

        # Build artifacts list HTML (placeholders for lazy loading)
        artifacts_list_html = self._render_artifacts_list_lightweight(
            interactions
        )

        # Build artifacts JSON (for frontend)
        artifacts_data: Dict[str, List[Dict[str, Any]]] = {}
        for interaction in interactions:
            int_id = interaction.get("id")
            artifact_ids = interaction.get("artifact_ids", [])
            if int_id and artifact_ids:
                artifacts_data[int_id] = [
                    {"id": aid, "type": "pending", "preview": "Loading..."}
                    for aid in artifact_ids
                ]
        artifacts_json = json.dumps(artifacts_data)

        # Combine into stack HTML
        stack_html = timeline_html + flowchart_html

        return render_template(
            "agent.html",
            title=f"Agent: {config.get('name', 'Unknown')}",
            config_html=config_html,
            agent_id=agent_data.get("id", "unknown"),
            num_interactions=str(len(interactions)),
            num_artifacts=str(
                len(agent_data.get("stack", {}).get("artifacts", []))
            ),
            stack_html=stack_html,
            artifacts_list_html=artifacts_list_html,
            artifacts_json=artifacts_json,
        )

    def _render_timeline_lightweight(
        self, interactions: List[Dict[str, Any]]
    ) -> str:
        """Render timeline from interaction metadata."""
        from datetime import datetime as dt

        html_parts = []
        html_parts.append("<div class='timeline-section'>")
        html_parts.append(
            f"<h2>Timeline ({len(interactions)} interactions)</h2>"
        )
        html_parts.append("<div class='timeline-view'>")
        html_parts.append("<div class='timeline-container'>")

        # Parse timestamps
        interactions_with_time = []
        for interaction in interactions:
            created_at = interaction.get("created_at")
            if created_at:
                try:
                    parsed = dt.fromisoformat(created_at.replace("Z", "+00:00"))
                    interactions_with_time.append((interaction, parsed))
                except Exception:
                    pass

        if not interactions_with_time:
            html_parts.append(
                "<p style='color: #7f8c8d; font-size: 0.9em;'>"
                "No timestamp data available</p>"
            )
            html_parts.append("</div></div></div>")
            return "\n".join(html_parts)

        for i, (interaction, parsed) in enumerate(interactions_with_time):
            int_type = interaction.get("type", "Unknown")
            int_id = interaction.get("id", f"interaction-{i}")
            time_str = parsed.strftime("%H:%M:%S")

            branch = interaction.get("branch")
            branch_display = branch if branch else "main"
            branch_class = "branch-main" if not branch else "branch-alt"

            gap_html = ""
            if i > 0:
                prev_dt = interactions_with_time[i - 1][1]
                gap = (parsed - prev_dt).total_seconds()
                if gap > 0.1:
                    if gap < 1:
                        gap_str = f"{gap*1000:.0f}ms"
                    elif gap < 60:
                        gap_str = f"{gap:.1f}s"
                    else:
                        gap_str = f"{gap/60:.1f}m"
                    gap_html = f'<span class="timeline-gap">+{gap_str}</span>'

            color_class = self._get_color_class(int_type)
            detail_html = self._get_timeline_detail_lightweight(interaction)

            html_parts.append(
                f"""
                <div class="timeline-item {color_class}"
                     data-interaction-id="{int_id}"
                     onclick="selectInteraction('{int_id}'); showInteractionDetails('{int_id}')"
                     style="cursor: pointer;">
                    <span class="timeline-time">{time_str}</span>
                    {gap_html}
                    <span class="timeline-type">{int_type}</span>
                    {detail_html}
                    <span class="timeline-branch {branch_class}">{branch_display}</span>
                </div>
                """
            )

        html_parts.append("</div></div></div>")
        return "\n".join(html_parts)

    def _render_flowchart_lightweight(
        self, interactions: List[Dict[str, Any]]
    ) -> str:
        """Render flowchart from interaction metadata."""
        html_parts = []

        if not interactions:
            html_parts.append("<div class='stack-visualization'>")
            html_parts.append("<h2>Stack Flow (0 interactions)</h2>")
            html_parts.append("<p>No interactions yet.</p>")
            html_parts.append("</div>")
            return "\n".join(html_parts)

        html_parts.append("<div class='stack-visualization'>")
        html_parts.append(
            f"<h2 class='expanded'>Stack Flow ({len(interactions)} interactions)</h2>"
        )
        html_parts.append("<div class='flowchart expanded'>")

        # Group by branch
        main_branch: List[Dict[str, Any]] = []
        branches: Dict[str, List[Dict[str, Any]]] = {}
        branch_fork_indices: Dict[str, int] = {}

        for interaction in interactions:
            branch = interaction.get("branch")
            if branch:
                if branch not in branches:
                    branches[branch] = []
                    branch_fork_indices[branch] = len(main_branch)
                branches[branch].append(interaction)
            else:
                main_branch.append(interaction)

        html_parts.append("<div class='flowchart-columns'>")

        # Main branch
        html_parts.append(
            "<div class='flowchart-column flowchart-column-main'>"
        )
        html_parts.append("<div class='flowchart-column-header'>main</div>")
        html_parts.append("<div class='flowchart-column-content'>")
        for i, interaction in enumerate(main_branch):
            html_parts.append(
                self._render_interaction_box_lightweight(
                    interaction, i, len(main_branch)
                )
            )
        html_parts.append("</div></div>")

        # Branch columns
        for branch_name, branch_ints in branches.items():
            fork_index = branch_fork_indices.get(branch_name, 0)
            html_parts.append(
                f"<div class='flowchart-column flowchart-column-branch' "
                f"data-branch='{branch_name}' data-fork-index='{fork_index}'>"
            )
            html_parts.append(
                f"<div class='flowchart-column-header'>{branch_name}</div>"
            )
            html_parts.append("<div class='flowchart-column-content'>")
            if fork_index > 0:
                html_parts.append(
                    f"<div class='flowchart-branch-spacer' data-height='{fork_index}'></div>"
                )
            for i, interaction in enumerate(branch_ints):
                html_parts.append(
                    self._render_interaction_box_lightweight(
                        interaction, i, len(branch_ints), branch_name
                    )
                )
            html_parts.append("</div></div>")

        html_parts.append("</div></div></div>")
        return "\n".join(html_parts)

    def _render_interaction_box_lightweight(
        self,
        interaction: Dict[str, Any],
        index: int,
        total: int,
        branch: Optional[str] = None,
    ) -> str:
        """Render a single interaction box from metadata."""
        int_type = interaction.get("type", "Unknown")
        int_id = interaction.get("id", f"interaction-{index}")
        color_class = self._get_color_class(int_type)

        # Build details string
        details_parts = []
        if interaction.get("task_name"):
            details_parts.append(f"Task: {interaction['task_name']}")
        if interaction.get("tool") or interaction.get("tool_name"):
            tool = interaction.get("tool") or interaction.get("tool_name")
            details_parts.append(f"Tool: {tool}")
        if interaction.get("finish_type"):
            details_parts.append(f"Finish: {interaction['finish_type']}")
        if interaction.get("summary"):
            summary = interaction["summary"]
            if len(summary) > 50:
                summary = summary[:50] + "..."
            details_parts.append(f"Summary: {summary}")
        details = " | ".join(details_parts)

        # Format timestamp
        timestamp = None
        created_at = interaction.get("created_at")
        if created_at:
            try:
                from datetime import datetime as dt

                parsed = dt.fromisoformat(created_at.replace("Z", "+00:00"))
                timestamp = parsed.strftime("%H:%M:%S")
            except Exception:
                pass

        has_artifacts = bool(interaction.get("artifact_ids"))
        artifact_count = len(interaction.get("artifact_ids", []))
        clickable_class = "flowchart-box-clickable" if has_artifacts else ""
        branch_display = branch if branch else "main"

        # Build optional HTML parts separately to avoid f-string escaping issues
        artifacts_badge = ""
        if has_artifacts:
            artifacts_badge = (
                f'<span class="flowchart-box-artifacts-badge" '
                f"onclick=\"scrollToArtifacts('{int_id}'); event.stopPropagation();\" "
                f'style="cursor: pointer;">📎 {artifact_count}</span>'
            )

        timestamp_html = ""
        if timestamp:
            timestamp_html = (
                f'<span class="flowchart-box-timestamp">{timestamp}</span>'
            )

        details_html = ""
        if details:
            details_html = f'<div class="flowchart-box-details">{details}</div>'

        box_html = f"""
        <div class="flowchart-item {color_class}" data-interaction-id="{int_id}">
            <div class="flowchart-box {clickable_class}" data-has-artifacts="{str(has_artifacts).lower()}">
                <div class="flowchart-box-header">
                    <span class="flowchart-box-type" onclick="showInteractionDetails('{int_id}')" style="cursor: pointer;">{int_type}</span>
                    <span class="flowchart-box-branch">{branch_display}</span>
                    {artifacts_badge}
                    {timestamp_html}
                </div>
                {details_html}
            </div>
        </div>
        """

        if index < total - 1:
            box_html += '<div class="flowchart-arrow">↓</div>'

        return box_html

    def _render_artifacts_list_lightweight(
        self, interactions: List[Dict[str, Any]]
    ) -> str:
        """Render artifacts list from interaction metadata."""
        import html as html_module

        # Collect all artifacts across interactions (using preloaded metadata)
        all_artifacts = []
        for interaction in interactions:
            int_id = interaction.get("id")
            int_type = interaction.get("type", "Unknown")
            tool_name = interaction.get("tool") or interaction.get("tool_name")
            # Use artifact metadata (type, format, preview) from lightweight load
            artifacts_metadata = interaction.get("artifacts", [])

            for artifact_meta in artifacts_metadata:
                all_artifacts.append(
                    {
                        "artifact_id": artifact_meta.get("id"),
                        "artifact_type": artifact_meta.get("type", "Unknown"),
                        "artifact_format": artifact_meta.get("format"),
                        "artifact_preview": artifact_meta.get("preview", ""),
                        "artifact_created_at": artifact_meta.get("created_at"),
                        "interaction_id": int_id,
                        "interaction_type": int_type,
                        "tool_name": tool_name,
                    }
                )

        if not all_artifacts:
            return '<p class="artifacts-list-empty">No artifacts in this session.</p>'

        parts = []
        for item in all_artifacts:
            artifact_id = item["artifact_id"]
            artifact_type = item["artifact_type"]
            artifact_format = item.get("artifact_format")
            int_id = item["interaction_id"]
            int_type = item["interaction_type"]
            tool_name = item.get("tool_name")

            short_artifact_id = (
                artifact_id[:8] + "..." if len(artifact_id) > 8 else artifact_id
            )
            short_int_id = int_id[:8] + "..." if len(int_id) > 8 else int_id

            tool_html = ""
            if tool_name:
                tool_html = f'<span class="artifacts-list-item-tool">{html_module.escape(str(tool_name))}</span>'

            format_html = ""
            if artifact_format:
                format_html = f'<span class="artifacts-list-item-format">{html_module.escape(str(artifact_format))}</span>'

            parts.append(
                f"""<div class="artifacts-list-item"
                         data-artifact-id="{artifact_id}"
                         data-interaction-id="{int_id}">
                    <div class="artifacts-list-item-header">
                        <div class="artifacts-list-item-title">
                            <span class="artifacts-list-item-type">{html_module.escape(artifact_type)}</span>
                            {format_html}
                            {tool_html}
                        </div>
                        <div class="artifacts-list-item-meta">
                            <span class="artifacts-list-item-id">{short_artifact_id}</span>
                            <button class="artifacts-list-item-open"
                                    onclick="openArtifactModal('{artifact_id}', '{int_id}'); event.stopPropagation();"
                                    title="Open artifact">Open</button>
                        </div>
                    </div>
                    <div class="artifacts-list-item-interaction"
                         onclick="showInteractionDetails('{int_id}', true); event.stopPropagation();">
                        <span class="artifacts-list-item-interaction-label">From:</span>
                        <span class="artifacts-list-item-interaction-type">{int_type}</span>
                        <span class="artifacts-list-item-interaction-id">{short_int_id}</span>
                    </div>
                </div>"""
            )

        return "\n".join(parts)

    def _get_color_class(self, interaction_type: str) -> str:
        """Get CSS color class for interaction type."""
        color_map = {
            "TaskDefinition": "flowchart-purple",
            "TaskChain": "flowchart-purple",
            "AskOracle": "flowchart-yellow",
            "OracleResponse": "flowchart-yellow",
            "ToolCall": "flowchart-blue",
            "ToolResult": "flowchart-blue",
            "AskHuman": "flowchart-yellow",
            "HumanResponse": "flowchart-yellow",
            "ExternalInput": "flowchart-yellow",
            "TaskResult": "flowchart-green",
        }
        return color_map.get(interaction_type, "flowchart-gray")

    def _get_timeline_detail_lightweight(
        self, interaction: Dict[str, Any]
    ) -> str:
        """Get detail HTML for timeline view from metadata."""
        int_type = interaction.get("type", "")

        if int_type == "ToolCall":
            tool = interaction.get("tool")
            if tool:
                return f'<span class="timeline-detail timeline-detail-tool">{tool}</span>'

        if int_type == "ToolResult":
            tool_name = interaction.get("tool_name")
            if tool_name:
                return f'<span class="timeline-detail timeline-detail-tool">{tool_name}</span>'

        if int_type == "TaskDefinition":
            task_name = interaction.get("task_name")
            if task_name:
                return f'<span class="timeline-detail timeline-detail-task">{task_name}</span>'

        if int_type == "TaskResult":
            finish_type = interaction.get("finish_type")
            if finish_type:
                return f'<span class="timeline-detail timeline-detail-result">{finish_type}</span>'

        if int_type == "AgentCall":
            config_name = interaction.get("config_name")
            if config_name:
                return f'<span class="timeline-detail timeline-detail-task">{config_name}</span>'

        if int_type == "TaskChain":
            next_task = interaction.get("next_task_name")
            if next_task:
                return f'<span class="timeline-detail timeline-detail-task">{next_task}</span>'

        return ""

    def serve_session_data(self, session_id: str) -> None:
        """Serve session details and agents list as JSON (lightweight loading)."""
        try:
            storage_path = self.storage_path
            session_file = storage_path / "sessions" / session_id

            if not session_file.exists():
                self.send_error(404, "Session not found")
                return

            # Read session JSON directly (lightweight)
            with open(session_file, "r") as f:
                session_data = json.load(f)

            session_last_modified = session_file.stat().st_mtime
            agent_uuids = session_data.get("agents", [])

            # Read agent data directly (no full deserialization)
            agents_dir = storage_path / "agents"
            agents: List[Dict[str, Any]] = []

            for agent_uuid in agent_uuids:
                agent_file = agents_dir / agent_uuid
                if not agent_file.exists():
                    continue

                try:
                    with open(agent_file, "r") as f:
                        agent_data = json.load(f)

                    config_data = agent_data.get("config", {})
                    stack_data = agent_data.get("stack", {})
                    interaction_uuids = stack_data.get("interactions", [])
                    artifact_uuids = stack_data.get("artifacts", [])
                    agent_last_modified = agent_file.stat().st_mtime

                    agents.append(
                        {
                            "id": agent_uuid,
                            "session_id": session_id,
                            "config_name": config_data.get("name", "Unknown"),
                            "num_interactions": len(interaction_uuids),
                            "num_artifacts": len(artifact_uuids),
                            "last_modified": agent_last_modified
                            or session_last_modified,
                            "created_at": agent_data.get("created_at"),
                        }
                    )
                except Exception as e:
                    logger.debug(f"Skipping agent {agent_uuid}: {e}")
                    continue

            agents.sort(
                key=lambda a: a.get("last_modified") or 0,
                reverse=True,
            )

            payload: Dict[str, Any] = {
                "id": session_id,
                "created_at": session_data.get("created_at"),
                "last_modified": session_last_modified,
                "num_agents": len(agents),
                "agents": agents,
            }

            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
        except FileNotFoundError:
            self.send_error(404, "Session not found")
        except Exception as e:
            logger.error(f"Error loading session {session_id}: {e}")
            self.send_error(500, f"Error loading session: {str(e)}")

    def serve_agent_data(self, agent_id: str) -> None:
        """Serve agent data as JSON (uses lightweight loading for speed).

        This method uses load_agent_lightweight() to avoid loading all artifacts
        upfront. Artifacts are loaded on-demand via /api/interaction endpoint.
        """
        # Check for new extensions before rendering (handles late metadata writes)
        load_extensions_from_storage(self.storage_path)

        agent_data = self.load_agent_lightweight(agent_id)
        if not agent_data:
            self.send_error(404, "Agent not found")
            return

        try:
            # Generate HTML from lightweight data
            html_content = self._render_agent_html_lightweight(agent_data)

            # Build interactions data (for details panel)
            interactions_data: Dict[str, Dict[str, Any]] = {}
            for interaction in agent_data.get("interactions", []):
                int_id = interaction.get("id")
                if int_id:
                    interactions_data[int_id] = interaction

            # Build artifacts data from lightweight metadata
            # Group artifacts by interaction for frontend
            artifacts_data: Dict[str, List[Dict[str, Any]]] = {}
            for interaction in agent_data.get("interactions", []):
                int_id = interaction.get("id")
                # Use pre-loaded artifact metadata (type, format, preview)
                artifacts_metadata = interaction.get("artifacts", [])
                if int_id and artifacts_metadata:
                    artifacts_data[int_id] = artifacts_metadata

            # Get agent details from lightweight data
            config = agent_data.get("config", {})
            cfg_name = config.get("name", "Unknown")
            num_interactions = len(agent_data.get("interactions", []))
            num_artifacts = len(
                agent_data.get("stack", {}).get("artifacts", [])
            )

            agent_details = {
                "id": agent_id,
                "config_name": cfg_name,
                "num_interactions": num_interactions,
                "num_artifacts": num_artifacts,
                "created_at": agent_data.get("created_at"),
            }

            if config:
                agent_details["config"] = {
                    "name": config.get("name"),
                    "llm_model": config.get("llm_model"),
                    "system_template": config.get("system_template"),
                    "tools": config.get("tools"),
                    "interactive": config.get("interactive"),
                }

            # Return as JSON
            response_data = {
                "html": html_content,
                "artifacts": artifacts_data,
                "interactions": interactions_data,
                "agent_details": agent_details,
                "lazy_loading": True,  # Signal frontend to use lazy loading
            }

            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                json.dumps(to_jsonable(response_data)).encode("utf-8")
            )
        except Exception as e:
            import traceback

            logger.error(f"Error rendering agent: {e}")
            logger.error(traceback.format_exc())
            self.send_error(500, f"Error rendering agent: {str(e)}")

    def _extract_interaction_fields(
        self, interaction: Any, details: Dict[str, Any]
    ) -> None:
        """Extract all relevant fields from an interaction."""
        # Add branch if present
        if hasattr(interaction, "branch") and interaction.branch:
            details["branch"] = interaction.branch

        # Add interaction-specific fields
        field_mappings = [
            ("task", "task"),
            ("tool", "tool"),
            ("args", "args"),
            ("reason", "reason"),
            ("result", "result"),
            ("prompt", "prompt"),
            ("template_inputs", "template_inputs"),
            ("finish_type", "finish_type"),
            ("summary", "summary"),
            ("is_error", "is_error"),
            ("tool_call_id", "tool_call_id"),
            ("tool_name", "tool_name"),
            # ToolResult-specific fields (deterministic tool chaining)
            ("next_tool", "next_tool"),
            ("next_tool_args", "next_tool_args"),
            ("response_interaction", "response_interaction"),
            ("response", "response"),
            ("created_at", "created_at"),
            ("agent_id", "agent_id"),
            ("config", "config"),
            ("task_result_id", "task_result_id"),
            ("caller_id", "caller_id"),
            # TaskChain-specific fields
            ("next_task_name", "next_task_name"),
            ("task_sequence", "task_sequence"),
            ("sequence_index", "sequence_index"),
            ("previous_result", "previous_result"),
            ("chain_config", "chain_config"),
            # Context inclusion (AskOracle, ToolResult)
            ("include_in_context", "include_in_context"),
            # AskHuman-specific fields
            ("question", "question"),
            # ExternalInput-specific fields
            ("input", "input"),
            # Waiting-specific fields
            ("status", "status"),
            ("condition", "condition"),
        ]

        for attr, key in field_mappings:
            if hasattr(interaction, attr):
                value = getattr(interaction, attr)
                if value is not None:
                    # Special handling for complex objects
                    if attr == "task" and hasattr(value, "name"):
                        details[key] = {
                            "name": getattr(value, "name", str(value)),
                            "description": getattr(value, "description", None),
                            "prompt": to_jsonable(
                                getattr(value, "prompt", None)
                            ),
                            "parameters": to_jsonable(
                                getattr(value, "parameters", None)
                            ),
                        }
                    elif attr == "config" and hasattr(value, "name"):
                        details["config_name"] = value.name
                    elif attr == "prompt":
                        if hasattr(value, "text"):
                            details[key] = {
                                "text": getattr(value, "text", None),
                                "type": getattr(value, "type", None),
                                "tool_use_id": getattr(
                                    value, "tool_use_id", None
                                ),
                            }
                        else:
                            details[key] = str(value)
                    elif attr == "condition" and hasattr(value, "evaluator"):
                        # Condition object with evaluator and parameters
                        details[key] = {
                            "evaluator": getattr(value, "evaluator", None),
                            "parameters": to_jsonable(
                                getattr(value, "parameters", None)
                            ),
                        }
                    else:
                        details[key] = to_jsonable(value)

    def serve_artifact_data(self, artifact_id: str) -> None:
        """Serve artifact data."""
        try:
            storage = LocalStorage(base_path=str(self.storage_path))
            artifact = storage.load_artifact(artifact_id)

            # Use ComponentRegistry to render artifact
            component = ComponentRegistry.get_component(artifact)
            html_content = component.render_detail(artifact)

            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_content.encode("utf-8"))
        except Exception as e:
            logger.error(f"Error loading artifact: {e}")
            self.send_error(404, f"Artifact not found: {str(e)}")

    def serve_artifact_download(self, artifact_id: str) -> None:
        """Serve artifact for download with appropriate content type."""
        try:
            storage = LocalStorage(base_path=str(self.storage_path))
            artifact = storage.load_artifact(artifact_id)

            artifact_type = artifact.__class__.__name__
            artifact_format = getattr(artifact, "format", "")
            short_id = artifact_id[:8]

            # Determine content, content type, and filename based on artifact
            if artifact_type == "Text":
                content = getattr(artifact, "content", "").encode("utf-8")
                # Map format to file extension and content type
                format_map = {
                    "markdown": ("md", "text/markdown"),
                    "html": ("html", "text/html"),
                    "json": ("json", "application/json"),
                    "xml": ("xml", "application/xml"),
                    "plain": ("txt", "text/plain"),
                }
                ext, content_type = format_map.get(
                    artifact_format, ("txt", "text/plain")
                )
                filename = f"artifact_{short_id}.{ext}"
            elif artifact_type in ("Image", "File") and hasattr(
                artifact, "get_content"
            ):
                # File-based artifacts - get content from storage
                get_content = getattr(artifact, "get_content")
                content = get_content()
                content_type = getattr(artifact, "content_type", "")
                name = getattr(artifact, "name", "")
                # Determine extension from content type or name
                if name and "." in name:
                    ext = name.rsplit(".", 1)[-1]
                    filename = name
                else:
                    ext_map = {
                        "image/png": "png",
                        "image/jpeg": "jpg",
                        "image/gif": "gif",
                        "image/webp": "webp",
                        "image/svg+xml": "svg",
                        "application/pdf": "pdf",
                    }
                    ext = ext_map.get(content_type, "bin")
                    filename = f"artifact_{short_id}.{ext}"
                if not content_type:
                    content_type = "application/octet-stream"
            else:
                # Generic fallback - serialize as JSON
                content = json.dumps(to_jsonable(artifact), indent=2).encode(
                    "utf-8"
                )
                content_type = "application/json"
                filename = f"artifact_{short_id}.json"

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header(
                "Content-Disposition", f'attachment; filename="{filename}"'
            )
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            logger.error(f"Error downloading artifact: {e}")
            self.send_error(404, f"Artifact download failed: {str(e)}")

    def serve_artifact_viewer(self, artifact_id: str) -> None:
        """Serve artifact in standalone full-page view for new tab viewing."""
        # Check for extensions before rendering
        load_extensions_from_storage(self.storage_path)

        try:
            storage = LocalStorage(base_path=str(self.storage_path))
            artifact = storage.load_artifact(artifact_id)

            artifact_format = getattr(artifact, "format", "")

            # For HTML artifacts, serve the raw content directly
            if artifact_format == "html":
                content = getattr(artifact, "content", "")
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
                return

            # For other formats, use the component renderer with wrapper
            component = ComponentRegistry.get_component(artifact)
            html_content = component.render_detail(artifact)
            component_styles = component.get_styles()

            artifact_type = artifact.__class__.__name__
            short_id = (
                artifact_id[:12] + "..."
                if len(artifact_id) > 12
                else artifact_id
            )

            # Generate standalone page for non-HTML artifacts
            page = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Artifact: {artifact_type}</title>
    <link rel="stylesheet" href="/static/css/monitor.css">
    <style>
        /* Component styles */
        {component_styles}
        /* Page-specific styles */
        html, body {{
            margin: 0;
            padding: 0;
            background: var(--bg-primary);
            min-height: 100vh;
            overflow: auto;
        }}
        .artifact-viewer {{
            max-width: 1400px;
            margin: 0 auto;
            padding: var(--space-6);
        }}
        .artifact-viewer-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: var(--space-5);
            padding-bottom: var(--space-4);
            border-bottom: 1px solid var(--border-light);
        }}
        .artifact-viewer-header h1 {{
            font-size: 1.5rem;
            font-weight: 600;
            color: var(--text-primary);
            margin: 0;
        }}
        .artifact-viewer-header code {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.875rem;
            color: var(--text-tertiary);
            background: var(--bg-tertiary);
            padding: 4px 8px;
            border-radius: var(--radius-sm);
        }}
        .artifact-viewer-content {{
            background: var(--bg-secondary);
            border: 1px solid var(--border-light);
            border-radius: var(--radius-lg);
            padding: var(--space-5);
        }}
        .artifact-viewer-content .artifact-content {{
            line-height: 1.6;
        }}
        /* Override max-height for full-page view */
        .artifact-viewer-content .text-artifact,
        .text-artifact {{
            max-height: none !important;
            overflow: visible !important;
        }}
    </style>
</head>
<body data-theme="dark">
    <div class="artifact-viewer">
        <div class="artifact-viewer-header">
            <h1>{artifact_type}{f' ({artifact_format})' if artifact_format else ''}</h1>
            <code>{short_id}</code>
        </div>
        <div class="artifact-viewer-content">
            <div class="artifact-content">
                {html_content}
            </div>
        </div>
    </div>
    <script>
        // Initialize theme from localStorage or default to dark
        const savedTheme = localStorage.getItem('monitor-theme') || 'dark';
        document.documentElement.setAttribute('data-theme', savedTheme);
        document.body.setAttribute('data-theme', savedTheme);
    </script>
</body>
</html>"""

            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode("utf-8"))
        except Exception as e:
            logger.error(f"Error loading artifact for viewer: {e}")
            self.send_error(404, f"Artifact not found: {str(e)}")

    def serve_interaction_detail(self, interaction_id: str) -> None:
        """Serve full interaction data with artifacts on demand.

        This endpoint loads a single interaction with its artifacts rendered.
        Used for lazy loading when user clicks on an interaction in the timeline.
        """
        # Check for extensions before rendering
        load_extensions_from_storage(self.storage_path)

        try:
            storage = LocalStorage(base_path=str(self.storage_path))

            # Load raw interaction metadata
            raw = storage.load_interaction_metadata(interaction_id)
            # Interaction JSON is wrapped: {"type": "...", "data": {...}}
            int_data = raw.get("data", {})

            # Load and render artifacts
            artifacts = []
            for artifact_uuid in int_data.get("artifacts", []):
                try:
                    artifact = storage.load_artifact(artifact_uuid)
                    component = ComponentRegistry.get_component(artifact)
                    artifacts.append(
                        {
                            "id": artifact_uuid,
                            "type": artifact.__class__.__name__,
                            "preview": component.render_preview(artifact),
                            "html": component.render_detail(artifact),
                            "created_at": getattr(artifact, "created_at", None),
                            "format": getattr(artifact, "format", None),
                        }
                    )
                except Exception as e:
                    logger.debug(f"Error loading artifact {artifact_uuid}: {e}")
                    artifacts.append(
                        {
                            "id": artifact_uuid,
                            "type": "Error",
                            "preview": "Error",
                            "html": f"<p>Error loading artifact: {str(e)}</p>",
                        }
                    )

            # Build response with full interaction data
            response = {
                "interaction": to_jsonable(raw),
                "artifacts": artifacts,
            }

            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))

        except FileNotFoundError:
            self.send_error(404, f"Interaction not found: {interaction_id}")
        except Exception as e:
            logger.error(f"Error loading interaction {interaction_id}: {e}")
            self.send_error(500, f"Error loading interaction: {str(e)}")

    def serve_updates_stream(self) -> None:
        """Serve Server-Sent Events stream for live updates."""
        logger.info("Setting up SSE stream headers")

        # Set socket timeout to prevent blocking writes if client disconnects
        # This ensures we don't hang forever on write() if connection goes stale
        self.connection.settimeout(
            35
        )  # Slightly longer than keep-alive interval

        self.send_response(200)
        self.send_header("Content-type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        logger.info("SSE headers sent, starting stream loop")

        try:
            # Send initial connection message
            logger.info("Sending initial connection message")
            self.wfile.write(b'data: {"type": "connected"}\n\n')
            self.wfile.flush()
            logger.info("Initial message sent, entering update loop")

            # Send updates from the queue with timeout
            while True:
                try:
                    # Wait for update with timeout
                    logger.debug("Waiting for update (30s timeout)...")
                    update = _update_queue.get(timeout=30)
                    logger.info(f"Got update: {update}")
                    # Send update as SSE
                    data = json.dumps(update)
                    self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    logger.debug("Update sent to client")
                except queue.Empty:
                    # Send keep-alive comment every 30 seconds
                    logger.debug("Sending keep-alive")
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
        except (
            BrokenPipeError,
            ConnectionResetError,
            TimeoutError,
            OSError,
        ) as e:
            # Client disconnected or connection timed out
            logger.info(f"SSE client disconnected: {type(e).__name__}")
        except Exception as e:
            logger.error(f"Error in SSE stream: {e}")
            import traceback

            logger.error(traceback.format_exc())

    def generate_monitor_page(self) -> str:
        """Generate the main monitoring page HTML."""
        # Collect CSS and JS from all registered components
        component_styles = ComponentRegistry.get_all_styles()
        component_scripts = ComponentRegistry.get_all_scripts()

        # Render the template with component styles/scripts
        return render_template(
            "monitor.html",
            component_styles=component_styles,
            component_scripts=component_scripts,
        )


def run_monitor_server(
    storage_path: str = "./storage",
    config_path: Optional[str] = None,
    host: str = "localhost",
    port: int = 8080,
    open_browser: bool = True,
) -> None:
    """Run the agent monitoring web server."""
    # Load custom artifact types and UI components from storage metadata
    print(f"Loading extensions from storage: {storage_path}")
    load_extensions_from_storage(Path(storage_path))

    # Set class variables before creating server
    AgentMonitorHTTPRequestHandler._storage_path = storage_path
    AgentMonitorHTTPRequestHandler._config_path = config_path

    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, AgentMonitorHTTPRequestHandler)

    # Set socket timeout to prevent hanging connections (60 seconds)
    httpd.socket.settimeout(60)

    # Start file watcher thread for live updates
    stop_event = threading.Event()
    watcher_thread = threading.Thread(
        target=_watch_storage_directory,
        args=(Path(storage_path), stop_event),
        daemon=True,
    )
    watcher_thread.start()
    logger.info("Storage file watcher started")

    url = f"http://{host}:{port}/"

    print("=" * 60)
    print("Agent Monitor")
    print("=" * 60)
    print(f"Storage path: {storage_path}")
    if config_path:
        print(f"Config path: {config_path}")
    print()
    print(f"Web server running at: {url}")
    if open_browser:
        print("   Opening browser automatically...")
    else:
        print("   Open this URL in your browser to monitor agents")
    print()
    print("Live updates: ENABLED")
    print("   - File watcher monitoring storage directory")
    print("   - Updates streamed to browser via Server-Sent Events")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()

    # Open browser in a separate thread after a short delay
    if open_browser:

        def open_browser_delayed() -> None:
            time.sleep(1)  # Wait for server to be ready
            webbrowser.open(url)

        browser_thread = threading.Thread(target=open_browser_delayed)
        browser_thread.daemon = True
        browser_thread.start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\nShutting down server...")
        stop_event.set()  # Stop the file watcher thread
        print("Goodbye!")


def main() -> int:
    """Entry point for the agent monitor."""
    parser = argparse.ArgumentParser(
        description="Monitor active agents via web interface"
    )
    parser.add_argument(
        "--storage-path",
        type=str,
        default="./storage",
        help="Path to storage directory (default: ./storage)",
    )
    parser.add_argument(
        "--config-path",
        type=str,
        default=None,
        help="Path to configuration directory (optional)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Host to bind to (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port to bind to (default: 8001)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set the logging level (default: INFO)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't automatically open browser (default: opens browser)",
    )

    args = parser.parse_args()

    # Configure logging
    from gimle.hugin.utils.logging import setup_logging

    setup_logging(level=getattr(logging, args.log_level))

    # Ensure storage path exists
    storage_path = Path(args.storage_path)
    if not storage_path.exists():
        print(f"Warning: Storage path '{storage_path}' does not exist")
        storage_path.mkdir(parents=True, exist_ok=True)
        print(f"Created storage directory: {storage_path}")

    run_monitor_server(
        storage_path=str(storage_path),
        config_path=args.config_path,
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
    )

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
