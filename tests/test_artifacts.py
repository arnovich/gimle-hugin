"""Tests for Artifact and Store serialization and deserialization."""

from datetime import datetime

import pytest

from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.interaction.task_definition import TaskDefinition

from .memory_storage import MemoryStorage


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
