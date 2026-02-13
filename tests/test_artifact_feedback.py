"""Comprehensive tests for ArtifactFeedback feature."""

import pytest

from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.artifacts.feedback import ArtifactFeedback
from gimle.hugin.artifacts.query_engine import (
    RATING_BOOST_MULTIPLIER,
    RATING_NEUTRAL,
    ArtifactQueryEngine,
)
from gimle.hugin.artifacts.text import Text
from gimle.hugin.interaction.task_definition import TaskDefinition

from .memory_storage import MemoryStorage


class TestArtifactFeedbackModel:
    """Test ArtifactFeedback creation and validation."""

    def test_create_feedback(self):
        """Test basic feedback creation."""
        fb = ArtifactFeedback(artifact_id="art-1", rating=4)
        assert fb.artifact_id == "art-1"
        assert fb.rating == 4
        assert fb.comment is None
        assert fb.agent_id is None
        assert fb.id is not None

    def test_create_feedback_with_all_fields(self):
        """Test feedback with all optional fields."""
        fb = ArtifactFeedback(
            artifact_id="art-1",
            rating=5,
            comment="Very useful",
            agent_id="agent-1",
        )
        assert fb.comment == "Very useful"
        assert fb.agent_id == "agent-1"

    def test_rating_boundaries(self):
        """Test valid rating boundaries."""
        fb_low = ArtifactFeedback(artifact_id="a", rating=1)
        fb_high = ArtifactFeedback(artifact_id="a", rating=5)
        assert fb_low.rating == 1
        assert fb_high.rating == 5

    def test_rating_too_low(self):
        """Test rating below minimum raises ValueError."""
        with pytest.raises(ValueError, match="between 1 and 5"):
            ArtifactFeedback(artifact_id="a", rating=0)

    def test_rating_too_high(self):
        """Test rating above maximum raises ValueError."""
        with pytest.raises(ValueError, match="between 1 and 5"):
            ArtifactFeedback(artifact_id="a", rating=6)

    def test_rating_negative(self):
        """Test negative rating raises ValueError."""
        with pytest.raises(ValueError, match="between 1 and 5"):
            ArtifactFeedback(artifact_id="a", rating=-1)

    def test_float_coercion(self):
        """Test that float ratings are coerced to int."""
        fb = ArtifactFeedback(
            artifact_id="a", rating=3.0  # type: ignore[arg-type]
        )
        assert fb.rating == 3
        assert isinstance(fb.rating, int)

    def test_non_integer_float_rejected(self):
        """Test that non-integer floats are rejected."""
        with pytest.raises(TypeError, match="must be an integer"):
            ArtifactFeedback(
                artifact_id="a", rating=3.5  # type: ignore[arg-type]
            )

    def test_string_rating_rejected(self):
        """Test that string rating is rejected."""
        with pytest.raises(TypeError, match="must be an integer"):
            ArtifactFeedback(
                artifact_id="a", rating="3"  # type: ignore[arg-type]
            )

    def test_uuid_auto_generated(self):
        """Test that UUID is auto-generated."""
        fb = ArtifactFeedback(artifact_id="a", rating=3)
        assert len(fb.id) > 0

    def test_uuid_preserved(self):
        """Test that custom UUID is preserved."""
        fb = ArtifactFeedback(
            artifact_id="a",
            rating=3,
            uuid="custom-uuid",  # type: ignore[call-arg]
        )
        assert fb.id == "custom-uuid"

    def test_created_at_auto_generated(self):
        """Test that created_at is auto-generated."""
        fb = ArtifactFeedback(artifact_id="a", rating=3)
        assert hasattr(fb, "created_at")
        assert fb.created_at is not None


