"""Verify the TUI's session driver without a terminal or live provider."""

from types import SimpleNamespace
from typing import Any

import pytest

from gimle.hugin.agent.task import Task
from gimle.hugin.cli import create_agent
from gimle.hugin.cli.interactive import runner
from gimle.hugin.cli.interactive.state import AgentController
from gimle.hugin.interaction.task_result import TaskResult


def test_controlled_builder_runs_child_at_exact_call_limit(
    builder_cli_run: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same TUI runner advances the generated child and honors one shared cap."""
    run = builder_cli_run

    def drive(**kwargs: Any) -> tuple[int, None]:
        """Drive the real builder session through the TUI's control loop."""
        session = kwargs["session"]
        run.session = session
        runner.run_controlled_session(
            session,
            AgentController(session.agents[0].id),
            kwargs["save_fn"],
            max_llm_calls=kwargs["max_llm_calls"],
        )
        return session.llm_calls, None

    monkeypatch.setattr(create_agent, "run_steps_with_spinner", drive)
    assert create_agent.main(run.args + ["--max-llm-calls", "9"]) == 0
    assert run.session.llm_calls == 9
    assert run.session.limit_reached is None
    assert len(run.session.agents) == 2
    assert all(
        any(isinstance(item, TaskResult) for item in agent.stack.interactions)
        for agent in run.session.agents
    )


def test_controlled_pause_and_single_step_preserve_budget(
    budget_session: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Paused time and single-step control do not consume model-call credits."""
    run = budget_session
    agent = run.session.create_agent_from_task(
        run.config, Task(name="one", description="One", prompt="Finish")
    )
    controller = AgentController(agent.id)
    controller.pause()
    controller.toggle_step_through()
    pauses = []

    def release_one_step(seconds: float) -> None:
        """Act like a user resuming and advancing exactly one scheduler pass."""
        assert seconds == 0.1
        pauses.append(run.session.llm_calls)
        controller.resume()
        controller.request_step()

    monkeypatch.setattr(
        runner,
        "time",
        SimpleNamespace(sleep=release_one_step, monotonic=lambda: 0),
    )
    runner.run_controlled_session(
        run.session,
        controller,
        lambda: run.session.storage.save_session(run.session),
        1,
    )
    assert pauses[0] == 0
    assert len(pauses) > 1
    assert run.session.llm_calls == 1
    assert run.session.limit_reached is None


def test_controlled_runner_leaves_unselected_sibling_parked(
    budget_session: Any,
) -> None:
    """Resuming one root must not execute another root, even when it is paused."""
    run = budget_session
    first = run.session.create_agent_from_task(
        run.config, Task(name="first", description="First", prompt="Finish")
    )
    sibling = run.session.create_agent_from_task(
        run.config, Task(name="sibling", description="Sibling", prompt="Finish")
    )
    controllers = {
        agent.id: AgentController(agent.id) for agent in run.session.agents
    }
    controllers[sibling.id].pause()
    runner.run_controlled_session(
        run.session,
        controllers[first.id],
        lambda: None,
        2,
        get_controller=controllers.__getitem__,
    )
    assert run.session.llm_calls == 1
    assert len(sibling.stack.interactions) == 1
    assert controllers[sibling.id].paused


def test_second_runner_cannot_replace_active_budget(
    budget_session: Any,
) -> None:
    """Concurrent resume attempts cannot drive or reset the owner's session."""
    from gimle.hugin.agent.session import SessionBusyError

    run = budget_session
    agent = run.session.create_agent_from_task(
        run.config, Task(name="one", description="One", prompt="Finish")
    )
    with run.session.execution(), run.session.limit_llm_calls(1):
        with pytest.raises(SessionBusyError, match="active runner"):
            runner.run_controlled_session(
                run.session, AgentController(agent.id), lambda: None, 999
            )
        run.session.record_llm_call()
        assert not run.session.can_call_model
        assert len(agent.stack.interactions) == 1
    assert run.session.llm_calls == 1


def test_controlled_runner_respects_paused_descendant(
    budget_session: Any,
) -> None:
    """A root's runner must honor a child's individual pause and later resume."""
    run = budget_session
    parent = run.session.create_agent_from_task(
        run.config, Task(name="parent", description="Parent", prompt="Finish")
    )
    child = run.session.create_agent_from_task(
        run.config,
        Task(name="child", description="Child", prompt="Finish"),
        caller=parent,
    )
    controllers = {
        agent.id: AgentController(agent.id) for agent in run.session.agents
    }
    controllers[child.id].pause()
    runner.run_controlled_session(
        run.session,
        controllers[parent.id],
        lambda: None,
        1,
        get_controller=controllers.__getitem__,
    )
    assert len(child.stack.interactions) == 1
    assert run.session.llm_calls == 1
    controllers[child.id].resume()
    runner.run_controlled_session(
        run.session,
        controllers[parent.id],
        lambda: None,
        1,
        get_controller=controllers.__getitem__,
    )
    assert any(
        isinstance(item, TaskResult) for item in child.stack.interactions
    )
    assert run.session.llm_calls == 2
