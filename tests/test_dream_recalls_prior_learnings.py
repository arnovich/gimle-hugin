"""The dream worker is shown the learnings already in effect for its scope.

Without this it was asked the same open question ("find cross-cutting patterns")
over a near-identical corpus every night, holding an explicit licence to save
nothing — and it could not know that the answer was already on disk, because
``scan_provenance`` excludes Learning artifacts from the corpus. Two identical
runs minutes apart produced ten learnings and zero. Nothing asserted that the
worker knew what it had already saved, so nothing caught it.

The corpus exclusion stays (consolidating learnings into learnings compounds
drift). Prior learnings enter as CONTEXT instead, and the ask becomes a diff
against them.
"""

from typing import Any, Dict, List
from unittest.mock import Mock, patch

import gimle.hugin.tools  # noqa: F401  (registers dreaming.save_learning)
from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.text import Text
from gimle.hugin.dreaming.consolidate import (
    NO_PRIOR_LEARNINGS,
    _consolidate_prompt,
    _prior_learnings_block,
    run_dream,
)
from gimle.hugin.dreaming.selector import DEFAULT_BUDGET
from gimle.hugin.llm.models.model import Model, ModelResponse
from gimle.hugin.storage.local import LocalStorage

LESSON = "Always check for null dates before parsing."
EPISODIC = "When dates are null the parser returns nothing."


class _Scripted(Model):
    """Replay a fixed list of responses, recording every prompt it was sent."""

    def __init__(self, responses: List[ModelResponse]):
        """Store the scripted responses and an empty recording."""
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
        self.seen: List[str] = []

    def chat_completion(self, system_prompt, messages, tools=None):
        """Record the conversation, then return the next scripted response."""
        self.seen.append(str(system_prompt) + "\n" + str(messages))
        response = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        return response


