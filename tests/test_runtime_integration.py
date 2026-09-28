"""Cross-task verification for parked durable inboxes and cost budgets."""

from typing import Any

from gimle.hugin.agent.environment import Environment
from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.conditions import Condition
from gimle.hugin.interaction.waiting import Waiting
from gimle.hugin.storage.local import LocalStorage


def test_wait_inbox_budget_and_disk_resume(
    external_input_run: Any, scheduler_clock: Any
) -> None:
    """Preserve a parked inbox across an exhausted run and fresh disk resume."""
    run = external_input_run
    run.stack.add_interaction(
        Waiting(
            stack=run.stack,
            condition=Condition("wait_for_seconds", {"seconds": 120}),
        )
    )
    for value in ("first", "second", "third"):
        run.agent.message_agent(value, source="integration")
    run.session.run(max_llm_calls=0)
    assert scheduler_clock.sleeps == [120]
    assert run.session.llm_calls == 0
    assert run.session.limit_reached == "llm_calls"
    assert isinstance(run.stack.interactions[-1], AskOracle)
    assert (
        len(run.stack.queued_interactions)
        + len(run.stack.interactions[-1].external_inputs)
        == 3
    )
    fresh = LocalStorage(base_path=str(run.storage.base_path))
    resumed = fresh.load_session(run.session.id, Environment(storage=fresh))
    try:
        resumed.run(max_llm_calls=1)
        assert resumed.limit_reached is None
        assert len(run.calls) == 1
        content = str(run.calls[0]["messages"])
        for value in ("first", "second", "third"):
            assert value in content
        assert not resumed.agents[0].stack.queued_interactions
    finally:
        resumed.close()