class TestArtifactFeedbackSerialization:
    """Test feedback serialization round-trips."""

    def test_to_dict(self):
        """Test serialization to dict."""
        fb = ArtifactFeedback(
            artifact_id="art-1",
            rating=4,
            comment="Good",
            agent_id="agent-1",
        )
        data = fb.to_dict()
        assert data["artifact_id"] == "art-1"
        assert data["rating"] == 4
        assert data["comment"] == "Good"
        assert data["agent_id"] == "agent-1"
        assert "uuid" in data
        assert "created_at" in data

    def test_to_dict_minimal(self):
        """Test serialization without optional fields."""
        fb = ArtifactFeedback(artifact_id="art-1", rating=3)
        data = fb.to_dict()
        assert "comment" not in data
        assert "agent_id" not in data

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "artifact_id": "art-1",
            "rating": 4,
            "comment": "Good",
            "agent_id": "agent-1",
            "uuid": "fb-uuid",
            "created_at": "2024-01-01T00:00:00Z",
        }
        fb = ArtifactFeedback.from_dict(data)
        assert fb.artifact_id == "art-1"
        assert fb.rating == 4
        assert fb.comment == "Good"
        assert fb.agent_id == "agent-1"
        assert fb.id == "fb-uuid"
        assert fb.created_at == "2024-01-01T00:00:00Z"

    def test_round_trip(self):
        """Test full serialization round-trip."""
        original = ArtifactFeedback(
            artifact_id="art-1",
            rating=5,
            comment="Excellent",
            agent_id="agent-1",
        )
        data = original.to_dict()
        restored = ArtifactFeedback.from_dict(data)

        assert restored.id == original.id
        assert restored.artifact_id == original.artifact_id
        assert restored.rating == original.rating
        assert restored.comment == original.comment
        assert restored.agent_id == original.agent_id
        assert restored.created_at == original.created_at

    def test_from_dict_missing_optional_fields(self):
        """Test deserialization with missing optional fields."""
        data = {
            "artifact_id": "art-1",
            "rating": 3,
        }
        fb = ArtifactFeedback.from_dict(data)
        assert fb.artifact_id == "art-1"
        assert fb.rating == 3
        assert fb.comment is None
        assert fb.agent_id is None


class TestFeedbackStorage:
    """Test feedback storage operations."""

    def test_save_and_load(self):
        """Test saving and loading feedback."""
        storage = MemoryStorage()
        fb = ArtifactFeedback(
            artifact_id="art-1",
            rating=4,
            comment="Good insight",
        )
        storage.save_feedback(fb)
        loaded = storage.load_feedback(fb.id)

        assert loaded.id == fb.id
        assert loaded.artifact_id == "art-1"
        assert loaded.rating == 4
        assert loaded.comment == "Good insight"

    def test_load_nonexistent_raises(self):
        """Test loading nonexistent feedback raises error."""
        storage = MemoryStorage()
        with pytest.raises(ValueError, match="not found"):
            storage.load_feedback("nonexistent")

    def test_list_all_feedback(self):
        """Test listing all feedback."""
        storage = MemoryStorage()
        fb1 = ArtifactFeedback(artifact_id="art-1", rating=4)
        fb2 = ArtifactFeedback(artifact_id="art-2", rating=3)
        storage.save_feedback(fb1)
        storage.save_feedback(fb2)

        all_ids = storage.list_feedback()
        assert len(all_ids) == 2
        assert fb1.id in all_ids
        assert fb2.id in all_ids

    def test_list_feedback_by_artifact(self):
        """Test listing feedback filtered by artifact."""
        storage = MemoryStorage()
        fb1 = ArtifactFeedback(artifact_id="art-1", rating=4)
        fb2 = ArtifactFeedback(artifact_id="art-1", rating=3)
        fb3 = ArtifactFeedback(artifact_id="art-2", rating=5)
        storage.save_feedback(fb1)
        storage.save_feedback(fb2)
        storage.save_feedback(fb3)

        art1_ids = storage.list_feedback(artifact_id="art-1")
        assert len(art1_ids) == 2
        assert fb1.id in art1_ids
        assert fb2.id in art1_ids

        art2_ids = storage.list_feedback(artifact_id="art-2")
        assert len(art2_ids) == 1
        assert fb3.id in art2_ids

    def test_delete_feedback(self):
        """Test deleting feedback."""
        storage = MemoryStorage()
        fb = ArtifactFeedback(artifact_id="art-1", rating=4)
        storage.save_feedback(fb)
        assert len(storage.list_feedback()) == 1

        storage.delete_feedback(fb)
        assert len(storage.list_feedback()) == 0

    def test_caching(self):
        """Test feedback caching in store dict."""
        storage = MemoryStorage()
        fb = ArtifactFeedback(artifact_id="art-1", rating=4)
        storage.save_feedback(fb)

        assert f"feedback:{fb.id}" in storage.store

        # Load should use cache
        loaded = storage.load_feedback(fb.id)
        assert loaded.id == fb.id

    def test_cascade_delete_artifact(self, mock_stack):
        """Test that deleting an artifact cascades to feedback."""
        storage = MemoryStorage()
        task = Task(
            name="t",
            description="T",
            parameters={},
            prompt="p",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)

        artifact = Artifact(interaction=task_def)
        storage.save_artifact(artifact)

        # Add feedback for this artifact
        fb1 = ArtifactFeedback(artifact_id=artifact.id, rating=4)
        fb2 = ArtifactFeedback(artifact_id=artifact.id, rating=5)
        storage.save_feedback(fb1)
        storage.save_feedback(fb2)
        assert len(storage.list_feedback(artifact.id)) == 2

        # Delete artifact should cascade to feedback
        storage.delete_artifact(artifact)
        assert len(storage.list_feedback(artifact.id)) == 0


