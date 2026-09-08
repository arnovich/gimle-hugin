"""End-to-end dreaming loop: run -> dream -> re-render shows the learning."""

from pathlib import Path
from typing import List
from unittest.mock import Mock, patch

import pytest

import gimle.hugin.dreaming as dreaming_pkg
import gimle.hugin.tools  # noqa: F401  (registers dreaming.save_learning)
from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.text import Text
from gimle.hugin.dreaming.consolidate import DREAM_SCOPE_RESULTS_KEY, run_dream
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
        self.offered_tools = []
        self.system_prompts = []

    def chat_completion(self, system_prompt, messages, tools=None):
        """Return the next scripted response, repeating the last."""
        self.offered_tools.append({tool.name for tool in tools or []})
        self.system_prompts.append(system_prompt)
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


def _default_dream_env(storage):
    """Load the worker configuration used by production callers."""
    return Environment.load(
        str(Path(dreaming_pkg.__file__).parent / "agent"), storage=storage
    )


def test_run_dream_then_reinjects_learning():
    """Run -> dream -> re-render shows the consolidated learning."""
    storage = MemoryStorage()
    _seed_episodic_memory(storage)

    dream_env = _default_dream_env(storage)

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
    assert all(
        tools == {"save_learning", "finish"} for tools in scripted.offered_tools
    )
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

    dream_env = _default_dream_env(storage)

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


def test_step_budget_exhaustion_is_visible(caplog):
    """Stopping before a proposed learning executes is not convergence."""
    storage = MemoryStorage()
    _seed_episodic_memory(storage)
    scripted = ScriptedModel(
        [
            ModelResponse(
                role="assistant",
                content={"content": LESSON},
                tool_call="save_learning",
                tool_call_id="tc-budget",
            )
        ]
    )
    registry = Mock()
    registry.get_model.return_value = scripted
    registry.get_provider.return_value = None
    with patch(
        "gimle.hugin.llm.completion.get_model_registry", return_value=registry
    ):
        results = run_dream(
            _default_dream_env(storage), config="researcher", max_steps=2
        )
    assert results == []
    assert scripted._index == 0
    assert "exhausted its 2 interaction-step budget" in caplog.text
    assert "not evidence of convergence" in caplog.text


def test_finish_on_last_budgeted_step_is_not_exhaustion(caplog):
    """A completed abstention at the budget boundary must stay quiet."""
    storage = MemoryStorage()
    _seed_episodic_memory(storage)
    scripted = ScriptedModel(
        [
            ModelResponse(
                role="assistant",
                content={"finish_type": "success", "result": "No new evidence"},
                tool_call="finish",
                tool_call_id="tc-finish",
            )
        ]
    )
    registry = Mock()
    registry.get_model.return_value = scripted
    registry.get_provider.return_value = None
    with patch(
        "gimle.hugin.llm.completion.get_model_registry", return_value=registry
    ):
        results = run_dream(
            _default_dream_env(storage), config="researcher", max_steps=6
        )
    assert results == []
    assert scripted._index == 1
    assert "exhausted" not in caplog.text


@pytest.mark.parametrize("finish_type", ["success", "failure"])
def test_reserves_closing_turn_after_three_saves(finish_type, caplog):
    """The production 20-step budget fits three saves and an honest finish."""
    storage = MemoryStorage()
    _seed_episodic_memory(storage)
    env = _default_dream_env(storage)
    scripted = ScriptedModel(
        [
            ModelResponse(
                role="assistant",
                content={"content": f"Lesson {index}"},
                tool_call="save_learning",
                tool_call_id=f"save-{index}",
            )
            for index in range(3)
        ]
        + [
            ModelResponse(
                role="assistant",
                content={"finish_type": finish_type, "result": "Review status"},
                tool_call="finish",
                tool_call_id="finish",
            )
        ]
    )
    registry = Mock()
    registry.get_model.return_value = scripted
    with patch(
        "gimle.hugin.llm.completion.get_model_registry", return_value=registry
    ):
        results = run_dream(env, config="researcher")
    assert len(results) == 3
    assert scripted._index == 4
    assert "at most 3 more save_learning" in scripted.system_prompts[0]
    assert "at most 1 more save_learning" in scripted.system_prompts[2]
    assert "CLOSING TURN" in scripted.system_prompts[3]
    assert env.env_vars[DREAM_SCOPE_RESULTS_KEY] == [
        {
            "config": "researcher",
            "status": "completed" if finish_type == "success" else "incomplete",
            "steps": 18,
        }
    ]
    assert ("not evidence of convergence" in caplog.text) == (
        finish_type == "failure"
    )


@pytest.mark.parametrize("dry_run", [False, True])
def test_ignoring_closing_turn_cannot_save_more_or_claim_completion(
    dry_run, caplog
):
    """A model repeating saves is stopped before its fourth write, within 20 steps."""
    storage = MemoryStorage()
    _seed_episodic_memory(storage)
    env = _default_dream_env(storage)
    scripted = ScriptedModel(
        [
            ModelResponse(
                role="assistant",
                content={"content": LESSON},
                tool_call="save_learning",
                tool_call_id="save",
            )
        ]
    )
    registry = Mock()
    registry.get_model.return_value = scripted
    with patch(
        "gimle.hugin.llm.completion.get_model_registry", return_value=registry
    ):
        results = run_dream(env, config="researcher", dry_run=dry_run)
    assert len(results) == 3
    assert scripted._index == 4
    assert env.env_vars[DREAM_SCOPE_RESULTS_KEY] == [
        {
            "config": "researcher",
            "status": "budget_exhausted",
            "steps": 15,
        }
    ]
    assert "not evidence of convergence" in caplog.text
    stored = [storage.load_artifact_record(a) for a in storage.list_artifacts()]
    assert sum(r["type"] == "Learning" for r in stored) == (0 if dry_run else 3)


@pytest.mark.parametrize("max_steps", [0, 1, 2, 5])
def test_tiny_budget_never_starts_an_unfinishable_model_call(max_steps):
    """Insufficient budgets are visible without spending a provider call."""
    storage = MemoryStorage()
    _seed_episodic_memory(storage)
    env = _default_dream_env(storage)
    with patch("gimle.hugin.llm.completion.get_model_registry") as registry:
        assert run_dream(env, config="researcher", max_steps=max_steps) == []
    registry.assert_not_called()
    report = env.env_vars[DREAM_SCOPE_RESULTS_KEY][0]
    assert report["status"] == "budget_exhausted"
    assert report["steps"] <= max_steps
