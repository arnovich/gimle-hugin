"""Shared in-memory storage implementation for tests."""

import logging
from typing import Any, Dict, List, Optional

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.session import Session
from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.artifacts.feedback import ArtifactFeedback
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.storage.storage import Storage

logger = logging.getLogger(__name__)


class MemoryStorage(Storage):
    """In-memory storage for testing.

    Implements the full Storage interface using plain dicts.
    Accepts an optional callback like the real LocalStorage.
    """

    def __init__(self, callback: Any = None) -> None:
        """Initialize the memory storage."""
        super().__init__(callback=callback)
        self._artifacts: Dict[str, dict] = {}
        self._sessions: Dict[str, dict] = {}
        self._agents: Dict[str, dict] = {}
        self._interactions: Dict[str, dict] = {}
        self._files: Dict[str, bytes] = {}
        self._feedback: Dict[str, dict] = {}

    # -- list --

    def list_sessions(self) -> List[str]:
        """List all sessions in memory."""
        return list(self._sessions.keys())

    def list_agents(self) -> List[str]:
        """List all agents in memory."""
        return list(self._agents.keys())

    def list_interactions(self) -> List[str]:
        """List all interactions in memory."""
        return list(self._interactions.keys())

    def list_artifacts(self) -> List[str]:
        """List all artifacts in memory."""
        return list(self._artifacts.keys())

    # -- artifact --

    def _load_artifact(
        self,
        uuid: str,
        stack: Any = None,
        load_interaction: bool = True,
    ) -> Artifact:
        """Load an artifact from memory."""
        if uuid not in self._artifacts:
            raise ValueError(f"Artifact {uuid} not found in storage")
        return Artifact.from_dict(
            self._artifacts[uuid],
            storage=self,
            stack=stack,
            load_interaction=load_interaction,
        )

    def _save_artifact(self, artifact: Artifact) -> None:
        """Save an artifact to memory."""
        self._artifacts[artifact.uuid] = artifact.to_dict()

    def _delete_artifact(self, artifact: Artifact) -> None:
        """Delete an artifact from memory."""
        self._artifacts.pop(artifact.uuid, None)

    # -- session --

    def _load_session(self, uuid: str, environment: Any) -> Session:
        """Load a session from memory."""
        if uuid not in self._sessions:
            raise ValueError(f"Session {uuid} not found in storage")
        return Session.from_dict(self._sessions[uuid], environment=environment)

    def _save_session(self, session: Session) -> None:
        """Save a session to memory."""
        self._sessions[session.uuid] = session.to_dict()

    def _delete_session(self, session: Session) -> None:
        """Delete a session from memory."""
        self._sessions.pop(session.uuid, None)

    # -- agent --

    def _load_agent(self, uuid: str, session: Session) -> Agent:
        """Load an agent from memory."""
        if uuid not in self._agents:
            raise ValueError(f"Agent {uuid} not found in storage")
        return Agent.from_dict(
            self._agents[uuid],
            storage=self,
            session=session,
        )

    def _save_agent(self, agent: Agent) -> None:
        """Save an agent to memory."""
        self._agents[agent.uuid] = agent.to_dict()

    def _delete_agent(self, agent: Agent) -> None:
        """Delete an agent from memory."""
        self._agents.pop(agent.uuid, None)

    # -- interaction --

    def _load_interaction(self, uuid: str, stack: Any) -> Interaction:
        """Load an interaction from memory."""
        if uuid not in self._interactions:
            raise ValueError(f"Interaction {uuid} not found in storage")
        return Interaction.from_dict(self._interactions[uuid], stack=stack)

    def _save_interaction(self, interaction: Interaction) -> None:
        """Save an interaction to memory."""
        self._interactions[interaction.uuid] = interaction.to_dict()

    def _delete_interaction(self, interaction: Interaction) -> None:
        """Delete an interaction from memory."""
        self._interactions.pop(interaction.uuid, None)

    # -- file --

    def save_file(
        self,
        artifact_uuid: str,
        content: bytes,
        extension: str,
    ) -> str:
        """Save file content to memory."""
        filename = artifact_uuid
        if extension:
            filename = f"{artifact_uuid}.{extension}"
        file_path = f"files/{filename}"
        self._files[file_path] = content
        return file_path

    def load_file(self, file_path: str) -> bytes:
        """Load file content from memory."""
        if file_path not in self._files:
            raise FileNotFoundError(f"File not found: {file_path}")
        return self._files[file_path]

    # -- feedback --

    def _save_feedback(self, feedback: ArtifactFeedback) -> None:
        """Save feedback to memory."""
        self._feedback[feedback.id] = feedback.to_dict()

    def _load_feedback(self, uuid: str) -> ArtifactFeedback:
        """Load feedback from memory."""
        if uuid not in self._feedback:
            raise ValueError(f"Feedback {uuid} not found in storage")
        return ArtifactFeedback.from_dict(self._feedback[uuid])

    def _delete_feedback(self, feedback: ArtifactFeedback) -> None:
        """Delete feedback from memory."""
        self._feedback.pop(feedback.id, None)

    def _list_feedback(self, artifact_id: Optional[str] = None) -> List[str]:
        """List feedback UUIDs, optionally by artifact."""
        if artifact_id is None:
            return list(self._feedback.keys())
        return [
            k
            for k, v in self._feedback.items()
            if v.get("artifact_id") == artifact_id
        ]
