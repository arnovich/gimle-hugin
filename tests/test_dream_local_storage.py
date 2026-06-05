"""End-to-end dreaming loop against real on-disk LocalStorage.

The other dream tests use in-memory MemoryStorage. This one exercises the disk
path: JSON serialization of Learning artifacts + feedback, the raw
``load_artifact_record`` reader against real files, and cross-handle
persistence (a fresh LocalStorage handle reads what the dream wrote).
"""

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
from gimle.hugin.storage.local import LocalStorage

LESSON = "Always check for null dates before parsing."


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


def _researcher_agent(storage):
    session = Session(environment=Environment(storage=storage))
    return Agent.create_from_task(
        session,
        Config(
            name="researcher",
            description="d",
            system_template="system",
            llm_model="m",
        ),
        Task(
            name="analyze", description="", parameters={}, prompt="p", tools=[]
        ),
    )


def test_dream_loop_on_local_storage(tmp_path):
    """Run -> dream -> re-render works through real on-disk LocalStorage."""
    base = str(tmp_path / "storage")

    # Seed a real episodic insight on disk under config 'researcher'.
    storage = LocalStorage(base_path=base)
    agent = _researcher_agent(storage)
    task_def = agent.stack.interactions[0]
    task_def.add_artifact(
        Text(
            interaction=task_def,
            content="When dates are null the parser returns nothing.",
        )
    )
    storage.save_agent(agent)

    # The raw-record reader works against real JSON files on disk.
    (artifact_id,) = storage.list_artifacts()
    assert storage.load_artifact_record(artifact_id)["type"] == "Text"

    # Dream over the on-disk storage with a scripted worker model.
    dream_env = Environment(storage=LocalStorage(base_path=base))
    dream_env.config_registry.register(
        Config(
            name="dreamer",
            description="d",
            system_template="You are the dream worker.",
            llm_model="m",
            tools=[
                "dreaming.save_learning:save_learning",
                "builtins.finish:finish",
            ],
        )
    )
    scripted = _Scripted(
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
            ModelResponse(role="assistant", content="done."),
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
    assert len(results) == 1

    # A fresh storage handle (no in-memory carryover) reads the Learning back
    # from disk and a new agent injects it into a {{ learnings }} prompt.
    fresh = LocalStorage(base_path=base)
    learnings = [
        record
        for a in fresh.list_artifacts()
        for record in [fresh.load_artifact_record(a)]
        if record["type"] == "Learning"
    ]
    assert len(learnings) == 1
    assert learnings[0]["data"]["scope_config"] == "researcher"

    rendered = PromptRenderer(_researcher_agent(fresh)).render_prompt(
        "Lessons:\n{{ learnings }}", {}
    )
    assert LESSON in rendered
