"""Integration test for the dreaming example (examples/dreaming).

Exercises the real example config/task/template and the real builtin dream
worker, with scripted models so it runs offline and deterministically:

    run (save_insight) -> dream (save_learning) -> re-render shows the learning
"""

import shutil
import tempfile
from pathlib import Path
from typing import List
from unittest.mock import Mock, patch

import pytest

import gimle.hugin.dreaming as dreaming_pkg
import gimle.hugin.tools  # noqa: F401  (registers dreaming.save_learning)
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.dreaming.consolidate import run_dream
from gimle.hugin.llm.models.model import Model, ModelResponse
from gimle.hugin.llm.prompt.renderer import PromptRenderer
from gimle.hugin.storage.local import LocalStorage

EXAMPLE_PATH = "examples/dreaming"
PREFERENCE = "prefers a window seat"


class _Scripted(Model):
    """Replay a fixed list of responses, repeating the last."""

    def __init__(self, responses: List[ModelResponse]):
        """Store the scripted responses."""
        super().__init__(
            {
                "model": "m",
                "temperature": 0,
                "max_tokens": 50,
                "tool_choice": {"type": "auto"},
            }
        )
        self._responses = responses
        self._index = 0

    def chat_completion(self, system_prompt, messages, tools=None):
        """Return the next scripted response."""
        response = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        return response


def _registry(model):
    registry = Mock()
    registry.get_model.return_value = model
    registry.get_provider.return_value = None
    return registry


@pytest.fixture
def storage_path():
    """Provide a temporary on-disk storage path, cleaned up after the test."""
    temp_dir = tempfile.mkdtemp(prefix="dreaming_example_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def _render_assistant_system(storage_base):
    """Render the example assistant's system prompt against the storage."""
    env = Environment.load(
        EXAMPLE_PATH, storage=LocalStorage(base_path=storage_base)
    )
    session = Session(environment=env)
    agent = session.create_agent_from_task(
        env.config_registry.get("assistant"),
        env.task_registry.get("assist"),
    )
    return PromptRenderer(agent).render_system_prompt()


def test_dreaming_example_closed_loop(storage_path):
    """The example's run -> dream -> re-render loop injects the learning."""
    # Cold: before any dream, the "what you've learned" section is empty.
    cold = _render_assistant_system(storage_path)
    assert PREFERENCE not in cold

    # Day 1: run the example assistant; it saves the preference as an insight.
    env = Environment.load(
        EXAMPLE_PATH, storage=LocalStorage(base_path=storage_path)
    )
    session = Session(environment=env)
    agent = session.create_agent_from_task(
        env.config_registry.get("assistant"),
        env.task_registry.get("assist"),
    )
    assistant_model = _Scripted(
        [
            ModelResponse(
                role="assistant",
                content={
                    "insight": "The traveler prefers a window seat.",
                    "format": "markdown",
                },
                tool_call="save_insight",
                tool_call_id="tc-insight",
            ),
            ModelResponse(role="assistant", content="All set — booked!"),
        ]
    )
    with patch(
        "gimle.hugin.llm.completion.get_model_registry",
        return_value=_registry(assistant_model),
    ):
        for _ in range(20):
            if not agent.step():
                break
    env.storage.save_session(session)
    assert env.storage.list_artifacts(), "the run saved no episodic insight"

    # Night: dream over the storage using the real builtin dream worker.
    dreamer_dir = str(Path(dreaming_pkg.__file__).resolve().parent / "agent")
    dream_env = Environment.load(
        dreamer_dir, storage=LocalStorage(base_path=storage_path)
    )
    dream_model = _Scripted(
        [
            ModelResponse(
                role="assistant",
                content={
                    "content": (
                        "The traveler prefers a window seat; book one by "
                        "default."
                    ),
                    "confidence": 0.9,
                    "source_artifact_ids": [],
                },
                tool_call="save_learning",
                tool_call_id="tc-learning",
            ),
            ModelResponse(role="assistant", content="Consolidation complete."),
        ]
    )
    with patch(
        "gimle.hugin.llm.completion.get_model_registry",
        return_value=_registry(dream_model),
    ):
        results = run_dream(dream_env, config="assistant", max_steps=15)
    assert len(results) == 1
    assert results[0]["scope_config"] == "assistant"

    # Day 2: the same assistant config now renders the learning into its prompt.
    warm = _render_assistant_system(storage_path)
    assert PREFERENCE in warm
