"""Conservative physical pruning for structurally superseded learnings."""

import sys
from datetime import datetime, timezone

import pytest

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.feedback import ArtifactFeedback
from gimle.hugin.artifacts.learning import Learning
from gimle.hugin.cli.cli import main
from gimle.hugin.dreaming.prune import (
    plan_learning_prune,
    prune_learnings,
)
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.storage.local import LocalStorage

from .memory_storage import MemoryStorage

NOW = datetime(2026, 3, 15, tzinfo=timezone.utc)


def _storage_and_interaction(storage):
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


@pytest.fixture
def storage_and_interaction():
    return _storage_and_interaction(MemoryStorage())


def _save_learning(
    storage,
    interaction,
    artifact_id,
    created_at,
    *,
    supersedes=None,
    scope_config="researcher",
):
    learning = Learning(
        interaction=interaction,
        content=artifact_id,
        scope_config=scope_config,
        supersedes=supersedes or [],
        uuid=artifact_id,
        created_at=created_at,
    )
    interaction.artifacts.append(learning)
    storage.save_interaction(interaction)
    return learning


class TestLearningPrunePlan:
    """The plan is structural, deterministic, and fail-closed."""

    def test_only_retained_structural_targets_become_candidates(
        self, storage_and_interaction
    ):
        storage, interaction = storage_and_interaction
        old = _save_learning(
            storage,
            interaction,
            "old",
            "2025-12-01T00:00:00+00:00",
        )
        _save_learning(
            storage,
            interaction,
            "replacement",
            "2026-02-01T00:00:00+00:00",
            supersedes=[old.id],
        )
        _save_learning(
            storage,
            interaction,
            "low-ranked-but-active",
            "2020-01-01T00:00:00+00:00",
        )

        candidates = plan_learning_prune(storage, retention_days=30, now=NOW)

        assert [candidate.artifact_id for candidate in candidates] == [old.id]
        assert candidates[0].superseded_by == ("replacement",)
        assert candidates[0].superseded_at == "2026-02-01T00:00:00+00:00"
        assert candidates[0].scope_config == "researcher"

    def test_retention_begins_when_replacement_records_supersession(
        self, storage_and_interaction
    ):
        storage, interaction = storage_and_interaction
        old = _save_learning(
            storage,
            interaction,
            "very-old",
            "2020-01-01T00:00:00+00:00",
        )
        _save_learning(
            storage,
            interaction,
            "recent-replacement",
            "2026-03-01T00:00:00+00:00",
            supersedes=[old.id],
        )

        assert plan_learning_prune(storage, retention_days=30, now=NOW) == []

    def test_cross_scope_and_cyclic_imports_never_authorize_deletion(
        self, storage_and_interaction
    ):
        storage, interaction = storage_and_interaction
        target = _save_learning(
            storage,
            interaction,
            "target",
            "2025-01-01T00:00:00+00:00",
        )
        _save_learning(
            storage,
            interaction,
            "other-scope",
            "2025-02-01T00:00:00+00:00",
            supersedes=[target.id],
            scope_config="other",
        )
        _save_learning(
            storage,
            interaction,
            "cycle-a",
            "2025-03-01T00:00:00+00:00",
            supersedes=["cycle-b"],
        )
        _save_learning(
            storage,
            interaction,
            "cycle-b",
            "2025-04-01T00:00:00+00:00",
            supersedes=["cycle-a"],
        )

        assert plan_learning_prune(storage, retention_days=0, now=NOW) == []

    def test_bad_or_impossible_timestamps_fail_closed(
        self, storage_and_interaction, caplog
    ):
        storage, interaction = storage_and_interaction
        target = _save_learning(
            storage,
            interaction,
            "target",
            "2025-06-01T00:00:00+00:00",
        )
        replacement = _save_learning(
            storage,
            interaction,
            "replacement",
            "2025-05-01T00:00:00+00:00",
            supersedes=[target.id],
        )

        assert plan_learning_prune(storage, retention_days=0, now=NOW) == []
        assert "predates it" in caplog.text

        storage._artifacts[replacement.id]["data"]["created_at"] = "invalid"
        storage.store.pop(f"artifact_record:{replacement.id}", None)
        caplog.clear()

        assert plan_learning_prune(storage, retention_days=0, now=NOW) == []
        assert "invalid created_at" in caplog.text

    def test_invalid_policy_time_is_rejected(self, storage_and_interaction):
        storage, _ = storage_and_interaction

        with pytest.raises(ValueError, match="non-negative"):
            plan_learning_prune(storage, retention_days=-1, now=NOW)
        with pytest.raises(ValueError, match="timezone"):
            plan_learning_prune(
                storage,
                retention_days=30,
                now=datetime(2026, 3, 15),
            )


