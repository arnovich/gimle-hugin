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
    """Source-aware quality ranking is stable and budget-capped."""

    def test_sorted_by_rating(self, storage_and_interaction):
        """Higher-rated learnings sort first."""
        storage, interaction = storage_and_interaction
        low = _save_learning(storage, interaction, "low", scope_config="r")
        high = _save_learning(storage, interaction, "high", scope_config="r")
        _rate(storage, low.id, 1)
        _rate(storage, high.id, 5)

        result = select_learnings(storage, config="r")
        assert [item.content for item in result] == ["high", "low"]

    def test_human_rating_replaces_agent_birth_confidence(
        self, storage_and_interaction
    ):
        """Independent feedback is not diluted by self-confidence."""
        storage, interaction = storage_and_interaction
        reviewed = _save_learning(
            storage, interaction, "reviewed", scope_config="r"
        )
        agent_only = _save_learning(
            storage, interaction, "agent-only", scope_config="r"
        )
        _rate(storage, reviewed.id, 5, source="agent")
        _rate(storage, reviewed.id, 1, source="human")
        _rate(storage, agent_only.id, 2, source="agent")

        result = select_learnings(storage, config="r")

        assert [item.content for item in result] == ["agent-only", "reviewed"]
        assert result[1].average_rating == 1.0
        assert result[1].rating_count == 1
        assert result[1].rating_source == "human"

    def test_human_review_wins_an_equal_score(self, storage_and_interaction):
        """Equal quality prefers independent evidence over self-assessment."""
        storage, interaction = storage_and_interaction
        agent_only = _save_learning(
            storage,
            interaction,
            "agent-only",
            scope_config="r",
            uuid="a-agent",
        )
        reviewed = _save_learning(
            storage,
            interaction,
            "reviewed",
            scope_config="r",
            uuid="z-reviewed",
        )
        _rate(storage, agent_only.id, 5, source="agent")
        _rate(storage, reviewed.id, 1, source="agent")
        _rate(storage, reviewed.id, 5, source="human")

        result = select_learnings(storage, config="r")

        assert [item.content for item in result] == ["reviewed", "agent-only"]
        assert result[0].rating_source == "human"

    def test_more_human_evidence_breaks_an_equal_average(
        self, storage_and_interaction
    ):
        """Rating count is considered only after score and source agree."""
        storage, interaction = storage_and_interaction
        one_rating = _save_learning(
            storage,
            interaction,
            "one-rating",
            scope_config="r",
            uuid="a-one",
        )
        two_ratings = _save_learning(
            storage,
            interaction,
            "two-ratings",
            scope_config="r",
            uuid="z-two",
        )
        _rate(storage, one_rating.id, 4, source="human")
        _rate(storage, two_ratings.id, 3, source="human")
        _rate(storage, two_ratings.id, 5, source="human")

        result = select_learnings(storage, config="r")

        assert [item.content for item in result] == [
            "two-ratings",
            "one-rating",
        ]
        assert result[0].average_rating == 4.0
        assert result[0].rating_count == 2

    def test_equal_ratings_do_not_prefer_recency(self, storage_and_interaction):
        """The final tie-break is stable artifact id, not creation time."""
        storage, interaction = storage_and_interaction
        old = _save_learning(
            storage,
            interaction,
            "old",
            scope_config="r",
            uuid="a-old",
            created_at="2020-01-01T00:00:00+00:00",
        )
        new = _save_learning(
            storage,
            interaction,
            "new",
            scope_config="r",
            uuid="z-new",
            created_at="2030-01-01T00:00:00+00:00",
        )
        _rate(storage, old.id, 4, source="agent")
        _rate(storage, new.id, 4, source="agent")

        result = select_learnings(storage, config="r")

        assert [item.content for item in result] == ["old", "new"]

    def test_old_human_review_survives_equal_new_confidence_at_budget(
        self, storage_and_interaction
    ):
        """Five newer self-ratings cannot evict equal human-backed quality."""
        storage, interaction = storage_and_interaction
        old = _save_learning(
            storage,
            interaction,
            "reviewed-old",
            scope_config="r",
            uuid="reviewed-old",
            created_at="2020-01-01T00:00:00+00:00",
        )
        _rate(storage, old.id, 5, source="agent")
        _rate(storage, old.id, 5, source="human")
        for i in range(5):
            new = _save_learning(
                storage,
                interaction,
                f"new-{i}",
                scope_config="r",
                uuid=f"new-{i}",
                created_at=f"2030-01-01T00:00:0{i}+00:00",
            )
            _rate(storage, new.id, 5, source="agent")

        result = select_learnings(storage, config="r", budget=5)

        assert result[0].artifact_id == old.id
        assert len(result) == 5

    def test_budget_caps_results(self, storage_and_interaction):
        """The budget caps how many learnings are returned."""
        storage, interaction = storage_and_interaction
        for i in range(5):
            _save_learning(
                storage, interaction, f"lesson-{i}", scope_config="r"
            )

        assert len(select_learnings(storage, config="r", budget=2)) == 2


