"""Storage interface module."""

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, cast

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.session import Session
from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.artifacts.feedback import ArtifactFeedback
from gimle.hugin.interaction.interaction import Interaction

if TYPE_CHECKING:
    from gimle.hugin.agent.environment import Environment
    from gimle.hugin.interaction.stack import Stack


logger = logging.getLogger(__name__)


class Storage(ABC):
    """Abstract storage interface."""

    def __init__(
        self, callback: Optional[Callable[[str, str], None]] = None
    ) -> None:
        """Initialize the storage."""
        self.store: Dict[str, Any] = {}
        self.callback = callback

    @abstractmethod
    def list_sessions(self) -> List[str]:
        """List all sessions in the storage."""
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    def list_agents(self) -> List[str]:
        """List all agents in the storage."""
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    def list_interactions(self) -> List[str]:
        """List all interactions in the storage."""
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    def list_artifacts(self) -> List[str]:
        """List all artifacts in the storage."""
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    def _load_artifact(
        self,
        uuid: str,
        stack: Optional["Stack"] = None,
        load_interaction: bool = True,
    ) -> Artifact:
        raise NotImplementedError("Subclasses must implement this method")

    def load_artifact(
        self,
        uuid: str,
        stack: Optional["Stack"] = None,
        load_interaction: bool = True,
    ) -> Artifact:
        """Load an artifact by UUID."""
        cache_key = f"artifact:{uuid}"
        if cache_key not in self.store:
            self.store[cache_key] = self._load_artifact(
                uuid, stack, load_interaction
            )
        return cast(Artifact, self.store[cache_key])

    @abstractmethod
    def _save_artifact(self, artifact: Artifact) -> None:
        raise NotImplementedError("Subclasses must implement this method")

    def save_artifact(self, artifact: Artifact) -> None:
        """Save an artifact."""
        if not getattr(artifact, "uuid", None):
            raise ValueError("Artifact must have a uuid")
        self._save_artifact(artifact)
        self.store[f"artifact:{artifact.id}"] = artifact
        if self.callback:
            self.callback("artifact", artifact.id)

    @abstractmethod
    def _delete_artifact(self, artifact: Artifact) -> None:
        raise NotImplementedError("Subclasses must implement this method")

    def delete_artifact(self, artifact: Artifact) -> None:
        """Delete an artifact and its associated feedback."""
        # Cascade delete feedback — clear cache, then bulk-delete
        for feedback_uuid in self.list_feedback(artifact.id):
            self.store.pop(f"feedback:{feedback_uuid}", None)
        self._delete_feedback_for_artifact(artifact.id)
        self._delete_artifact(artifact)
        self.store.pop(f"artifact:{artifact.id}", None)

    @abstractmethod
    def _load_session(self, uuid: str, environment: "Environment") -> Session:
        raise NotImplementedError("Subclasses must implement this method")

    def load_session(self, uuid: str, environment: "Environment") -> Session:
        """Load a session by UUID."""
        cache_key = f"session:{uuid}"
        environment.storage = self
        if cache_key not in self.store:
            self.store[cache_key] = self._load_session(uuid, environment)
        return cast(Session, self.store[cache_key])

    @abstractmethod
    def _save_session(self, session: Session) -> None:
        raise NotImplementedError("Subclasses must implement this method")

    def save_session(self, session: Session) -> None:
        """Save a session."""
        logger.info(f"Saving session {session.id}")
        if not getattr(session, "uuid", None):
            raise ValueError("Session must have a uuid")
        self._save_session(session)
        for agent in session.agents:
            self.save_agent(agent)
        self.store[f"session:{session.id}"] = session
        if self.callback:
            self.callback("session", session.id)

    @abstractmethod
    def _delete_session(self, session: Session) -> None:
        raise NotImplementedError("Subclasses must implement this method")

    def delete_session(self, session: Session) -> None:
        """Delete a session."""
        for agent in session.agents:
            self.delete_agent(agent)
        self._delete_session(session)
        self.store.pop(f"session:{session.id}", None)

    @abstractmethod
    def _load_agent(self, uuid: str, session: "Session") -> Agent:
        raise NotImplementedError("Subclasses must implement this method")

    def load_agent(self, uuid: str, session: "Session") -> Agent:
        """Load an agent by UUID."""
        cache_key = f"agent:{uuid}"
        if cache_key not in self.store:
            self.store[cache_key] = self._load_agent(uuid, session)
        return cast(Agent, self.store[cache_key])

    @abstractmethod
    def _save_agent(self, agent: Agent) -> None:
        raise NotImplementedError("Subclasses must implement this method")

    def save_agent(self, agent: Agent) -> None:
        """Save an agent."""
        if not getattr(agent, "uuid", None):
            raise ValueError("Agent must have a uuid")
        self._save_agent(agent)
        self.store[f"agent:{agent.id}"] = agent
        for interaction in agent.stack.interactions:
            self.save_interaction(interaction)
        if self.callback:
            self.callback("agent", agent.id)

    @abstractmethod
    def _delete_agent(self, agent: Agent) -> None:
        raise NotImplementedError("Subclasses must implement this method")

    def delete_agent(self, agent: Agent) -> None:
        """Delete an agent."""
        for interaction in agent.stack.interactions:
            self.delete_interaction(interaction)
        self._delete_agent(agent)
        self.store.pop(f"agent:{agent.id}", None)

    @abstractmethod
    def _load_interaction(self, uuid: str, stack: "Stack") -> Interaction:
        raise NotImplementedError("Subclasses must implement this method")

    def load_interaction(self, uuid: str, stack: "Stack") -> Interaction:
        """Load an interaction by UUID."""
        cache_key = f"interaction:{uuid}"
        if cache_key not in self.store:
            self.store[cache_key] = self._load_interaction(uuid, stack)
        return cast(Interaction, self.store[cache_key])

    @abstractmethod
    def _save_interaction(self, interaction: Interaction) -> None:
        raise NotImplementedError("Subclasses must implement this method")

    def save_interaction(self, interaction: Interaction) -> None:
        """Save an interaction."""
        if not getattr(interaction, "uuid", None):
            raise ValueError("Interaction must have a uuid")
        self._save_interaction(interaction)
        self.store[f"interaction:{interaction.id}"] = interaction
        for artifact in interaction.artifacts:
            self.save_artifact(artifact)
        if self.callback:
            self.callback("interaction", interaction.id)

    @abstractmethod
    def _delete_interaction(self, interaction: Interaction) -> None:
        raise NotImplementedError("Subclasses must implement this method")

    def delete_interaction(self, interaction: Interaction) -> None:
        """Delete an interaction."""
        for artifact in interaction.artifacts:
            self.delete_artifact(artifact)
        self._delete_interaction(interaction)
        self.store.pop(f"interaction:{interaction.id}", None)

    # -- feedback --

    @abstractmethod
    def _save_feedback(self, feedback: ArtifactFeedback) -> None:
        raise NotImplementedError("Subclasses must implement this method")

    def save_feedback(self, feedback: ArtifactFeedback) -> None:
        """Save feedback."""
        self._save_feedback(feedback)
        self.store[f"feedback:{feedback.id}"] = feedback
        if self.callback:
            self.callback("feedback", feedback.id)

    @abstractmethod
    def _load_feedback(self, uuid: str) -> ArtifactFeedback:
        raise NotImplementedError("Subclasses must implement this method")

    def load_feedback(self, uuid: str) -> ArtifactFeedback:
        """Load feedback by UUID."""
        cache_key = f"feedback:{uuid}"
        if cache_key not in self.store:
            self.store[cache_key] = self._load_feedback(uuid)
        return cast(ArtifactFeedback, self.store[cache_key])

    @abstractmethod
    def _delete_feedback(self, feedback: ArtifactFeedback) -> None:
        raise NotImplementedError("Subclasses must implement this method")

    def delete_feedback(self, feedback: ArtifactFeedback) -> None:
        """Delete feedback."""
        self._delete_feedback(feedback)
        self.store.pop(f"feedback:{feedback.id}", None)

    @abstractmethod
    def _delete_feedback_for_artifact(self, artifact_id: str) -> None:
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    def _list_feedback(self, artifact_id: Optional[str] = None) -> List[str]:
        raise NotImplementedError("Subclasses must implement this method")

    def list_feedback(self, artifact_id: Optional[str] = None) -> List[str]:
        """List feedback UUIDs, optionally filtered by artifact."""
        return self._list_feedback(artifact_id)

    # -- file --

    @abstractmethod
    def save_file(
        self, artifact_uuid: str, content: bytes, extension: str
    ) -> str:
        """Save file content to storage.

        Args:
            artifact_uuid: UUID of the artifact this file belongs to
            content: Raw bytes to store
            extension: File extension (without dot)

        Returns:
            Relative path to the stored file (e.g., "files/uuid.ext")
        """
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    def load_file(self, file_path: str) -> bytes:
        """Load file content from storage.

        Args:
            file_path: Relative path to the file (as returned by save_file)

        Returns:
            Raw bytes of the file content
        """
        raise NotImplementedError("Subclasses must implement this method")