class TestQueryEngineRatingBoost:
    """Test rating boost in query engine."""

    def _setup_artifact(self, storage, mock_stack, content):
        """Create a text artifact with content."""
        task = Task(
            name="t",
            description="T",
            parameters={},
            prompt="p",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)
        artifact = Text(
            interaction=task_def,
            content=content,
            format="plain",
        )
        storage.save_artifact(artifact)
        return artifact

    def test_unrated_artifact_no_boost(self, mock_stack):
        """Test that unrated artifacts get no boost."""
        storage = MemoryStorage()
        self._setup_artifact(storage, mock_stack, "test content")

        engine = ArtifactQueryEngine(storage)
        results = engine.query("test")

        assert len(results) == 1
        assert "average_rating" not in results[0].metadata

    def test_high_rated_artifact_boosted(self, mock_stack):
        """Test that highly rated artifacts get positive boost."""
        storage = MemoryStorage()
        artifact = self._setup_artifact(storage, mock_stack, "test content")

        # Rate it 5
        fb = ArtifactFeedback(artifact_id=artifact.id, rating=5)
        storage.save_feedback(fb)

        engine = ArtifactQueryEngine(storage)
        results = engine.query("test")

        assert len(results) == 1
        assert results[0].metadata["average_rating"] == 5.0
        assert results[0].metadata["rating_count"] == 1
        # Score should include boost: (5-3)*1.5 = 3.0
        expected_boost = (5 - RATING_NEUTRAL) * RATING_BOOST_MULTIPLIER
        assert results[0].score > 0
        # Base score is 1.0 (one match of "test"), boost adds 3.0
        assert results[0].score == 1.0 + expected_boost

    def test_low_rated_artifact_penalized(self, mock_stack):
        """Test that poorly rated artifacts get negative boost."""
        storage = MemoryStorage()
        artifact = self._setup_artifact(storage, mock_stack, "test content")

        fb = ArtifactFeedback(artifact_id=artifact.id, rating=1)
        storage.save_feedback(fb)

        engine = ArtifactQueryEngine(storage)
        results = engine.query("test")

        assert len(results) == 1
        assert results[0].metadata["average_rating"] == 1.0
        # (1-3)*1.5 = -3.0, base 1.0, total = -2.0
        expected_boost = (1 - RATING_NEUTRAL) * RATING_BOOST_MULTIPLIER
        assert results[0].score == 1.0 + expected_boost

    def test_average_rating_across_multiple(self, mock_stack):
        """Test average rating calculation with multiple ratings."""
        storage = MemoryStorage()
        artifact = self._setup_artifact(storage, mock_stack, "test content")

        # Rate 3 and 5, average = 4.0
        storage.save_feedback(
            ArtifactFeedback(artifact_id=artifact.id, rating=3)
        )
        storage.save_feedback(
            ArtifactFeedback(artifact_id=artifact.id, rating=5)
        )

        engine = ArtifactQueryEngine(storage)
        results = engine.query("test")

        assert results[0].metadata["average_rating"] == 4.0
        assert results[0].metadata["rating_count"] == 2

    def test_rating_affects_ordering(self, mock_stack):
        """Test that ratings affect result ordering."""
        storage = MemoryStorage()
        # Create two artifacts with same keyword match
        art_good = self._setup_artifact(
            storage, mock_stack, "test artifact good"
        )
        art_bad = self._setup_artifact(storage, mock_stack, "test artifact bad")

        # Rate good one high, bad one low
        storage.save_feedback(
            ArtifactFeedback(artifact_id=art_good.id, rating=5)
        )
        storage.save_feedback(
            ArtifactFeedback(artifact_id=art_bad.id, rating=1)
        )

        engine = ArtifactQueryEngine(storage)
        results = engine.query("test")

        assert len(results) == 2
        assert results[0].artifact_id == art_good.id
        assert results[1].artifact_id == art_bad.id

    def test_neutral_rating_no_boost(self, mock_stack):
        """Test that neutral (3) rating gives zero boost."""
        storage = MemoryStorage()
        artifact = self._setup_artifact(storage, mock_stack, "test content")

        storage.save_feedback(
            ArtifactFeedback(artifact_id=artifact.id, rating=3)
        )

        engine = ArtifactQueryEngine(storage)
        results = engine.query("test")

        # Boost = (3-3)*1.5 = 0.0
        assert results[0].score == 1.0


