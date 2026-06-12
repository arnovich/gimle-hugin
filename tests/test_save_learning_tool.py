"""Tests for the dreaming.save_learning builtin tool."""

import pytest

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.agent.task import Task
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
