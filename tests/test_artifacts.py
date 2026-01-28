"""Tests for Artifact and Store serialization and deserialization."""

from datetime import datetime

import pytest

from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.interaction.stack import Stack
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.storage.storage import Storage


class MemoryStorage(Storage):
    """A memory-based storage implementation for testing."""

    def __init__(self) -> None:
        """Initialize the memory storage."""
        super().__init__()
        self._artifacts: dict[str, dict] = {}
        self._interactions: dict[str, dict] = {}
        self._files: dict[str, bytes] = {}

    def list_sessions(self) -> list[str]:
        """List all sessions in the storage."""
        return list(self._sessions.keys())

    def list_agents(self) -> list[str]:
        """List all agents in the storage."""
        return list(self._agents.keys())

    def list_interactions(self) -> list[str]:
        """List all interactions in the storage."""
        return list(self._interactions.keys())

    def list_artifacts(self) -> list[str]:
        """List all artifacts in the storage."""
        return list(self._artifacts.keys())

    def _load_artifact(
        self, uuid: str, stack=None, load_interaction: bool = True
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

    def _load_interaction(self, uuid: str, stack: "Stack") -> Interaction:
        """Load an interaction from memory."""
        if uuid not in self._interactions:
            raise ValueError(f"Interaction {uuid} not found in storage")
        return Interaction.from_dict(self._interactions[uuid], stack=stack)

    def _save_interaction(self, interaction: Interaction) -> None:
        """Save an interaction to memory."""
        self._interactions[interaction.uuid] = interaction.to_dict()

    def _load_session(self, uuid: str, storage: "Storage", environment=None):
        raise NotImplementedError

    def _save_session(self, session):
        raise NotImplementedError

    def _load_agent(self, uuid: str, storage: "Storage", session):
        raise NotImplementedError

    def _save_agent(self, agent):
        raise NotImplementedError

    def _delete_artifact(self, artifact) -> None:
        """Delete an artifact from memory."""
        if artifact.uuid in self._artifacts:
            del self._artifacts[artifact.uuid]

    def _delete_session(self, session) -> None:
        """Delete a session from memory."""
        raise NotImplementedError

    def _delete_agent(self, agent) -> None:
        """Delete an agent from memory."""
        raise NotImplementedError

    def _delete_interaction(self, interaction) -> None:
        """Delete an interaction from memory."""
        if interaction.uuid in self._interactions:
            del self._interactions[interaction.uuid]

    def save_file(
        self, artifact_uuid: str, content: bytes, extension: str
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


class TestArtifactSerialization:
    """Test Artifact serialization and deserialization."""

    def test_artifact_to_dict(self, mock_stack):
        """Test serializing an artifact."""
        # Create a simple interaction for the artifact
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        artifact = Artifact(interaction=task_def)

        data = artifact.to_dict()

        assert "type" in data
        assert "data" in data
        assert data["type"] == "Artifact"
        assert (
            data["data"]["interaction"] == task_def.uuid
        )  # Should be UUID, not object
        assert "uuid" in data["data"]

    def test_artifact_from_dict(self, mock_stack):
        """Test deserializing an artifact."""
        storage = MemoryStorage()
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)
        artifact = Artifact(interaction=task_def)

        # Serialize
        data = artifact.to_dict()

        # Deserialize
        new_artifact = Artifact.from_dict(
            data, storage=storage, stack=mock_stack
        )

        assert new_artifact.uuid == artifact.uuid
        assert new_artifact.interaction == task_def

    def test_artifact_from_dict_requires_interaction(self, mock_stack):
        """Test that artifact deserialization requires an interaction."""
        storage = MemoryStorage()
        data = {
            "type": "Artifact",
            "data": {"interaction": "some-uuid", "uuid": "artifact-uuid"},
        }

        with pytest.raises(
            ValueError, match="Interaction some-uuid not found in storage"
        ):
            Artifact.from_dict(data, storage=storage, stack=mock_stack)

    def test_artifact_round_trip(self, mock_stack):
        """Test round-trip serialization/deserialization."""
        storage = MemoryStorage()
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)
        artifact = Artifact(interaction=task_def)

        # Serialize
        data = artifact.to_dict()

        # Deserialize
        new_artifact = Artifact.from_dict(
            data, storage=storage, stack=mock_stack
        )

        assert new_artifact.uuid == artifact.uuid
        assert new_artifact.interaction.id == task_def.id

    def test_artifact_preserves_uuid(self, mock_stack):
        """Test that artifact UUID is preserved during serialization."""
        storage = MemoryStorage()
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)

        artifact = Artifact(interaction=task_def)
        original_uuid = artifact.uuid

        data = artifact.to_dict()
        new_artifact = Artifact.from_dict(
            data, storage=storage, stack=mock_stack
        )

        assert new_artifact.uuid == original_uuid

    def test_store_preserves_all_artifact_uuids(self, mock_stack):
        """Test that all artifact UUIDs are preserved during store serialization."""
        storage = MemoryStorage()

        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)

        artifact1 = Artifact(interaction=task_def)
        storage.save_artifact(artifact1)
        artifact1_uuid = artifact1.id

        artifact2 = Artifact(interaction=task_def)
        storage.save_artifact(artifact2)
        artifact2_uuid = artifact2.id

        # Load artifacts back
        loaded_artifact1 = storage.load_artifact(artifact1_uuid)
        loaded_artifact2 = storage.load_artifact(artifact2_uuid)

        assert loaded_artifact1.uuid == artifact1_uuid
        assert loaded_artifact2.uuid == artifact2_uuid


class TestArtifactTimestamps:
    """Test timestamp functionality in Artifact classes."""

    def test_artifact_has_created_at(self, mock_stack):
        """Test that artifacts automatically get a created_at timestamp."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        artifact = Artifact(interaction=task_def)

        assert hasattr(artifact, "created_at")
        assert artifact.created_at is not None
        # Verify it's a valid ISO format timestamp
        parsed = datetime.fromisoformat(
            artifact.created_at.replace("Z", "+00:00")
        )
        assert parsed.tzinfo is not None

    def test_artifact_created_at_can_be_provided(self, mock_stack):
        """Test that created_at can be provided explicitly."""
        custom_timestamp = "2024-01-01T12:00:00+00:00"
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        artifact = Artifact(interaction=task_def, created_at=custom_timestamp)

        assert artifact.created_at == custom_timestamp

    def test_artifact_to_dict_includes_created_at(self, mock_stack):
        """Test that to_dict includes created_at."""
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        artifact = Artifact(interaction=task_def)

        data = artifact.to_dict()
        assert "created_at" in data["data"]
        assert data["data"]["created_at"] == artifact.created_at

    def test_artifact_from_dict_restores_created_at(self, mock_stack):
        """Test that from_dict restores created_at."""
        storage = MemoryStorage()
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)
        original = Artifact(interaction=task_def)
        original_created_at = original.created_at

        # Serialize and deserialize
        data = original.to_dict()
        restored = Artifact.from_dict(data, storage=storage, stack=mock_stack)

        assert restored.created_at == original_created_at

    def test_artifact_round_trip_preserves_created_at(self, mock_stack):
        """Test that created_at is preserved through save/load cycle."""
        storage = MemoryStorage()
        task = Task(
            name="test_task",
            description="Test",
            parameters={},
            prompt="Do something",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)

        artifact = Artifact(interaction=task_def)
        original_created_at = artifact.created_at

        # Save and load
        storage.save_artifact(artifact)
        loaded = storage.load_artifact(artifact.uuid)

        assert loaded.created_at == original_created_at
