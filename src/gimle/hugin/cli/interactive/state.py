"""Application state management for the interactive TUI."""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from gimle.hugin.storage.local import LocalStorage


@dataclass
class SessionInfo:
    """Summary information about a session."""

    id: str
    created_at: Optional[datetime]
    last_modified: float
    num_agents: int
    is_running: bool = False
    num_running: int = 0
    num_finished: int = 0
    num_awaiting_input: int = 0
    num_idle: int = 0


@dataclass
class AgentInfo:
    """Summary information about an agent."""

    id: str
    session_id: str
    config_name: str
    num_interactions: int
    created_at: Optional[datetime]
    last_modified: float
    is_running: bool = False
    is_finished: bool = False
    awaiting_input: bool = False
    awaiting_input_question: Optional[str] = None


@dataclass
class InteractionInfo:
    """Summary information about an interaction."""

    id: str
    type: str
    label: str
    created_at: Optional[datetime]
    branch: Optional[str]
    is_error: bool = False
    has_artifacts: bool = False
    artifact_ids: List[str] = field(default_factory=list)


@dataclass
class ArtifactInfo:
    """Summary information about an artifact."""

    id: str
    type: str
    format: Optional[str]
    preview: str
    created_at: Optional[str]
    interaction_id: Optional[str] = None


def load_artifact_rating(
    storage_path: Path,
    artifact_id: str,
    storage: Optional[LocalStorage] = None,
) -> Optional[Tuple[float, int]]:
    """Load average rating and count for an artifact.

    Args:
        storage_path: Path to storage directory.
        artifact_id: UUID of the artifact.
        storage: Optional pre-existing storage instance.

    Returns:
        (average_rating, count) or None if no ratings exist.
    """
    try:
        if storage is None:
            storage = LocalStorage(base_path=str(storage_path))
        fb_ids = storage.list_feedback(artifact_id=artifact_id)
        if not fb_ids:
            return None
        ratings: List[int] = []
        for fb_id in fb_ids:
            try:
                fb = storage.load_feedback(fb_id)
                ratings.append(fb.rating)
            except Exception:
                continue
        if not ratings:
            return None
        return (sum(ratings) / len(ratings), len(ratings))
    except Exception:
        return None


@dataclass
class LogRecord:
    """A single log entry for display in the TUI."""

    timestamp: datetime
    level: int
    level_name: str
    logger_name: str
    message: str
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    filename: Optional[str] = None
    lineno: Optional[int] = None


@dataclass
class LogState:
    """State for log panel and viewer."""

    panel_visible: bool = False
    panel_height: int = 8
    current_level: int = logging.DEBUG
    scroll_offset: int = 0
    auto_scroll: bool = True


class AgentController:
    """Controller for managing agent execution state.

    Thread-safe controller that allows pausing, resuming, and
    step-through debugging of running agents.
    """

    def __init__(self, agent_id: str):
        """Initialize the controller."""
        import threading

        self.agent_id = agent_id
        self._lock = threading.Lock()
        self._paused = False
        self._step_through = False
        self._step_requested = False

    @property
    def paused(self) -> bool:
        """Return whether the agent is paused."""
        with self._lock:
            return self._paused

    @property
    def step_through(self) -> bool:
        """Return whether step-through mode is enabled."""
        with self._lock:
            return self._step_through

    def should_step(self) -> bool:
        """Check if the agent should take a step.

        This method should be called by the agent execution loop
        before each step. It will block if paused (checking periodically)
        or wait for step request in step-through mode.
        """
        import time

        while True:
            with self._lock:
                if not self._paused and not self._step_through:
                    return True
                if not self._paused and self._step_through:
                    if self._step_requested:
                        self._step_requested = False
                        return True
            # Sleep briefly before checking again
            time.sleep(0.1)

    def should_continue(self) -> bool:
        """Non-blocking check if agent should continue.

        Returns False if paused, True otherwise.
        For step-through mode, returns True only if step was requested.
        """
        with self._lock:
            if self._paused:
                return False
            if self._step_through:
                if self._step_requested:
                    self._step_requested = False
                    return True
                return False
            return True

    def pause(self) -> None:
        """Pause the agent."""
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        """Resume the agent."""
        with self._lock:
            self._paused = False

    def request_step(self) -> None:
        """Request a single step (for step-through mode)."""
        with self._lock:
            self._step_requested = True

    def toggle_step_through(self) -> None:
        """Toggle step-through mode."""
        with self._lock:
            self._step_through = not self._step_through
            if not self._step_through:
                self._step_requested = False

    def get_status(self) -> str:
        """Get a human-readable status string."""
        with self._lock:
            if self._paused:
                return "Paused"
            if self._step_through:
                return "Step"
            return "Running"


