"""Run an interactive session with pause controls and a shared model budget."""

import time
from typing import Callable, Optional

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.session import LLMCallLimitReached, Session
from gimle.hugin.cli.interactive.state import AgentController
from gimle.hugin.interaction.task_definition import TaskDefinition


def run_controlled_session(
    session: Session,
    controller: AgentController,
    save: Callable[[], None],
    max_llm_calls: int,
    max_iterations: int = 10000,
    get_controller: Optional[Callable[[str], AgentController]] = None,
) -> None:
    """Drive the selected agent and descendants while respecting their controls."""

    def eligible(agent: Agent) -> bool:
        """Exclude unrelated siblings and individually paused descendants."""
        if not _belongs_to_subtree(agent, controller.agent_id):
            return False
        return (
            agent.id == controller.agent_id
            or get_controller is None
            or get_controller(agent.id).should_continue()
        )

    with session.execution(), session.limit_llm_calls(max_llm_calls):
        iterations = 0
        try:
            while iterations < max_iterations:
                if not controller.should_continue():
                    time.sleep(0.1)
                    continue
                if not session.step(agent_filter=eligible):
                    break
                iterations += 1
                save()
                deadline = time.monotonic() + session.idle_delay
                while (
                    iterations < max_iterations
                    and deadline > time.monotonic()
                    and not controller.paused
                    and not controller.step_through
                ):
                    time.sleep(max(0.0, min(0.1, deadline - time.monotonic())))
            else:
                session.limit_reached = "iterations"
        except LLMCallLimitReached:
            pass
        finally:
            save()


def _belongs_to_subtree(agent: Agent, root_id: str) -> bool:
    """Follow initial task callers, retaining ancestry through chained stages."""
    seen = set()
    current: Optional[Agent] = agent
    while current is not None and current.id not in seen:
        if current.id == root_id:
            return True
        seen.add(current.id)
        first = next(
            (
                item
                for item in current.stack.interactions
                if isinstance(item, TaskDefinition)
            ),
            None,
        )
        current = (
            current.session.get_agent(first.caller_id)
            if first and first.caller_id
            else None
        )
    return False