def _save_then_stop() -> _Scripted:
    return _Scripted(
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


def _researcher_agent(storage: LocalStorage) -> Agent:
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


def _dream_env(base: str) -> Environment:
    env = Environment(storage=LocalStorage(base_path=base))
    env.config_registry.register(
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
    return env


def _seed_episodic(base: str) -> LocalStorage:
    """One episodic Text under config 'researcher', on disk."""
    storage = LocalStorage(base_path=base)
    agent = _researcher_agent(storage)
    task_def = agent.stack.interactions[0]
    task_def.add_artifact(Text(interaction=task_def, content=EPISODIC))
    storage.save_agent(agent)
    return storage


def _run_dream(env: Environment, model: _Scripted) -> List[Dict[str, Any]]:
    registry = Mock()
    registry.get_model.return_value = model
    registry.get_provider.return_value = None
    with patch(
        "gimle.hugin.llm.completion.get_model_registry",
        return_value=registry,
    ):
        return run_dream(env, config="researcher", max_steps=15)


def test_second_dream_sees_what_the_first_one_saved(tmp_path):
    """The regression: a repeat dream is shown the learning it already wrote.

    This is the whole bug. The first run saves LESSON; the second run must be
    told LESSON is in effect, or it re-answers "is there a pattern?" blind and
    either restates it or (as production did) saves nothing at all.
    """
    base = str(tmp_path / "storage")
    _seed_episodic(base)

    assert len(_run_dream(_dream_env(base), _save_then_stop())) == 1

    second = _save_then_stop()
    _run_dream(_dream_env(base), second)

    # The FIRST prompt only. Later turns contain the worker's own save_learning
    # argument, which is also LESSON — asserting over the whole conversation
    # passes even when nothing was recalled (it did, until this comment).
    opening = second.seen[0]
    assert LESSON in opening, "the worker was not shown the learning it saved"
    # The episodic memory is still the material it reasons over.
    assert EPISODIC in opening


def test_prior_learnings_are_not_folded_into_the_corpus(tmp_path):
    """Learnings stay OUT of the corpus — they are context, not material.

    Consolidating learnings into learnings compounds drift, so
    ``scan_provenance`` excludes them. Showing them must not smuggle them back
    in as episodic entries.
    """
    base = str(tmp_path / "storage")
    _seed_episodic(base)
    _run_dream(_dream_env(base), _save_then_stop())

    storage = LocalStorage(base_path=base)
    block = _prior_learnings_block(storage, "researcher")
    prompt = _consolidate_prompt("researcher", "EPISODIC-CORPUS-HERE", block)

    prior_at = prompt.index(block)
    corpus_at = prompt.index("EPISODIC-CORPUS-HERE")
    assert prior_at < corpus_at, "prior learnings must be labelled separately"
    assert "Episodic memories" in prompt


def test_no_prior_learnings_is_stated_not_blank(tmp_path):
    """A scope with nothing learned yet says so explicitly.

    A blank block reads as "the context failed to load"; the worker should be
    able to tell that apart from "nothing learned yet, write the first ones".
    """
    storage = LocalStorage(base_path=str(tmp_path / "storage"))
    assert _prior_learnings_block(storage, "researcher") == NO_PRIOR_LEARNINGS


def test_unreadable_store_warns_and_still_dreams(tmp_path, caplog):
    """A store that cannot be read must not kill the dream.

    It degrades to the old blind behaviour, which is survivable — but silently
    doing so is exactly the failure mode this fixes, so it WARNs.
    """
    storage = LocalStorage(base_path=str(tmp_path / "storage"))
    with patch(
        "gimle.hugin.dreaming.consolidate.select_learnings",
        side_effect=OSError("disk gone"),
    ):
        block = _prior_learnings_block(storage, "researcher")

    assert block == NO_PRIOR_LEARNINGS
    assert any(
        "could not load prior learnings" in record.getMessage()
        for record in caplog.records
    )


def test_dedup_sees_every_learning_not_the_render_time_top_n(tmp_path):
    """Judging "do I already know this?" needs ALL of them, not the injected 5.

    ``selector.DEFAULT_BUDGET`` caps how many learnings are INJECTED into a
    persona's prompt — a prompt-economy limit. Reusing it here made the worker
    blind to anything below the cut, and in production it restated a learning it
    had written itself thirteen minutes earlier: the original had dropped out of
    the top 5, and the duplicate then competed for the slot that hid it.
    """
    from gimle.hugin.artifacts.learning import Learning

    base = str(tmp_path / "storage")
    storage = _seed_episodic(base)
    task_def = _researcher_agent(storage).stack.interactions[0]
    for i in range(DEFAULT_BUDGET + 3):
        storage.save_artifact(
            Learning(
                interaction=task_def,
                content=f"lesson number {i}",
                scope_config="researcher",
            )
        )

    block = _prior_learnings_block(storage, "researcher")

    for i in range(DEFAULT_BUDGET + 3):
        assert (
            f"lesson number {i}" in block
        ), f"lesson {i} was hidden from dedup"


def test_task_scoped_dream_sees_task_learnings(tmp_path):
    """The worker must see ids it is allowed to supersede in its exact scope."""
    from gimle.hugin.artifacts.learning import Learning

    base = str(tmp_path / "storage")
    storage = _seed_episodic(base)
    task_def = _researcher_agent(storage).stack.interactions[0]
    task_learning = Learning(
        interaction=task_def,
        content="task-only lesson",
        scope_config="researcher",
        scope_task="analyze",
    )
    storage.save_artifact(task_learning)

    config_only = _prior_learnings_block(storage, "researcher")
    task_scope = _prior_learnings_block(
        storage, "researcher", task_name="analyze"
    )

    assert task_learning.id not in config_only
    assert task_learning.id in task_scope
    assert "scope: config=researcher, task=analyze" in task_scope


def test_dedup_omits_superseded_learning(tmp_path):
    """The dream compares against active knowledge, not retired audit records."""
    from gimle.hugin.artifacts.learning import Learning

    base = str(tmp_path / "storage")
    storage = _seed_episodic(base)
    task_def = _researcher_agent(storage).stack.interactions[0]
    old = Learning(
        interaction=task_def,
        content="old lesson",
        scope_config="researcher",
    )
    current = Learning(
        interaction=task_def,
        content="current lesson",
        scope_config="researcher",
        supersedes=[old.id],
    )
    storage.save_artifact(old)
    storage.save_artifact(current)

    block = _prior_learnings_block(storage, "researcher")
    assert old.id not in block
    assert current.id in block


def test_the_ask_is_a_diff_not_an_open_question():
    """The prompt asks what is MISSING, and licenses superseding.

    Guards the framing itself: reverting to "find cross-cutting patterns" over
    an unchanged corpus reinstates the nightly coin-flip.
    """
    prompt = _consolidate_prompt(
        "researcher", "corpus", "- [a1] a prior lesson"
    )
    assert "do NOT already say" in prompt
    assert "Do not restate" in prompt
    assert "overtaken" in prompt
    assert "supersedes" in prompt
    assert "same exact scope" in prompt