class AppState:
    """Global application state for the TUI."""

    def __init__(self, storage_path: str, task_path: Optional[str] = None):
        """Initialize the application state."""
        self.storage_path = Path(storage_path)
        self.task_path = Path(task_path) if task_path else None
        self.storage = LocalStorage(base_path=str(self.storage_path))

        # Current selections
        self.selected_session_id: Optional[str] = None
        self.selected_agent_id: Optional[str] = None
        self.selected_interaction_idx: int = 0

        # Cached data
        self.sessions: List[SessionInfo] = []
        self.agents: List[AgentInfo] = []
        self.interactions: List[InteractionInfo] = []
        self.interaction_detail: Optional[Dict[str, Any]] = None

        # Agent controllers for running agents
        self.controllers: Dict[str, AgentController] = {}

        # Log state
        self.log_state = LogState()

        # Update tracking
        self._last_refresh = 0.0
        self._refresh_interval = 1.0
        self._update_callbacks: List[Callable[[], None]] = []

        # Watcher thread
        self._watcher_thread: Optional[threading.Thread] = None
        self._watcher_running = False
        self._file_mtimes: Dict[str, float] = {}

    def start_watcher(self) -> None:
        """Start the storage watcher thread."""
        if self._watcher_thread is not None:
            return

        self._watcher_running = True
        self._watcher_thread = threading.Thread(
            target=self._watch_storage, daemon=True
        )
        self._watcher_thread.start()

    def stop_watcher(self) -> None:
        """Stop the storage watcher thread."""
        self._watcher_running = False
        if self._watcher_thread:
            self._watcher_thread.join(timeout=2.0)
            self._watcher_thread = None

    def add_update_callback(self, callback: Callable[[], None]) -> None:
        """Add a callback to be called when data updates."""
        self._update_callbacks.append(callback)

    def _watch_storage(self) -> None:
        """Watch storage directory for changes."""
        while self._watcher_running:
            try:
                changed = self._check_for_changes()
                if changed:
                    self.refresh_data()
                    for callback in self._update_callbacks:
                        try:
                            callback()
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(self._refresh_interval)

    def _check_for_changes(self) -> bool:
        """Check if any storage files have changed."""
        changed = False

        for subdir in ["sessions", "agents"]:
            dir_path = self.storage_path / subdir
            if not dir_path.exists():
                continue

            for file_path in dir_path.iterdir():
                if file_path.is_file():
                    key = str(file_path)
                    mtime = file_path.stat().st_mtime
                    if key not in self._file_mtimes:
                        self._file_mtimes[key] = mtime
                        changed = True
                    elif self._file_mtimes[key] != mtime:
                        self._file_mtimes[key] = mtime
                        changed = True

        return changed

    def refresh_data(self) -> None:
        """Refresh all cached data from storage."""
        self._load_sessions()
        if self.selected_session_id:
            self._load_agents(self.selected_session_id)
        if self.selected_agent_id:
            self._load_interactions(self.selected_agent_id)

    def _load_sessions(self) -> None:
        """Load session list from storage."""
        self.sessions = []

        sessions_dir = self.storage_path / "sessions"
        if not sessions_dir.exists():
            return

        for session_file in sessions_dir.iterdir():
            if not session_file.is_file():
                continue

            session_id = session_file.stem
            try:
                import json

                with open(session_file) as f:
                    data = json.load(f)

                created_at = None
                if "created_at" in data:
                    try:
                        created_at = datetime.fromisoformat(
                            data["created_at"].replace("Z", "+00:00")
                        )
                    except (ValueError, AttributeError):
                        pass

                agent_ids = data.get("agents", [])
                num_agents = (
                    len(agent_ids) if isinstance(agent_ids, list) else 0
                )

                # Count agent states
                num_running = 0
                num_finished = 0
                num_awaiting_input = 0
                num_idle = 0
                last_modified = session_file.stat().st_mtime

                if isinstance(agent_ids, list):
                    for agent_id in agent_ids:
                        agent_file = self.storage_path / "agents" / agent_id
                        if not agent_file.exists():
                            continue

                        try:
                            with open(agent_file) as af:
                                agent_data = json.load(af)

                            # Get interactions
                            interactions = agent_data.get("stack", {}).get(
                                "interactions", []
                            )

                            # Update last_modified if agent is newer
                            agent_mtime = agent_file.stat().st_mtime
                            if agent_mtime > last_modified:
                                last_modified = agent_mtime

                            # Check agent state
                            is_agent_running = (time.time() - agent_mtime) < 45
                            is_finished = self._check_agent_finished(
                                interactions
                            )
                            awaiting, _ = self._check_awaiting_input(
                                interactions
                            )

                            if awaiting:
                                num_awaiting_input += 1
                            elif is_finished:
                                num_finished += 1
                            elif is_agent_running:
                                num_running += 1
                            else:
                                num_idle += 1
                        except Exception:
                            continue

                is_running = num_running > 0

                self.sessions.append(
                    SessionInfo(
                        id=session_id,
                        created_at=created_at,
                        last_modified=last_modified,
                        num_agents=num_agents,
                        is_running=is_running,
                        num_running=num_running,
                        num_finished=num_finished,
                        num_awaiting_input=num_awaiting_input,
                        num_idle=num_idle,
                    )
                )
            except Exception:
                continue

        # Sort by last modified, newest first
        self.sessions.sort(key=lambda s: s.last_modified, reverse=True)

    def _load_agents(self, session_id: str) -> None:
        """Load agents for a session."""
        self.agents = []

        session_file = self.storage_path / "sessions" / session_id
        if not session_file.exists():
            return

        try:
            import json

            with open(session_file) as f:
                session_data = json.load(f)

            agent_ids = session_data.get("agents", [])
            if not isinstance(agent_ids, list):
                return

            for agent_id in agent_ids:
                agent_file = self.storage_path / "agents" / agent_id
                if not agent_file.exists():
                    continue

                try:
                    with open(agent_file) as f:
                        agent_data = json.load(f)

                    config_name = "unknown"
                    if "config" in agent_data:
                        config = agent_data["config"]
                        if isinstance(config, dict):
                            config_name = config.get("name", "unknown")
                        elif isinstance(config, str):
                            config_name = config

                    interactions = agent_data.get("stack", {}).get(
                        "interactions", []
                    )
                    num_interactions = (
                        len(interactions)
                        if isinstance(interactions, list)
                        else 0
                    )

                    created_at = None
                    if "created_at" in agent_data:
                        try:
                            created_at = datetime.fromisoformat(
                                agent_data["created_at"].replace("Z", "+00:00")
                            )
                        except (ValueError, AttributeError):
                            pass

                    last_modified = agent_file.stat().st_mtime
                    is_running = (time.time() - last_modified) < 45

                    # Check if agent is finished (last interaction is terminal)
                    is_finished = self._check_agent_finished(interactions)

                    # Check if agent is awaiting human input
                    awaiting_input, question = self._check_awaiting_input(
                        interactions
                    )

                    self.agents.append(
                        AgentInfo(
                            id=agent_id,
                            session_id=session_id,
                            config_name=config_name,
                            num_interactions=num_interactions,
                            created_at=created_at,
                            last_modified=last_modified,
                            is_running=is_running,
                            is_finished=is_finished,
                            awaiting_input=awaiting_input,
                            awaiting_input_question=question,
                        )
                    )
                except Exception:
                    continue

        except Exception:
            pass

    def _check_agent_finished(self, interaction_ids: List[Any]) -> bool:
        """Check if an agent is finished based on its last interaction.

        An agent is finished if its last interaction is a Waiting
        interaction with no condition (terminal state).

        Args:
            interaction_ids: List of interaction IDs from the agent's stack

        Returns:
            True if the agent is in a terminal finished state
        """
        import json

        if not interaction_ids or not isinstance(interaction_ids, list):
            return False

        # Get the last interaction ID
        last_id = interaction_ids[-1]
        if not isinstance(last_id, str):
            return False

        # Load the last interaction
        interaction_file = self.storage_path / "interactions" / last_id
        if not interaction_file.exists():
            return False

        try:
            with open(interaction_file) as f:
                interaction = json.load(f)

            # Check if it's a Waiting interaction with no condition
            int_type = interaction.get("type", "")
            if int_type == "Waiting":
                data = interaction.get("data", {})
                # No condition means terminal state
                return data.get("condition") is None

            return False
        except Exception:
            return False

    def _check_awaiting_input(
        self, interaction_ids: List[Any]
    ) -> Tuple[bool, Optional[str]]:
        """Check if an agent is awaiting human input.

        An agent is awaiting input if its last interaction is an AskHuman.

        Args:
            interaction_ids: List of interaction IDs from the agent's stack

        Returns:
            Tuple of (awaiting_input, question)
        """
        import json

        if not interaction_ids or not isinstance(interaction_ids, list):
            return False, None

        # Get the last interaction ID
        last_id = interaction_ids[-1]
        if not isinstance(last_id, str):
            return False, None

        # Load the last interaction
        interaction_file = self.storage_path / "interactions" / last_id
        if not interaction_file.exists():
            return False, None

        try:
            with open(interaction_file) as f:
                interaction = json.load(f)

            # Check if it's an AskHuman interaction
            int_type = interaction.get("type", "")
            if int_type == "AskHuman":
                data = interaction.get("data", {})
                question = data.get("question")
                return True, question

            return False, None
        except Exception:
            return False, None

    def _load_interactions(self, agent_id: str) -> None:
        """Load interactions for an agent."""
        self.interactions = []

        agent_file = self.storage_path / "agents" / agent_id
        if not agent_file.exists():
            return

        try:
            import json

            with open(agent_file) as f:
                agent_data = json.load(f)

            stack_data = agent_data.get("stack", {})
            interaction_ids = stack_data.get("interactions", [])

            if not isinstance(interaction_ids, list):
                return

            # Load each interaction from the interactions directory
            for int_id in interaction_ids:
                if not isinstance(int_id, str):
                    continue

                interaction_file = self.storage_path / "interactions" / int_id
                if not interaction_file.exists():
                    continue

                try:
                    with open(interaction_file) as f:
                        interaction = json.load(f)

                    if not isinstance(interaction, dict):
                        continue

                    int_type = interaction.get("type", "Unknown")

                    # Build label based on type
                    label = self._get_interaction_label(interaction)

                    created_at = None
                    # Check both top-level and nested data for created_at
                    created_at_str = interaction.get(
                        "created_at"
                    ) or interaction.get("data", {}).get("created_at")
                    if created_at_str:
                        try:
                            created_at = datetime.fromisoformat(
                                created_at_str.replace("Z", "+00:00")
                            )
                        except (ValueError, AttributeError):
                            pass

                    # Get data from nested structure
                    data = interaction.get("data", {})
                    branch = data.get("branch")
                    is_error = data.get("is_error", False)
                    artifacts = data.get("artifacts", [])
                    artifact_ids = (
                        artifacts if isinstance(artifacts, list) else []
                    )
                    has_artifacts = bool(artifact_ids)

                    self.interactions.append(
                        InteractionInfo(
                            id=int_id,
                            type=int_type,
                            label=label,
                            created_at=created_at,
                            branch=branch,
                            is_error=is_error,
                            has_artifacts=has_artifacts,
                            artifact_ids=artifact_ids,
                        )
                    )
                except Exception:
                    continue
        except Exception:
            pass

    def _get_interaction_label(self, interaction: Dict[str, Any]) -> str:
        """Extract a meaningful label from an interaction."""
        int_type = str(interaction.get("type", ""))

        # Get nested data if present
        data = interaction.get("data", interaction)

        # Try various fields that might contain useful info
        if "tool" in data or "tool_name" in data:
            tool_val = data.get("tool") or data.get("tool_name", "")
            return str(tool_val) if tool_val else ""
        if "task" in data and isinstance(data["task"], dict):
            task_name = data["task"].get("name", "")
            if task_name:
                return str(task_name)
        if "summary" in data:
            summary = data["summary"]
            if summary:
                s = str(summary)
                return s[:50] + "..." if len(s) > 50 else s
        if "prompt" in data:
            prompt = data["prompt"]
            if isinstance(prompt, str) and prompt:
                return prompt[:50] + "..." if len(prompt) > 50 else prompt
        if "response" in data:
            response = data["response"]
            if isinstance(response, str) and response:
                return response[:50] + "..." if len(response) > 50 else response
        if "result" in data:
            result = data["result"]
            if isinstance(result, str) and result:
                return result[:50] + "..." if len(result) > 50 else result

        return int_type

    def load_interaction_detail(self, idx: int) -> Optional[Dict[str, Any]]:
        """Load full details for an interaction."""
        if idx < 0 or idx >= len(self.interactions):
            return None

        # Get the interaction ID from the cached list
        interaction_info = self.interactions[idx]
        interaction_file = (
            self.storage_path / "interactions" / interaction_info.id
        )

        if not interaction_file.exists():
            return None

        try:
            import json

            with open(interaction_file) as f:
                self.interaction_detail = json.load(f)
                return self.interaction_detail
        except Exception:
            pass

        return None

    def select_session(self, session_id: str) -> None:
        """Select a session and load its agents."""
        self.selected_session_id = session_id
        self.selected_agent_id = None
        self.selected_interaction_idx = 0
        self._load_agents(session_id)

    def select_agent(self, agent_id: str) -> None:
        """Select an agent and load its interactions."""
        self.selected_agent_id = agent_id
        self.selected_interaction_idx = 0
        self._load_interactions(agent_id)

    def get_controller(self, agent_id: str) -> AgentController:
        """Get or create a controller for an agent."""
        if agent_id not in self.controllers:
            self.controllers[agent_id] = AgentController(agent_id)
        return self.controllers[agent_id]

    def get_relative_time(self, timestamp: float) -> str:
        """Get a human-readable relative time string."""
        diff = time.time() - timestamp
        if diff < 60:
            return "just now"
        elif diff < 3600:
            mins = int(diff / 60)
            return f"{mins}m ago"
        elif diff < 86400:
            hours = int(diff / 3600)
            return f"{hours}h ago"
        else:
            days = int(diff / 86400)
            return f"{days}d ago"

    def load_artifact_info(
        self, artifact_id: str, interaction_id: Optional[str] = None
    ) -> Optional[ArtifactInfo]:
        """Load artifact metadata.

        Args:
            artifact_id: The artifact UUID to load
            interaction_id: Optional interaction ID this artifact belongs to

        Returns:
            ArtifactInfo or None if not found
        """
        try:
            metadata = self.storage.load_artifact_metadata(artifact_id)
            return ArtifactInfo(
                id=metadata.get("id", artifact_id),
                type=metadata.get("type", "Unknown"),
                format=metadata.get("format"),
                preview=metadata.get("preview", ""),
                created_at=metadata.get("created_at"),
                interaction_id=interaction_id,
            )
        except Exception:
            return None

    def get_all_artifacts_for_agent(self) -> List[ArtifactInfo]:
        """Get all artifacts for the currently selected agent.

        Returns:
            List of ArtifactInfo for all artifacts across all interactions
        """
        artifacts = []
        for interaction in self.interactions:
            for artifact_id in interaction.artifact_ids:
                info = self.load_artifact_info(artifact_id, interaction.id)
                if info:
                    artifacts.append(info)
        return artifacts

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its agents and interactions.

        Args:
            session_id: The session ID to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        import json

        session_file = self.storage_path / "sessions" / session_id
        if not session_file.exists():
            return False

        try:
            # Load session to get agent list
            with open(session_file) as f:
                session_data = json.load(f)

            agent_ids = session_data.get("agents", [])
            if isinstance(agent_ids, list):
                for agent_id in agent_ids:
                    self._delete_agent_files(agent_id)

            # Delete the session file
            session_file.unlink(missing_ok=True)

            # Clear selection if this session was selected
            if self.selected_session_id == session_id:
                self.selected_session_id = None
                self.selected_agent_id = None
                self.agents = []
                self.interactions = []

            # Refresh the sessions list
            self._load_sessions()
            return True

        except Exception:
            return False

    def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent and all its interactions.

        Args:
            agent_id: The agent ID to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        import json

        if not self.selected_session_id:
            return False

        # Delete the agent files
        if not self._delete_agent_files(agent_id):
            return False

        # Update the session to remove the agent reference
        session_file = self.storage_path / "sessions" / self.selected_session_id
        if session_file.exists():
            try:
                with open(session_file) as f:
                    session_data = json.load(f)

                agent_ids = session_data.get("agents", [])
                if isinstance(agent_ids, list) and agent_id in agent_ids:
                    agent_ids.remove(agent_id)
                    session_data["agents"] = agent_ids

                    with open(session_file, "w") as f:
                        json.dump(session_data, f)
            except Exception:
                pass

        # Clear selection if this agent was selected
        if self.selected_agent_id == agent_id:
            self.selected_agent_id = None
            self.interactions = []

        # Refresh the agents list
        if self.selected_session_id:
            self._load_agents(self.selected_session_id)

        return True

    def rewind_agent_to(self, agent_id: str, interaction_idx: int) -> int:
        """Rewind an agent to a specific interaction index.

        Removes all interactions after the given index and updates storage.

        Args:
            agent_id: The agent ID to rewind
            interaction_idx: The interaction index to rewind to (0-based)

        Returns:
            Number of interactions removed, or -1 if rewind failed
        """
        import json

        if not self.selected_session_id:
            return -1

        agent_file = self.storage_path / "agents" / agent_id
        if not agent_file.exists():
            return -1

        try:
            # Load the agent data
            with open(agent_file) as f:
                agent_data = json.load(f)

            stack_data = agent_data.get("stack", {})
            interaction_ids = stack_data.get("interactions", [])

            if not isinstance(interaction_ids, list):
                return -1

            # Validate the index
            if interaction_idx < 0 or interaction_idx >= len(interaction_ids):
                return -1

            # Get interactions to remove
            ids_to_remove = interaction_ids[interaction_idx + 1 :]
            if not ids_to_remove:
                return 0

            # Delete interaction files and their artifacts
            for int_id in ids_to_remove:
                if isinstance(int_id, str):
                    # Load interaction to get artifact IDs
                    interaction_file = (
                        self.storage_path / "interactions" / int_id
                    )
                    if interaction_file.exists():
                        try:
                            with open(interaction_file) as f:
                                int_data = json.load(f)
                            # Delete artifacts
                            artifacts = int_data.get("data", {}).get(
                                "artifacts", []
                            )
                            for artifact_id in artifacts:
                                artifact_file = (
                                    self.storage_path
                                    / "artifacts"
                                    / artifact_id
                                )
                                artifact_file.unlink(missing_ok=True)
                        except Exception:
                            pass
                        # Delete interaction file
                        interaction_file.unlink(missing_ok=True)

            # Update agent data
            stack_data["interactions"] = interaction_ids[: interaction_idx + 1]
            agent_data["stack"] = stack_data

            # Save updated agent
            with open(agent_file, "w") as f:
                json.dump(agent_data, f)

            # Clear storage cache so agent is reloaded from disk on resume
            # The storage caches sessions and agents by UUID
            agent_cache_key = f"agent:{agent_id}"
            if agent_cache_key in self.storage.store:
                del self.storage.store[agent_cache_key]

            # Also clear session cache since it contains the agent list
            if self.selected_session_id:
                session_cache_key = f"session:{self.selected_session_id}"
                if session_cache_key in self.storage.store:
                    del self.storage.store[session_cache_key]

            # Update the AgentInfo in our agents list
            remaining_interactions = interaction_ids[: interaction_idx + 1]
            is_now_finished = self._check_agent_finished(remaining_interactions)
            for agent_info in self.agents:
                if agent_info.id == agent_id:
                    agent_info.is_finished = is_now_finished
                    agent_info.is_running = (
                        False  # Agent is now idle after rewind
                    )
                    agent_info.num_interactions = len(remaining_interactions)
                    break

            # Refresh the interactions list
            self._load_interactions(agent_id)

            return len(ids_to_remove)

        except Exception:
            return -1

    def _delete_agent_files(self, agent_id: str) -> bool:
        """Delete an agent file and all its interaction files.

        Args:
            agent_id: The agent ID to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        import json

        agent_file = self.storage_path / "agents" / agent_id
        if not agent_file.exists():
            return False

        try:
            # Load agent to get interaction list
            with open(agent_file) as f:
                agent_data = json.load(f)

            # Delete all interactions
            stack_data = agent_data.get("stack", {})
            interaction_ids = stack_data.get("interactions", [])
            if isinstance(interaction_ids, list):
                for int_id in interaction_ids:
                    if isinstance(int_id, str):
                        interaction_file = (
                            self.storage_path / "interactions" / int_id
                        )
                        interaction_file.unlink(missing_ok=True)

            # Delete the agent file
            agent_file.unlink(missing_ok=True)

            # Remove controller if exists
            if agent_id in self.controllers:
                del self.controllers[agent_id]

            return True

        except Exception:
            return False

    def load_agent_for_resume(
        self, session_id: str, agent_id: str
    ) -> Optional[Tuple[Any, Any]]:
        """Load a session and agent for resuming execution.

        Args:
            session_id: The session ID
            agent_id: The agent ID

        Returns:
            Tuple of (session, agent) if successful, None otherwise
        """
        import json

        from gimle.hugin.agent.environment import Environment

        try:
            # Get package paths from metadata
            metadata_path = self.storage_path / ".hugin_metadata.json"
            if not metadata_path.exists():
                return None

            with open(metadata_path) as f:
                metadata = json.load(f)

            package_paths = metadata.get("package_paths", [])
            if not package_paths:
                return None

            # Try each package path until we find one that works
            for package_path in package_paths:
                try:
                    # Load environment from package path
                    env = Environment.load(package_path, storage=self.storage)

                    # Load session
                    session = self.storage.load_session(session_id, env)

                    # Find the agent
                    for agent in session.agents:
                        if agent.id == agent_id:
                            return (session, agent)

                except Exception:
                    continue

            return None

        except Exception:
            return None

    def submit_human_response(self, agent_id: str, response: str) -> bool:
        """Submit a human response to an agent waiting for input.

        Adds a HumanResponse interaction to the agent's stack.

        Args:
            agent_id: The agent ID to respond to
            response: The human response text

        Returns:
            True if the response was submitted successfully
        """
        import json

        from gimle.hugin.utils.uuid import generate_uuid

        agent_file = self.storage_path / "agents" / agent_id
        if not agent_file.exists():
            return False

        try:
            # Load the agent data
            with open(agent_file) as f:
                agent_data = json.load(f)

            # Generate a UUID for the interaction
            interaction_id = generate_uuid()

            # Save the interaction to disk
            interaction_data = {
                "type": "HumanResponse",
                "data": {
                    "id": interaction_id,
                    "response": response,
                },
            }

            interaction_file = (
                self.storage_path / "interactions" / interaction_id
            )
            with open(interaction_file, "w") as f:
                json.dump(interaction_data, f)

            # Add to agent's stack
            stack_data = agent_data.get("stack", {})
            interaction_ids = stack_data.get("interactions", [])
            interaction_ids.append(interaction_id)
            stack_data["interactions"] = interaction_ids
            agent_data["stack"] = stack_data

            # Save the updated agent
            with open(agent_file, "w") as f:
                json.dump(agent_data, f)

            # Clear storage cache so agent is reloaded from disk on resume
            agent_cache_key = f"agent:{agent_id}"
            if agent_cache_key in self.storage.store:
                del self.storage.store[agent_cache_key]

            if self.selected_session_id:
                session_cache_key = f"session:{self.selected_session_id}"
                if session_cache_key in self.storage.store:
                    del self.storage.store[session_cache_key]

            # Update the AgentInfo to no longer be awaiting input
            for agent_info in self.agents:
                if agent_info.id == agent_id:
                    agent_info.awaiting_input = False
                    agent_info.awaiting_input_question = None
                    agent_info.num_interactions += 1
                    break

            # Refresh interactions list
            if self.selected_agent_id == agent_id:
                self._load_interactions(agent_id)

            return True

        except Exception:
            return False
