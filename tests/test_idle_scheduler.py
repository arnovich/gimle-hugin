"""Exercise real waits and cost limits independently of scheduler iterations."""

import time
from typing import Any
from unittest.mock import Mock

import pytest

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.interaction.conditions import Condition
from gimle.hugin.interaction.waiting import Waiting

from .memory_storage import MemoryStorage


def test_real_wait_is_quiet_and_finishes() -> None:
    """A two-second deadline needs one sleep, not thousands of storage writes."""
    storage = MemoryStorage()
    session = Session(environment=Environment(storage=storage))
    agent = Agent(
        session,
        Config(name="waiter", description="Wait", system_template="Wait"),
    )
    session.add_agent(agent)
    waiting = Waiting(
        stack=agent.stack,
        condition=Condition("wait_for_seconds", {"seconds": 2}),
    )
    agent.stack.add_interaction(waiting)
    writes = Mock(wraps=storage._save_interaction)
    storage._save_interaction = writes
    started = time.monotonic()

    assert session.run(max_llm_calls=1, max_iterations=5) < 5

    assert time.monotonic() - started >= 2
    assert session.llm_calls == 0
    assert waiting.completed
    assert writes.call_count <= 2
    storage.save_session(session)
    assert writes.call_count <= 2


def test_unchanged_records_skip_writes_but_nested_changes_persist() -> None:
    """Snapshot comparison must detect mutation inside previously saved objects."""
    storage = MemoryStorage()
    session = Session(environment=Environment(storage=storage))
    agent = Agent(
        session,
        Config(name="waiter", description="Wait", system_template="Wait"),
    )
    session.add_agent(agent)
    waiting = Waiting(
        stack=agent.stack, next_tool_args={"nested": {"value": 1}}
    )
    agent.stack.add_interaction(waiting)
    storage.save_session(session)
    writes = Mock(wraps=storage._save_interaction)
    storage._save_interaction = writes

    storage.save_session(session)
    assert writes.call_count == 0
    waiting.next_tool_args["nested"]["value"] = 2
    storage.save_session(session)
    assert writes.call_count == 1
    storage.delete_interaction(waiting)
    storage.save_interaction(waiting)
    assert writes.call_count == 2


def test_failed_record_write_can_be_retried() -> None:
    """Only successfully persisted snapshots may suppress another write."""
    storage = MemoryStorage()
    session = Session(environment=Environment(storage=storage))
    original = storage._save_session
    storage._save_session = Mock(side_effect=OSError("disk unavailable"))
    with pytest.raises(OSError, match="disk unavailable"):
        storage.save_session(session)
    storage._save_session = Mock(wraps=original)
    storage.save_session(session)
    assert storage._save_session.call_count == 1


def test_nearest_deadline_and_long_wait_do_not_exhaust_call_budget(
    scheduler_clock: Any,
) -> None:
    """Two-minute waits exceed the old default 100 cap but use no model calls."""
    storage = MemoryStorage()
    session = Session(environment=Environment(storage=storage))
    for seconds in (120, 180):
        agent = Agent(
            session,
            Config(
                name=str(seconds), description="Wait", system_template="Wait"
            ),
        )
        session.add_agent(agent)
        agent.stack.add_interaction(
            Waiting(
                stack=agent.stack,
                condition=Condition("wait_for_seconds", {"seconds": seconds}),
            )
        )
    writes = Mock(wraps=storage._save_session)
    storage._save_session = writes
    assert session.run(max_steps=100) == 2
    assert scheduler_clock.sleeps == [120, 60]
    assert session.llm_calls == 0
    assert session.limit_reached is None
    assert writes.call_count <= 3


def test_one_call_budget_allows_deterministic_completion(
    budget_session,
) -> None:
    """Finish processing a model result even if that call used the last credit."""
    from gimle.hugin.agent.task import Task
    from gimle.hugin.interaction.task_result import TaskResult

    run = budget_session
    agent = run.session.create_agent_from_task(
        run.config, Task(name="one", description="One", prompt="Finish")
    )
    assert run.session.run(max_steps=1) > 1
    assert run.session.llm_calls == 1
    assert run.session.limit_reached is None
    assert any(
        isinstance(item, TaskResult) for item in agent.stack.interactions
    )


@pytest.mark.parametrize("same_agent", [False, True])
def test_call_budget_cannot_overshoot_and_resumes(
    budget_session: Any, same_agent: bool
) -> None:
    """The cap applies before each model call, including multiple live branches."""
    from gimle.hugin.agent.task import Task
    from gimle.hugin.interaction.task_definition import TaskDefinition

    run = budget_session
    first = run.session.create_agent_from_task(
        run.config, Task(name="first", description="First", prompt="Finish")
    )
    second = Task(name="second", description="Second", prompt="Finish")
    if same_agent:
        first.stack.add_interaction(
            TaskDefinition(stack=first.stack, branch="side", task=second)
        )
    else:
        run.session.create_agent_from_task(run.config, second)
    run.session.run(max_llm_calls=1)
    assert run.session.llm_calls == 1
    assert run.model._i == 1
    assert run.session.limit_reached == "llm_calls"
    from gimle.hugin.interaction.task_result import TaskResult

    assert any(
        isinstance(item, TaskResult) for item in first.stack.interactions
    )
    assert all(not agent.stack._step_lock for agent in run.session.agents)
    run.session.run(max_llm_calls=1)
    assert run.session.llm_calls == 2
    assert run.model._i == 2
    assert run.session.limit_reached is None