class TestRateArtifactTool:
    """Test the rate_artifact builtin tool."""

    def test_rate_artifact_success(self, mock_stack):
        """Test successful artifact rating."""
        storage = MemoryStorage()
        mock_stack.agent.environment.storage = storage

        # Create an artifact to rate
        task = Task(
            name="t",
            description="T",
            parameters={},
            prompt="p",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)
        artifact = Text(
            interaction=task_def,
            content="Some insight",
            format="plain",
        )
        storage.save_artifact(artifact)

        from gimle.hugin.tools.builtins.rate_artifact import (
            rate_artifact,
        )

        result = rate_artifact(
            artifact_id=artifact.id,
            rating=4,
            stack=mock_stack,
            comment="Helpful",
        )

        assert not result.is_error
        assert "feedback_id" in result.content

        # Verify feedback was saved
        fb_id = result.content["feedback_id"]
        loaded = storage.load_feedback(fb_id)
        assert loaded.rating == 4
        assert loaded.comment == "Helpful"
        assert loaded.artifact_id == artifact.id

    def test_rate_nonexistent_artifact(self, mock_stack):
        """Test rating a nonexistent artifact returns error."""
        storage = MemoryStorage()
        mock_stack.agent.environment.storage = storage

        from gimle.hugin.tools.builtins.rate_artifact import (
            rate_artifact,
        )

        result = rate_artifact(
            artifact_id="nonexistent",
            rating=4,
            stack=mock_stack,
        )

        assert result.is_error
        assert "not found" in result.content["error"]

    def test_rate_artifact_invalid_rating(self, mock_stack):
        """Test invalid rating returns error."""
        storage = MemoryStorage()
        mock_stack.agent.environment.storage = storage

        # Create artifact
        task = Task(
            name="t",
            description="T",
            parameters={},
            prompt="p",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)
        artifact = Text(
            interaction=task_def,
            content="Content",
            format="plain",
        )
        storage.save_artifact(artifact)

        from gimle.hugin.tools.builtins.rate_artifact import (
            rate_artifact,
        )

        result = rate_artifact(
            artifact_id=artifact.id,
            rating=10,
            stack=mock_stack,
        )

        assert result.is_error
        assert "between 1 and 5" in result.content["error"]

    def test_rate_artifact_float_coercion(self, mock_stack):
        """Test that float ratings are coerced by tool."""
        storage = MemoryStorage()
        mock_stack.agent.environment.storage = storage

        task = Task(
            name="t",
            description="T",
            parameters={},
            prompt="p",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)
        artifact = Text(
            interaction=task_def,
            content="Content",
            format="plain",
        )
        storage.save_artifact(artifact)

        from gimle.hugin.tools.builtins.rate_artifact import (
            rate_artifact,
        )

        result = rate_artifact(
            artifact_id=artifact.id,
            rating=4.0,  # type: ignore[arg-type]
            stack=mock_stack,
        )

        assert not result.is_error
        fb_id = result.content["feedback_id"]
        loaded = storage.load_feedback(fb_id)
        assert loaded.rating == 4

    def test_rate_artifact_no_storage(self, mock_stack):
        """Test rating without storage returns error."""
        mock_stack.agent.environment.storage = None

        from gimle.hugin.tools.builtins.rate_artifact import (
            rate_artifact,
        )

        result = rate_artifact(
            artifact_id="any",
            rating=4,
            stack=mock_stack,
        )

        assert result.is_error
        assert "No storage" in result.content["error"]

    def test_rate_artifact_captures_agent_id(self, mock_stack):
        """Test that agent_id is captured from stack."""
        storage = MemoryStorage()
        mock_stack.agent.environment.storage = storage

        task = Task(
            name="t",
            description="T",
            parameters={},
            prompt="p",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)
        artifact = Text(
            interaction=task_def,
            content="Content",
            format="plain",
        )
        storage.save_artifact(artifact)

        from gimle.hugin.tools.builtins.rate_artifact import (
            rate_artifact,
        )

        result = rate_artifact(
            artifact_id=artifact.id,
            rating=5,
            stack=mock_stack,
        )

        assert not result.is_error
        fb_id = result.content["feedback_id"]
        loaded = storage.load_feedback(fb_id)
        assert loaded.agent_id == mock_stack.agent.id


