"""Local storage implementation module."""

import datetime
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.session import Session
from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.artifacts.feedback import ArtifactFeedback
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.storage.storage import Storage

if TYPE_CHECKING:
    from gimle.hugin.agent.environment import Environment
    from gimle.hugin.interaction.stack import Stack


class SafeJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles non-serializable types gracefully."""

    def default(self, o: Any) -> Any:
        """Convert non-serializable objects to strings."""
        if isinstance(o, (datetime.datetime, datetime.date)):
            return o.isoformat()
        # Handle pandas Timestamp and other datetime-like objects
        if hasattr(o, "isoformat"):
            return o.isoformat()
        if hasattr(o, "item"):
            # numpy scalar types
            return o.item()
        return str(o)


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively convert non-serializable dict keys and values."""
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(item) for item in obj]
    return obj


logger = logging.getLogger(__name__)


class LocalStorage(Storage):
    """A local storage implementation that stores data in the local filesystem."""

    def __init__(
        self,
        base_path: Optional[str] = None,
        callback: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        """Initialize the local storage."""
        super().__init__(callback=callback)
        self.base_path = Path(base_path) if base_path else None
        if self.base_path:
            self.base_path.mkdir(parents=True, exist_ok=True)
            (self.base_path / "artifacts").mkdir(parents=True, exist_ok=True)
            (self.base_path / "sessions").mkdir(parents=True, exist_ok=True)
            (self.base_path / "agents").mkdir(parents=True, exist_ok=True)
            (self.base_path / "interactions").mkdir(parents=True, exist_ok=True)
            (self.base_path / "files").mkdir(parents=True, exist_ok=True)
            (self.base_path / "feedback").mkdir(parents=True, exist_ok=True)

    def _list_uuids(self, dir: Path) -> List[str]:
        """List all uuids in a directory."""
        return [f.name for f in dir.iterdir() if f.is_file()]

    def list_artifacts(self) -> List[str]:
        """List all artifacts in the local filesystem."""
        if not self.base_path:
            raise ValueError("Artifacts not found in local memory storage")
        return self._list_uuids(self.base_path / "artifacts")

    def list_sessions(self) -> List[str]:
        """List all sessions in the local filesystem."""
        if not self.base_path:
            raise ValueError("Sessions not found in local memory storage")
        return self._list_uuids(self.base_path / "sessions")

    def list_agents(self) -> List[str]:
        """List all agents in the local filesystem."""
        if not self.base_path:
            raise ValueError("Agents not found in local memory storage")
        return self._list_uuids(self.base_path / "agents")

    def list_interactions(self) -> List[str]:
        """List all interactions in the local filesystem."""
        if not self.base_path:
            raise ValueError("Interactions not found in local memory storage")
        return self._list_uuids(self.base_path / "interactions")

    def _load_artifact(
        self,
        uuid: str,
        stack: Optional["Stack"] = None,
        load_interaction: bool = True,
    ) -> Artifact:
        """Load an artifact from the local filesystem."""
        if not self.base_path:
            raise ValueError("Artifacts not found in local memory storage")
        with open(self.base_path / "artifacts" / uuid, "r") as f:
            data = json.load(f)
            return Artifact.from_dict(
                data,
                storage=self,
                stack=stack,
                load_interaction=load_interaction,
            )

    def _save_artifact(self, artifact: Artifact) -> None:
        """Save an artifact to the local filesystem."""
        if self.base_path:
            with open(self.base_path / "artifacts" / artifact.uuid, "w") as f:
                json.dump(artifact.to_dict(), f)

    def _delete_artifact(self, artifact: Artifact) -> None:
        """Delete an artifact from the local filesystem."""
        if self.base_path:
            (self.base_path / "artifacts" / artifact.uuid).unlink(
                missing_ok=True
            )

    def _load_session(self, uuid: str, environment: "Environment") -> Session:
        """Load a session from the local filesystem."""
        if not self.base_path:
            raise ValueError("Sessions not found in local memory storage")
        with open(self.base_path / "sessions" / uuid, "r") as f:
            return Session.from_dict(json.load(f), environment=environment)

    def _save_session(self, session: Session) -> None:
        """Save a session to the local filesystem."""
        if self.base_path:
            with open(self.base_path / "sessions" / session.uuid, "w") as f:
                json.dump(session.to_dict(), f)

            # Write metadata file for monitor to discover extensions
            # Supports multiple package paths from different agents
            if session.environment and session.environment.package_path:
                metadata_path = self.base_path / ".hugin_metadata.json"
                new_path = session.environment.package_path

                # Read existing paths and append new path if not present
                existing_paths: list = []
                if metadata_path.exists():
                    try:
                        with open(metadata_path, "r") as f:
                            existing_paths = json.load(f).get(
                                "package_paths", []
                            )
                    except (json.JSONDecodeError, KeyError):
                        existing_paths = []

                if new_path not in existing_paths:
                    existing_paths.append(new_path)

                with open(metadata_path, "w") as f:
                    json.dump({"package_paths": existing_paths}, f)

    def _delete_session(self, session: Session) -> None:
        """Delete a session from the local filesystem."""
        if self.base_path:
            (self.base_path / "sessions" / session.uuid).unlink(missing_ok=True)

    def _load_agent(self, uuid: str, session: "Session") -> Agent:
        """Load an agent from the local filesystem."""
        if not self.base_path:
            raise ValueError("Agents not found in local memory storage")
        with open(self.base_path / "agents" / uuid, "r") as f:
            return Agent.from_dict(json.load(f), storage=self, session=session)

    def _save_agent(self, agent: Agent) -> None:
        """Save an agent to the local filesystem."""
        if self.base_path:
            with open(self.base_path / "agents" / agent.uuid, "w") as f:
                json.dump(agent.to_dict(), f)

    def _delete_agent(self, agent: Agent) -> None:
        """Delete an agent from the local filesystem."""
        if self.base_path:
            (self.base_path / "agents" / agent.uuid).unlink(missing_ok=True)

    def _load_interaction(self, uuid: str, stack: "Stack") -> Interaction:
        """Load an interaction from the local filesystem."""
        if not self.base_path:
            raise ValueError(
                f"Interaction {uuid} not found in local memory storage"
            )
        interaction_path = self.base_path / "interactions" / uuid
        if not interaction_path.exists():
            raise FileNotFoundError(f"Interaction file {uuid} not found")

        try:
            with open(interaction_path, "r") as f:
                content = f.read().strip()
                if not content:
                    raise ValueError(f"Interaction file {uuid} is empty")
                data = json.loads(content)
                return Interaction.from_dict(data, stack=stack)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Interaction file {uuid} contains invalid JSON: {e}"
            ) from e
        except Exception as e:
            raise ValueError(f"Error loading interaction {uuid}: {e}") from e

    def load_interaction_metadata(self, uuid: str) -> Dict[str, Any]:
        """Load raw interaction JSON without deserializing artifacts.

        This is a lightweight alternative to _load_interaction() that returns
        the raw dictionary data without creating Interaction objects or loading
        artifacts. Used by the monitor for fast timeline rendering.

        Args:
            uuid: The interaction UUID to load

        Returns:
            Raw dictionary data from the interaction JSON file
        """
        if not self.base_path:
            raise ValueError("Interactions not found in local memory storage")
        interaction_path = self.base_path / "interactions" / uuid
        if not interaction_path.exists():
            raise FileNotFoundError(f"Interaction file {uuid} not found")

        with open(interaction_path, "r") as f:
            data: Dict[str, Any] = json.load(f)
            return data

    def load_artifact_metadata(self, uuid: str) -> Dict[str, Any]:
        """Load artifact metadata without full content rendering.

        Returns lightweight metadata for monitor display:
        - type: Artifact class name (Text, Image, File, etc.)
        - format: Format field if present (markdown, plain, etc.)
        - preview: Truncated content preview or name for file-based artifacts
        - created_at: Timestamp
        - id: Artifact UUID

        Args:
            uuid: The artifact UUID to load

        Returns:
            Dictionary with artifact metadata
        """
        if not self.base_path:
            raise ValueError("Artifacts not found in local memory storage")
        artifact_path = self.base_path / "artifacts" / uuid
        if not artifact_path.exists():
            raise FileNotFoundError(f"Artifact file {uuid} not found")

        with open(artifact_path, "r") as f:
            raw: Dict[str, Any] = json.load(f)

        # Artifact JSON is wrapped: {"type": "...", "data": {...}}
        artifact_type = raw.get("type", "Unknown")
        artifact_data = raw.get("data", {})

        # Generate preview based on artifact type
        preview = ""

        # For File and Image artifacts, use name instead of loading content
        if artifact_type in ("File", "Image"):
            name = artifact_data.get("name", "")
            description = artifact_data.get("description", "")
            if name:
                preview = name
            elif description:
                preview = (
                    description[:200] + "..."
                    if len(description) > 200
                    else description
                )
            else:
                preview = f"[{artifact_type}]"
        else:
            # For other artifacts, use content
            content = artifact_data.get("content")
            if content:
                if isinstance(content, str):
                    preview = (
                        content[:200] + "..." if len(content) > 200 else content
                    )
                elif isinstance(content, dict):
                    # For structured content, show a summary
                    preview = f"[{len(content)} fields]"

        return {
            "id": uuid,
            "type": artifact_type,
            "format": artifact_data.get("format"),
            "preview": preview,
            "created_at": artifact_data.get("created_at"),
        }

    def _save_interaction(self, interaction: Interaction) -> None:
        """Save an interaction to the local filesystem."""
        if self.base_path:
            logger.debug(
                f"Saving interaction {interaction.uuid} of type {interaction.__class__.__name__}"
            )
            with open(
                self.base_path / "interactions" / interaction.uuid, "w"
            ) as f:
                data = _sanitize_for_json(interaction.to_dict())
                json.dump(data, f, cls=SafeJSONEncoder)

    def _delete_interaction(self, interaction: Interaction) -> None:
        """Delete an interaction from the local filesystem."""
        if self.base_path:
            (self.base_path / "interactions" / interaction.uuid).unlink(
                missing_ok=True
            )

    def _save_feedback(self, feedback: ArtifactFeedback) -> None:
        """Save feedback to the local filesystem."""
        if self.base_path:
            with open(self.base_path / "feedback" / feedback.id, "w") as f:
                json.dump(feedback.to_dict(), f)

    def _load_feedback(self, uuid: str) -> ArtifactFeedback:
        """Load feedback from the local filesystem."""
        if not self.base_path:
            raise ValueError("Feedback not found in local memory storage")
        path = self.base_path / "feedback" / uuid
        if not path.exists():
            raise ValueError(f"Feedback {uuid} not found in storage")
        with open(path, "r") as f:
            return ArtifactFeedback.from_dict(json.load(f))

    def _delete_feedback(self, feedback: ArtifactFeedback) -> None:
        """Delete feedback from the local filesystem."""
        if self.base_path:
            (self.base_path / "feedback" / feedback.id).unlink(missing_ok=True)

    def _list_feedback(self, artifact_id: Optional[str] = None) -> List[str]:
        """List feedback UUIDs, optionally filtered by artifact."""
        if not self.base_path:
            return []
        feedback_dir = self.base_path / "feedback"
        if not feedback_dir.exists():
            return []
        all_uuids = [f.name for f in feedback_dir.iterdir() if f.is_file()]
        if artifact_id is None:
            return all_uuids
        # Filter by artifact_id
        result = []
        for uuid in all_uuids:
            try:
                with open(feedback_dir / uuid, "r") as f:
                    data = json.load(f)
                if data.get("artifact_id") == artifact_id:
                    result.append(uuid)
            except (json.JSONDecodeError, OSError):
                continue
        return result

    def save_file(
        self, artifact_uuid: str, content: bytes, extension: str
    ) -> str:
        """Save file content to the local filesystem.

        Args:
            artifact_uuid: UUID of the artifact this file belongs to
            content: Raw bytes to store
            extension: File extension (without dot)

        Returns:
            Relative path to the stored file (e.g., "files/uuid.ext")
        """
        if not self.base_path:
            raise ValueError("Cannot save file without base_path")

        # Build filename with extension if provided
        filename = artifact_uuid
        if extension:
            filename = f"{artifact_uuid}.{extension}"

        file_path = self.base_path / "files" / filename
        with open(file_path, "wb") as f:
            f.write(content)

        return f"files/{filename}"

    def load_file(self, file_path: str) -> bytes:
        """Load file content from the local filesystem.

        Args:
            file_path: Relative path to the file (as returned by save_file)

        Returns:
            Raw bytes of the file content
        """
        if not self.base_path:
            raise ValueError("Cannot load file without base_path")

        full_path = self.base_path / file_path
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(full_path, "rb") as f:
            return f.read()