def test_provider_failure_counts_attempt_and_unlocks(
    budget_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed provider invocations still consume budget and permit a later retry."""
    from gimle.hugin.agent.task import Task

    run = budget_session
    agent = run.session.create_agent_from_task(
        run.config, Task(name="one", description="One", prompt="Finish")
    )
    monkeypatch.setattr(
        run.model,
        "chat_completion",
        Mock(side_effect=RuntimeError("provider failed")),
    )
    with pytest.raises(RuntimeError, match="provider failed"):
        run.session.run(max_llm_calls=1)
    assert run.session.llm_calls == 1
    assert not agent.stack._step_lock


def test_custom_wait_polls_without_rewriting_storage(
    scheduler_clock: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A parked 120-second custom condition performs zero writes on unchanged passes."""
    session = Session(environment=Environment(storage=MemoryStorage()))
    agent = Agent(
        session, Config(name="wait", description="Wait", system_template="Wait")
    )
    session.add_agent(agent)
    deadline = scheduler_clock.now + 120
    evaluate = Mock(
        side_effect=lambda *args, **kwargs: scheduler_clock.now < deadline
    )
    monkeypatch.setitem(Condition.registry._items, "custom_deadline", evaluate)
    agent.stack.add_interaction(
        Waiting(stack=agent.stack, condition=Condition("custom_deadline"))
    )
    storage = session.storage
    writes = Mock(wraps=storage._save_interaction)
    storage._save_interaction = writes
    assert session.run(max_steps=100) == 120
    assert evaluate.call_count == 121
    assert scheduler_clock.sleeps == [1.0] * 120
    assert writes.call_count == 2
    assert session.llm_calls == 0
    assert session.limit_reached is None


def test_idle_tick_mutations_are_saved(scheduler_clock: Any) -> None:
    """A condition's real state changes still persist even when its stack is idle."""
    storage = MemoryStorage()
    session = Session(environment=Environment(storage=storage))
    agent = Agent(
        session,
        Config(name="ticks", description="Ticks", system_template="Wait"),
    )
    session.add_agent(agent)
    agent.stack.add_interaction(
        Waiting(
            stack=agent.stack,
            condition=Condition("wait_for_ticks", {"ticks": 3}),
        )
    )
    writes = Mock(wraps=storage._save_session)
    storage._save_session = writes
    session.run(max_llm_calls=0)
    assert writes.call_count == 3
    assert session.llm_calls == 0


def test_background_wait_uses_bounded_idle_polling(
    budget_session: Any, scheduler_clock: Any
) -> None:
    """A background job lasting two minutes must not spend the iteration guard."""
    from gimle.hugin.agent.task import Task
    from gimle.hugin.interaction.bash_waiting import BashWaiting

    run = budget_session
    agent = run.session.create_agent_from_task(
        run.config,
        Task(name="background", description="Background", prompt="Finish"),
    )
    deadline = scheduler_clock.now + 120
    run.session.background.is_done = Mock(
        side_effect=lambda job: scheduler_clock.now >= deadline
    )
    run.session.background.collect = Mock(
        return_value=({"stdout": "done"}, False)
    )
    agent.stack.add_interaction(BashWaiting(stack=agent.stack, job_id="job"))
    assert run.session.run(max_llm_calls=1, max_iterations=130) < 130
    assert scheduler_clock.sleeps == [1.0] * 120
    assert run.session.llm_calls == 1
    assert run.session.limit_reached is None


def test_dataframe_snapshot_matches_local_storage(tmp_path: Any) -> None:
    """Unchanged pandas inputs compare safely; changed cells persist again."""
    import pandas as pd

    from gimle.hugin.interaction.ask_oracle import AskOracle
    from gimle.hugin.storage.local import LocalStorage

    storage = LocalStorage(base_path=str(tmp_path))
    session = Session(environment=Environment(storage=storage))
    agent = Agent(
        session,
        Config(name="table", description="Table", system_template="Table"),
    )
    frame = pd.DataFrame({"a": [1, 2]})
    interaction = AskOracle(stack=agent.stack, template_inputs={"table": frame})
    save = Mock(wraps=storage._save_interaction)
    storage._save_interaction = save
    storage.save_interaction(interaction)
    storage.save_interaction(interaction)
    assert save.call_count == 1
    frame.loc[0, "a"] = 99
    storage.save_interaction(interaction)
    assert save.call_count == 2
    assert "99" in (tmp_path / "interactions" / interaction.id).read_text()
