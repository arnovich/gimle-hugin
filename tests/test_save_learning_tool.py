"""Tests for the dreaming.save_learning builtin tool."""

import pytest

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.learning import Learning
from gimle.hugin.artifacts.text import Text
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.tools.builtins.save_learning import save_learning
from gimle.hugin.tools.tool import Tool

from .memory_storage import MemoryStorage


@pytest.fixture
def dream_stack():
    """Return a stack whose environment carries a dream scope."""
    storage = MemoryStorage()
    env = Environment(
        storage=storage,
        env_vars={
            "dream_scope": {
                "config": "researcher",
                "task": "analyze_sales",
                "app": None,
            }
        },
    )
    session = Session(environment=env)
    config = Config(
        llm_model="test-model",
        system_template="system",
        name="dreamer",
        description="d",
    )
    agent = Agent(session=session, config=config)
    task = Task(name="t", description="", parameters={}, prompt="p", tools=[])
    task_def = TaskDefinition(stack=agent.stack, task=task)
    agent.stack.add_interaction(task_def)
    return agent.stack, storage


def test_tool_is_registered():
    """The tool is discoverable under its registered name."""
    assert Tool.get_tool("dreaming.save_learning") is not None


def test_save_learning_stamps_scope_from_run(dream_stack):
    """The tool stamps scope from the dream run context."""
    stack, storage = dream_stack

    response = save_learning(
        content="Validate dates before parsing.",
        stack=stack,
        source_artifact_ids=["art-1", "art-2"],
        confidence=0.8,
    )

    assert response.is_error is False
    learning_id = response.content["learning"]

    record = storage.load_artifact_record(learning_id)
    assert record["type"] == "Learning"
    assert record["data"]["scope_config"] == "researcher"
    assert record["data"]["scope_task"] == "analyze_sales"
    assert record["data"]["source_artifact_ids"] == ["art-1", "art-2"]
    assert record["data"]["derived_from"] == "dream"


def test_save_learning_self_rates(dream_stack):
    """The tool self-rates the learning via agent feedback."""
    stack, storage = dream_stack

    response = save_learning(content="A lesson.", stack=stack, confidence=0.8)
    learning_id = response.content["learning"]

    feedback_ids = storage.list_feedback(learning_id)
    assert len(feedback_ids) == 1
    feedback = storage.load_feedback(feedback_ids[0])
    assert feedback.source == "agent"
    # 0.8 -> 1 + 0.8*4 = 4.2 -> 4
    assert feedback.rating == 4


def test_saved_learning_is_selectable(dream_stack):
    """A saved learning is immediately selectable for its scope."""
    from gimle.hugin.dreaming.selector import select_learnings

    stack, storage = dream_stack
    save_learning(content="Selectable lesson.", stack=stack, confidence=0.9)

    selected = select_learnings(
        storage, config="researcher", task="analyze_sales"
    )
    assert len(selected) == 1
    assert selected[0].content == "Selectable lesson."


def test_save_learning_structurally_supersedes_same_scope_learning(dream_stack):
    """The old learning stays stored but immediately leaves active selection."""
    from gimle.hugin.dreaming.selector import select_learnings

    stack, storage = dream_stack
    old = Learning(
        interaction=stack.interactions[-1],
        content="Old lesson.",
        scope_config="researcher",
        scope_task="analyze_sales",
    )
    storage.save_artifact(old)

    response = save_learning(
        content="Replacement lesson.",
        stack=stack,
        supersedes=[old.id],
    )

    assert response.is_error is False
    new_id = response.content["learning"]
    assert storage.load_artifact_record(new_id)["data"]["supersedes"] == [
        old.id
    ]
    assert old.id in storage.list_artifacts()
    selected = select_learnings(
        storage, config="researcher", task="analyze_sales"
    )
    assert [item.content for item in selected] == ["Replacement lesson."]


def test_supersedes_rejects_missing_or_non_learning_targets(dream_stack):
    """Every structural edge must point to an existing Learning."""
    stack, storage = dream_stack

    missing = save_learning(
        content="Replacement.", stack=stack, supersedes=["missing-id"]
    )
    assert missing.is_error is True
    assert storage.list_artifacts() == []

    text = Text(interaction=stack.interactions[-1], content="not a learning")
    storage.save_artifact(text)
    wrong_type = save_learning(
        content="Replacement.", stack=stack, supersedes=[text.id]
    )
    assert wrong_type.is_error is True
    assert storage.list_artifacts() == [text.id]


def test_supersedes_rejects_a_non_list_argument(dream_stack):
    """Direct callers receive a tool error instead of character-wise ids."""
    stack, storage = dream_stack
    response = save_learning(
        content="Replacement.",
        stack=stack,
        supersedes="not-a-list",  # type: ignore[arg-type]
    )

    assert response.is_error is True
    assert storage.list_artifacts() == []


def test_supersedes_rejects_a_different_scope(dream_stack):
    """A task-specific replacement cannot retire another scope's memory."""
    stack, storage = dream_stack
    other = Learning(
        interaction=stack.interactions[-1],
        content="Another scope.",
        scope_config="other",
        scope_task="analyze_sales",
    )
    storage.save_artifact(other)

    response = save_learning(
        content="Replacement.", stack=stack, supersedes=[other.id]
    )

    assert response.is_error is True
    assert "different scope" in response.content["error"]
    assert storage.list_artifacts() == [other.id]


def test_supersedes_rejects_a_cycle(dream_stack, monkeypatch):
    """A pre-existing forward link cannot be closed into a cycle."""
    stack, storage = dream_stack
    old = Learning(
        interaction=stack.interactions[-1],
        content="Forward reference.",
        scope_config="researcher",
        scope_task="analyze_sales",
        supersedes=["new-id"],
        uuid="old-id",
    )
    storage.save_artifact(old)
    monkeypatch.setattr(
        "gimle.hugin.utils.uuid.generate_uuid", lambda: "new-id"
    )

    response = save_learning(
        content="Would close cycle.", stack=stack, supersedes=[old.id]
    )

    assert response.is_error is True
    assert "cycle" in response.content["error"]
    assert storage.list_artifacts() == [old.id]
