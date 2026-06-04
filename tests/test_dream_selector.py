"""Tests for the dreaming learning selector."""

import pytest

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.feedback import ArtifactFeedback
from gimle.hugin.artifacts.learning import Learning
from gimle.hugin.dreaming.selector import (
    render_learnings_block,
    select_learnings,
)
from gimle.hugin.interaction.task_definition import TaskDefinition

from .memory_storage import MemoryStorage


@pytest.fixture
def storage_and_interaction():
    """Return a MemoryStorage plus a persisted interaction for learnings."""
    storage = MemoryStorage()
    session = Session(environment=Environment(storage=storage))
    config = Config(
        llm_model="test-model",
        system_template="system",
        name="host",
        description="d",
    )
    agent = Agent(session=session, config=config)
    task = Task(name="t", description="", parameters={}, prompt="p", tools=[])
    interaction = TaskDefinition(stack=agent.stack, task=task)
    storage.save_interaction(interaction)
    return storage, interaction


def _save_learning(storage, interaction, content, **scope):
    learning = Learning(interaction=interaction, content=content, **scope)
    storage.save_artifact(learning)
    return learning


def _rate(storage, artifact_id, rating, source="human"):
    storage.save_feedback(
        ArtifactFeedback(artifact_id=artifact_id, rating=rating, source=source)
    )


class TestScopeFiltering:
    """Selection respects scope_config / scope_task / scope_app."""

    def test_config_scoped_learning_matches_config(
        self, storage_and_interaction
    ):
        """A config-scoped learning matches only its config."""
        storage, interaction = storage_and_interaction
        _save_learning(
            storage, interaction, "lesson", scope_config="researcher"
        )

        assert len(select_learnings(storage, config="researcher")) == 1
        assert select_learnings(storage, config="other") == []

    def test_task_specific_only_matches_that_task(
        self, storage_and_interaction
    ):
        """A task-specific learning matches only that task."""
        storage, interaction = storage_and_interaction
        _save_learning(
            storage,
            interaction,
            "lesson",
            scope_config="researcher",
            scope_task="analyze_sales",
        )

        assert (
            len(
                select_learnings(
                    storage, config="researcher", task="analyze_sales"
                )
            )
            == 1
        )
        # Config-wide selection (no task) must not pull a task-specific learning.
        assert select_learnings(storage, config="researcher", task=None) == []

    def test_config_wide_learning_matches_any_task(
        self, storage_and_interaction
    ):
        """A config-wide learning matches any task in the config."""
        storage, interaction = storage_and_interaction
        _save_learning(
            storage, interaction, "lesson", scope_config="researcher"
        )

        result = select_learnings(storage, config="researcher", task="anything")
        assert len(result) == 1

    def test_app_scoped_learning_matches_app(self, storage_and_interaction):
        """An app-scoped learning matches only its app."""
        storage, interaction = storage_and_interaction
        _save_learning(
            storage, interaction, "world fact", scope_app="the_hugins"
        )

        assert len(select_learnings(storage, app="the_hugins")) == 1
        assert select_learnings(storage, app="other_world") == []

    def test_unscoped_learning_never_selected(self, storage_and_interaction):
        """A fully unscoped learning is never selected."""
        storage, interaction = storage_and_interaction
        _save_learning(storage, interaction, "global lesson")

        assert select_learnings(storage, config="researcher") == []


class TestRankingAndBudget:
    """Higher-rated, fresher learnings win; budget caps the count."""

    def test_sorted_by_rating(self, storage_and_interaction):
        """Higher-rated learnings sort first."""
        storage, interaction = storage_and_interaction
        low = _save_learning(storage, interaction, "low", scope_config="r")
        high = _save_learning(storage, interaction, "high", scope_config="r")
        _rate(storage, low.id, 1)
        _rate(storage, high.id, 5)

        result = select_learnings(storage, config="r")
        assert [item.content for item in result] == ["high", "low"]

    def test_budget_caps_results(self, storage_and_interaction):
        """The budget caps how many learnings are returned."""
        storage, interaction = storage_and_interaction
        for i in range(5):
            _save_learning(
                storage, interaction, f"lesson-{i}", scope_config="r"
            )

        assert len(select_learnings(storage, config="r", budget=2)) == 2


class TestRenderBlock:
    """The injected text block formatting."""

    def test_empty_when_no_learnings(self):
        """An empty selection renders an empty block."""
        assert render_learnings_block([]) == ""

    def test_bulleted_list(self, storage_and_interaction):
        """Selected learnings render as a bulleted list."""
        storage, interaction = storage_and_interaction
        _save_learning(storage, interaction, "first", scope_config="r")
        _save_learning(storage, interaction, "second", scope_config="r")

        block = render_learnings_block(select_learnings(storage, config="r"))
        assert "- first" in block
        assert "- second" in block
