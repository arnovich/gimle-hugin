"""Tests for render-time injection of consolidated learnings."""

import pytest

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.learning import Learning
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.llm.prompt.renderer import PromptRenderer

from .memory_storage import MemoryStorage


@pytest.fixture
def agent_on_storage():
    """Return an agent with a TaskDefinition, backed by MemoryStorage."""
    storage = MemoryStorage()
    session = Session(environment=Environment(storage=storage))
    config = Config(
        llm_model="test-model",
        system_template="system",
        name="researcher",
        description="d",
    )
    agent = Agent(session=session, config=config)
    task = Task(
        name="analyze", description="", parameters={}, prompt="p", tools=[]
    )
    task_def = TaskDefinition(stack=agent.stack, task=task)
    agent.stack.add_interaction(task_def)
    storage.save_interaction(task_def)
    return agent, storage, task_def


def _save_learning(storage, interaction, content, **scope):
    storage.save_artifact(
        Learning(interaction=interaction, content=content, **scope)
    )


class TestLearningInjection:
    """A {{ learnings }} template receives its scoped learnings; others don't."""

    def test_injected_when_referenced(self, agent_on_storage):
        """A {{ learnings }} template receives its scoped learnings."""
        agent, storage, task_def = agent_on_storage
        _save_learning(
            storage,
            task_def,
            "Validate dates first.",
            scope_config="researcher",
        )

        out = PromptRenderer(agent).render_prompt("Notes:\n{{ learnings }}", {})
        assert "Validate dates first." in out

    def test_not_injected_without_reference(self, agent_on_storage):
        """A template without {{ learnings }} is left unchanged."""
        agent, storage, task_def = agent_on_storage
        _save_learning(
            storage,
            task_def,
            "Validate dates first.",
            scope_config="researcher",
        )

        out = PromptRenderer(agent).render_prompt("Just a plain prompt.", {})
        assert out == "Just a plain prompt."
        assert "Validate dates first." not in out

    def test_caller_value_not_overridden(self, agent_on_storage):
        """A caller-provided learnings value is not overridden."""
        agent, storage, task_def = agent_on_storage
        _save_learning(
            storage, task_def, "From storage.", scope_config="researcher"
        )

        out = PromptRenderer(agent).render_prompt(
            "{{ learnings }}", {"learnings": "explicit override"}
        )
        assert out == "explicit override"

    def test_other_config_learning_not_injected(self, agent_on_storage):
        """A learning for another config is not injected."""
        agent, storage, task_def = agent_on_storage
        _save_learning(
            storage, task_def, "Other scope.", scope_config="someone_else"
        )

        out = PromptRenderer(agent).render_prompt("{{ learnings }}", {})
        assert "Other scope." not in out

    def test_cold_start_renders_empty(self, agent_on_storage):
        """With no learnings, {{ learnings }} renders empty."""
        agent, _storage, _task_def = agent_on_storage

        out = PromptRenderer(agent).render_prompt("Notes: {{ learnings }}", {})
        assert out == "Notes:"

    def test_literal_jinja_in_learning_preserved(self, agent_on_storage):
        """A learning containing {{ ... }} reaches output verbatim (task 020)."""
        agent, storage, task_def = agent_on_storage
        _save_learning(
            storage,
            task_def,
            "Reference a param as {{ foo.value }}.",
            scope_config="researcher",
        )

        out = PromptRenderer(agent).render_prompt("{{ learnings }}", {})
        assert "{{ foo.value }}" in out
