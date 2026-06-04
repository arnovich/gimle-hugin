"""Tests for the Learning artifact (consolidated 'dreaming' memory)."""

from gimle.hugin.agent.task import Task

# Import Learning to ensure it is registered in the artifact registry.
from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.artifacts.learning import Learning
from gimle.hugin.interaction.task_definition import TaskDefinition

from .memory_storage import MemoryStorage


def _task_def(stack):
    task = Task(
        name="test_task",
        description="Test",
        parameters={},
        prompt="Do something",
        tools=[],
    )
    return TaskDefinition(stack=stack, task=task)


class TestLearningArtifact:
    """Learning creation, defaults, and registration."""

    def test_registered_under_learning(self):
        """Learning is registered so from_dict can resolve it by type."""
        assert Artifact.get_type("Learning") is Learning

    def test_defaults(self, mock_stack):
        """Scope/provenance fields default sensibly."""
        learning = Learning(
            interaction=_task_def(mock_stack),
            content="Always validate dates first.",
        )
        assert learning.scope_config is None
        assert learning.scope_task is None
        assert learning.scope_app is None
        assert learning.source_artifact_ids == []
        assert learning.confidence == 0.0
        assert learning.derived_from == "dream"

    def test_distinct_default_lists(self, mock_stack):
        """Each Learning gets its own source_artifact_ids list."""
        a = Learning(interaction=_task_def(mock_stack), content="a")
        b = Learning(interaction=_task_def(mock_stack), content="b")
        a.source_artifact_ids.append("x")
        assert b.source_artifact_ids == []


class TestLearningSerialization:
    """Learning round-trips through to_dict / from_dict."""

    def test_round_trip_preserves_fields(self, mock_stack):
        """All scope/provenance fields survive serialization."""
        storage = MemoryStorage()
        task_def = _task_def(mock_stack)
        storage.save_interaction(task_def)
        learning = Learning(
            interaction=task_def,
            content="Prefer ';' delimiters over newlines for list output.",
            scope_config="research_assistant",
            scope_task="analyze_sales",
            scope_app="the_hugins",
            source_artifact_ids=["art-1", "art-2"],
            confidence=0.8,
        )

        data = learning.to_dict()
        assert data["type"] == "Learning"

        restored = Artifact.from_dict(data, storage=storage, stack=mock_stack)
        assert isinstance(restored, Learning)
        assert restored.uuid == learning.uuid
        assert restored.content == learning.content
        assert restored.scope_config == "research_assistant"
        assert restored.scope_task == "analyze_sales"
        assert restored.scope_app == "the_hugins"
        assert restored.source_artifact_ids == ["art-1", "art-2"]
        assert restored.confidence == 0.8
        assert restored.derived_from == "dream"
