"""Session boundaries report one correlated outcome to gimle-router."""

from unittest.mock import Mock, patch

import pytest

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.agent.task import Task
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.interaction.task_result import TaskResult
from gimle.hugin.interaction.waiting import Waiting


def _task() -> Task:
    return Task(name="root", description="test task", prompt="test")


def _agent(
    session: Session,
    *,
    caller_id: str | None = None,
    finish_type: str | None = None,
    waiting: bool = True,
) -> Agent:
    agent = Agent(
        session=session,
        config=Config(
            name="test-agent",
            description="test agent",
            system_template="test",
            tools=[],
        ),
    )
    agent.stack.add_interaction(
        TaskDefinition(
            stack=agent.stack,
            task=_task(),
            caller_id=caller_id,
        )
    )
    if finish_type is not None:
        agent.stack.add_interaction(
            TaskResult(
                stack=agent.stack,
                finish_type=finish_type,
                result={"finish_type": finish_type},
            )
        )
    if waiting:
        agent.stack.add_interaction(Waiting(stack=agent.stack))
    session.add_agent(agent)
    return agent


@pytest.mark.parametrize(
    ("finish_type", "success"),
    [("success", True), ("failure", False)],
)
def test_terminal_root_task_reports_once(finish_type, success):
    """A terminal root result is emitted exactly once with its status."""
    session = Session(environment=Environment())
    _agent(session, finish_type=finish_type)

    with patch("gimle.hugin.agent.session.report_outcome") as report:
        assert session.run() == 0
        session.run()

    report.assert_called_once_with(session.id, success=success)


def test_waiting_session_does_not_report_a_premature_failure():
    """A session waiting for more work has not reached an outcome boundary."""
    session = Session(environment=Environment())
    _agent(session)

    with patch("gimle.hugin.agent.session.report_outcome") as report:
        assert session.run() == 0

    report.assert_not_called()


def test_child_result_does_not_override_root_result():
    """Only the root task decides the edition-level outcome."""
    session = Session(environment=Environment())
    root = _agent(session, finish_type="success")
    _agent(session, caller_id=root.id, finish_type="failure")

    with patch("gimle.hugin.agent.session.report_outcome") as report:
        session.run()

    report.assert_called_once_with(session.id, success=True)


def test_max_steps_without_terminal_result_reports_failure():
    """Exhausting the caller's step budget is an explicit failed edition."""
    session = Session(environment=Environment())
    agent = Agent(
        session=session,
        config=Config(
            name="test-agent",
            description="test agent",
            system_template="test",
            tools=[],
        ),
    )
    interaction = Mock()
    interaction.step.return_value = True
    interaction.artifacts = []
    interaction.branch = None
    agent.stack.add_interaction(interaction)
    session.add_agent(agent)

    with patch("gimle.hugin.agent.session.report_outcome") as report:
        assert session.run(max_steps=1) == 1

    report.assert_called_once_with(session.id, success=False)


def test_terminal_result_wins_when_created_on_the_last_allowed_step():
    """A terminal result at the limit is not mislabeled as exhaustion."""
    session = Session(environment=Environment())
    _agent(session, finish_type="success", waiting=False)

    with patch("gimle.hugin.agent.session.report_outcome") as report:
        assert session.run(max_steps=1) == 1

    report.assert_called_once_with(session.id, success=True)


def test_session_exception_reports_failure_and_is_reraised():
    """Unhandled edition errors report failure without changing propagation."""
    session = Session(environment=Environment())
    agent = Agent(
        session=session,
        config=Config(
            name="test-agent",
            description="test agent",
            system_template="test",
            tools=[],
        ),
    )
    interaction = Mock()
    interaction.step.side_effect = RuntimeError("boom")
    interaction.artifacts = []
    interaction.branch = None
    agent.stack.add_interaction(interaction)
    session.add_agent(agent)

    with patch("gimle.hugin.agent.session.report_outcome") as report:
        with pytest.raises(RuntimeError, match="boom"):
            session.run()

    report.assert_called_once_with(session.id, success=False)


def test_reporting_failure_never_breaks_the_completed_session():
    """Unexpected reporter errors remain best-effort observability failures."""
    session = Session(environment=Environment())
    _agent(session, finish_type="success")

    with patch(
        "gimle.hugin.agent.session.report_outcome",
        side_effect=RuntimeError("router unavailable"),
    ):
        assert session.run() == 0