class TestPruneLearningApply:
    """Mutation requires explicit apply and uses reference-safe deletion."""

    def test_default_dry_run_changes_nothing(self, storage_and_interaction):
        storage, interaction = storage_and_interaction
        old = _save_learning(
            storage,
            interaction,
            "old",
            "2025-01-01T00:00:00+00:00",
        )
        _save_learning(
            storage,
            interaction,
            "replacement",
            "2025-02-01T00:00:00+00:00",
            supersedes=[old.id],
        )

        candidates = prune_learnings(storage, retention_days=30, now=NOW)

        assert [candidate.artifact_id for candidate in candidates] == [old.id]
        assert old.id in storage.list_artifacts()
        assert (
            old.id in storage._interactions[interaction.id]["data"]["artifacts"]
        )

    def test_apply_deletes_artifact_feedback_and_owner_reference(
        self, storage_and_interaction
    ):
        storage, interaction = storage_and_interaction
        old = _save_learning(
            storage,
            interaction,
            "old",
            "2025-01-01T00:00:00+00:00",
        )
        replacement = _save_learning(
            storage,
            interaction,
            "replacement",
            "2025-02-01T00:00:00+00:00",
            supersedes=[old.id],
        )
        feedback = ArtifactFeedback(
            artifact_id=old.id, rating=5, source="human"
        )
        storage.save_feedback(feedback)
        storage.store.clear()  # exercise fresh raw-record artifact hydration

        candidates = prune_learnings(
            storage, retention_days=30, apply=True, now=NOW
        )

        assert [candidate.artifact_id for candidate in candidates] == [old.id]
        assert storage.list_artifacts() == [replacement.id]
        assert storage.list_feedback(old.id) == []
        assert feedback.id not in storage._feedback
        assert storage._interactions[interaction.id]["data"]["artifacts"] == [
            replacement.id
        ]


def test_cli_previews_then_applies_on_local_storage(
    tmp_path, capsys, monkeypatch
):
    """The filesystem command is preview-only until --apply is explicit."""
    storage, interaction = _storage_and_interaction(
        LocalStorage(base_path=tmp_path)
    )
    old = _save_learning(
        storage,
        interaction,
        "old",
        "2020-01-01T00:00:00+00:00",
    )
    replacement = _save_learning(
        storage,
        interaction,
        "replacement",
        "2020-02-01T00:00:00+00:00",
        supersedes=[old.id],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "hugin",
            "prune-learnings",
            "--storage-path",
            str(tmp_path),
            "--retention-days",
            "30",
        ],
    )
    assert main() == 0
    preview = capsys.readouterr().out
    assert "Dry run: would prune 1" in preview
    assert "No changes made" in preview
    assert set(storage.list_artifacts()) == {old.id, replacement.id}

    sys.argv.append("--apply")
    assert main() == 0
    applied = capsys.readouterr().out
    assert "Pruned 1" in applied
    assert storage.list_artifacts() == [replacement.id]


def test_cli_rejects_negative_retention(monkeypatch, capsys):
    """Invalid destructive-policy input is rejected by argument parsing."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["hugin", "prune-learnings", "--retention-days", "-1"],
    )

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 2
    assert "must be non-negative" in capsys.readouterr().err