class TestStructuralSupersession:
    """Supersession retires active memory without deleting its audit record."""

    def test_superseded_learning_is_excluded_regardless_of_rating(
        self, storage_and_interaction
    ):
        """A high old rating cannot resurrect a structurally retired lesson."""
        storage, interaction = storage_and_interaction
        old = _save_learning(
            storage, interaction, "old", scope_config="researcher"
        )
        replacement = _save_learning(
            storage,
            interaction,
            "replacement",
            scope_config="researcher",
            supersedes=[old.id],
        )
        _rate(storage, old.id, 5)
        _rate(storage, replacement.id, 1)

        selected = select_learnings(storage, config="researcher")
        assert [item.artifact_id for item in selected] == [replacement.id]
        assert set(storage.list_artifacts()) == {old.id, replacement.id}

    def test_supersession_chain_is_monotonic(self, storage_and_interaction):
        """C replacing B replacing A leaves only C active."""
        storage, interaction = storage_and_interaction
        first = _save_learning(
            storage, interaction, "first", scope_config="researcher"
        )
        second = _save_learning(
            storage,
            interaction,
            "second",
            scope_config="researcher",
            supersedes=[first.id],
        )
        third = _save_learning(
            storage,
            interaction,
            "third",
            scope_config="researcher",
            supersedes=[second.id],
        )

        selected = select_learnings(storage, config="researcher")
        assert [item.artifact_id for item in selected] == [third.id]

    def test_cross_scope_edge_is_ignored(self, storage_and_interaction):
        """Corrupt imported data cannot retire another config's learning."""
        storage, interaction = storage_and_interaction
        old = _save_learning(
            storage, interaction, "research lesson", scope_config="researcher"
        )
        _save_learning(
            storage,
            interaction,
            "other lesson",
            scope_config="other",
            supersedes=[old.id],
        )

        selected = select_learnings(storage, config="researcher")
        assert [item.artifact_id for item in selected] == [old.id]

    def test_cyclic_imported_edges_are_ignored(
        self, storage_and_interaction, caplog
    ):
        """Malformed historical cycles must not hide every learning involved."""
        storage, interaction = storage_and_interaction
        third = _save_learning(
            storage,
            interaction,
            "unrelated target",
            scope_config="researcher",
            uuid="third-id",
        )
        first = _save_learning(
            storage,
            interaction,
            "first",
            scope_config="researcher",
            supersedes=["second-id", third.id],
            uuid="first-id",
        )
        second = _save_learning(
            storage,
            interaction,
            "second",
            scope_config="researcher",
            supersedes=[first.id],
            uuid="second-id",
        )

        selected = select_learnings(storage, config="researcher")
        assert {item.artifact_id for item in selected} == {
            first.id,
            second.id,
            third.id,
        }
        assert any(
            "cyclic supersession" in record.message for record in caplog.records
        )


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
