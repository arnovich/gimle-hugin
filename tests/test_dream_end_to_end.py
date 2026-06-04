"""End-to-end dreaming loop: run -> dream -> re-render shows the learning."""

from typing import List
from unittest.mock import Mock, patch

import gimle.hugin.tools  # noqa: F401  (registers dreaming.save_learning)
from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.text import Text
from gimle.hugin.dreaming.consolidate import run_dream
from gimle.hugin.llm.models.model import Model, ModelResponse
from gimle.hugin.llm.prompt.renderer import PromptRenderer

from .memory_storage import MemoryStorage

LESSON = "Always check for null dates before parsing."


class ScriptedModel(Model):
    """A model that replays a fixed list of responses, then repeats the last."""

    def __init__(self, responses: List[ModelResponse]):
        """Store the scripted responses to replay."""
        super().__init__(
            {
                "model": "test-model",
                "temperature": 0,
                "max_tokens": 100,
                "tool_choice": {"type": "auto"},
            }
        )
        self._responses = responses
        self._index = 0

    def chat_completion(self, system_prompt, messages, tools=None):
        """Return the next scripted response, repeating the last."""
        response = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        return response


def _make_researcher_agent(storage):
    session = Session(environment=Environment(storage=storage))
    config = Config(
        name="researcher",
        description="d",
        system_template="system",
        llm_model="test-model",
    )
    task = Task(
        name="analyze", description="", parameters={}, prompt="p", tools=[]
    )
    return Agent.create_from_task(session, config, task)


def _seed_episodic_memory(storage):
    """Simulate a prior researcher run that saved one insight."""
    agent = _make_researcher_agent(storage)
    task_def = agent.stack.interactions[0]
    artifact = Text(
        interaction=task_def,
        content="When dates are null the parser silently returns nothing.",
    )
    task_def.add_artifact(artifact)
    storage.save_agent(agent)


def test_run_dream_then_reinjects_learning():
    """Run -> dream -> re-render shows the consolidated learning."""
    storage = MemoryStorage()
    _seed_episodic_memory(storage)

    # Dream environment with a dreamer worker config registered.
    dream_env = Environment(storage=storage)
    dream_env.config_registry.register(
        Config(
            name="dreamer",
            description="dream worker",
            system_template="You are the dream worker.",
            llm_model="test-model",
            tools=[
                "dreaming.save_learning:save_learning",
                "builtins.finish:finish",
            ],
        )
    )

    # The worker calls save_learning once, then finishes with plain text.
    scripted = ScriptedModel(
        [
            ModelResponse(
                role="assistant",
                content={
                    "content": LESSON,
                    "confidence": 0.9,
                    "source_artifact_ids": [],
                },
                tool_call="save_learning",
                tool_call_id="tc-1",
            ),
            ModelResponse(role="assistant", content="Consolidation complete."),
        ]
    )
    registry = Mock()
    registry.get_model.return_value = scripted
    registry.get_provider.return_value = None

    with patch(
        "gimle.hugin.llm.completion.get_model_registry",
        return_value=registry,
    ):
        results = run_dream(dream_env, config="researcher", max_steps=15)

    # A scoped learning was produced.
    assert len(results) == 1
    assert results[0]["scope_config"] == "researcher"

    # Re-rendering a researcher prompt that opts into {{ learnings }} now
    # contains the consolidated lesson.
    researcher = _make_researcher_agent(storage)
    rendered = PromptRenderer(researcher).render_prompt(
        "Lessons learned:\n{{ learnings }}", {}
    )
    assert LESSON in rendered

    # A prompt that does not reference learnings is unaffected.
    plain = PromptRenderer(researcher).render_prompt("No learnings here.", {})
    assert plain == "No learnings here."


def test_dry_run_persists_nothing():
    """A dry run produces a result but persists no Learning."""
    storage = MemoryStorage()
    _seed_episodic_memory(storage)

    dream_env = Environment(storage=storage)
    dream_env.config_registry.register(
        Config(
            name="dreamer",
            description="dream worker",
            system_template="You are the dream worker.",
            llm_model="test-model",
            tools=[
                "dreaming.save_learning:save_learning",
                "builtins.finish:finish",
            ],
        )
    )

    scripted = ScriptedModel(
        [
            ModelResponse(
                role="assistant",
                content={"content": LESSON, "confidence": 0.9},
                tool_call="save_learning",
                tool_call_id="tc-1",
            ),
            ModelResponse(role="assistant", content="done"),
        ]
    )
    registry = Mock()
    registry.get_model.return_value = scripted
    registry.get_provider.return_value = None

    with patch(
        "gimle.hugin.llm.completion.get_model_registry",
        return_value=registry,
    ):
        results = run_dream(
            dream_env, config="researcher", max_steps=15, dry_run=True
        )

    # The worker produced a learning, but nothing was persisted.
    assert len(results) == 1
    assert results[0]["dry_run"] is True
    learning_records = [
        storage.load_artifact_record(a) for a in storage.list_artifacts()
    ]
    assert not any(r["type"] == "Learning" for r in learning_records)