class TestEndToEnd:
    """End-to-end test combining artifacts, feedback, and queries."""

    def test_full_workflow(self, mock_stack):
        """Test create artifact, rate it, query with boost."""
        storage = MemoryStorage()
        mock_stack.agent.environment.storage = storage

        task = Task(
            name="t",
            description="T",
            parameters={},
            prompt="p",
            tools=[],
        )
        task_def = TaskDefinition(stack=mock_stack, task=task)
        storage.save_interaction(task_def)

        # Create artifacts
        good = Text(
            interaction=task_def,
            content="Python web framework comparison",
            format="markdown",
        )
        bad = Text(
            interaction=task_def,
            content="Python cooking recipes",
            format="markdown",
        )
        storage.save_artifact(good)
        storage.save_artifact(bad)

        # Rate them
        storage.save_feedback(ArtifactFeedback(artifact_id=good.id, rating=5))
        storage.save_feedback(ArtifactFeedback(artifact_id=bad.id, rating=1))

        # Query
        engine = ArtifactQueryEngine(storage)
        results = engine.query("python")

        assert len(results) == 2
        # Good artifact should rank first due to rating
        assert results[0].artifact_id == good.id
        assert results[0].metadata["average_rating"] == 5.0
        assert results[1].artifact_id == bad.id
        assert results[1].metadata["average_rating"] == 1.0
