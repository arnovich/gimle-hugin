"""Session module."""

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session_state import SessionState
from gimle.hugin.llm.router_outcome import report_outcome
from gimle.hugin.sandbox.background import BackgroundExecutor
from gimle.hugin.utils.uuid import with_uuid

if TYPE_CHECKING:
    from gimle.hugin.agent.task import Task
    from gimle.hugin.interaction.interaction import Interaction
    from gimle.hugin.sandbox.manager import SandboxManager
    from gimle.hugin.sandbox.sandbox import SandboxSpec
    from gimle.hugin.storage.storage import Storage

logger = logging.getLogger(__name__)


@with_uuid
class Session:
    """A session is a collection of agents and artifacts with shared state.

    Each session has its own SessionState instance that manages namespace-based
    shared state between agents.
    """

    def __init__(
        self,
        environment: Environment,
        agents: Optional[List["Agent"]] = None,
        state: Optional[SessionState] = None,
    ):
        """Initialize a session.

        Args:
            environment: The environment containing configs, tasks, etc.
            agents: Optional list of agents in this session
            state: Optional SessionState instance (creates new if not provided)
        """
        self.environment = environment
        self.agents = agents if agents else []
        self.state = state if state is not None else SessionState(session=self)
        # Update state's session reference if it was passed in without one
        if self.state._session is None:
            self.state._session = self
        # The session owns one sandbox per distinct SandboxSpec (the bash tool
        # creates them lazily on first use), so agents with different isolation
        # profiles get the backend their config asks for — not whichever the
        # first agent to run bash created. Keyed by spec; not serialized (a
        # resumed session recreates them).
        self.sandboxes: Dict["SandboxSpec", "SandboxManager"] = {}
        # Runs background bash commands off the scheduler thread so one long
        # command doesn't freeze sibling agents. Lazy (no threads until a command
        # actually backgrounds); in-memory, not serialized (like sandboxes).
        self.background = BackgroundExecutor()
        # A session may be stepped or ``run`` more than once (for example after
        # external input).  The router contract is one terminal outcome per
        # edition, so keep an in-process latch while still allowing a
        # non-terminal run to resume and report later.
        self._router_outcome_reported = False

    @property
    def id(self) -> str:
        """Get the uuid of the session.

        Returns:
            The uuid of the session.
        """
        if not hasattr(self, "uuid"):
            raise ValueError("Session uuid not set")
        return str(self.uuid)

    @id.setter
    def id(self, id: str) -> None:
        """Set the uuid of the session.

        Args:
            id: The uuid to set for the session.
        """
        self.uuid = id

    @property
    def storage(self) -> Optional["Storage"]:
        """Get the storage of the session.

        Returns:
            The storage of the session.
        """
        return self.environment.storage

    def add_agent(self, agent: "Agent") -> None:
        """Add an agent to the session.

        Args:
            agent: The agent to add to the session.
        """
        agent.session = self
        self.agents.append(agent)

    def create_agent_from_task(
        self, config: Config, task: "Task", caller: Optional["Agent"] = None
    ) -> "Agent":
        """Create an agent from a task.

        Args:
            config: The config to use for the agent.
            task: The task to create the agent from.
            caller: The agent that is calling this agent.

        Returns:
            The created agent.

        Raises:
            ValueError: If required task parameters are missing.
        """
        agent = Agent.create_from_task(self, config, task, caller)
        self.add_agent(agent)
        return agent

    def get_agent(self, uuid: str) -> Optional["Agent"]:
        """Get an agent from the session.

        Args:
            uuid: The uuid of the agent to get.

        Returns:
            The agent with the given uuid.
        """
        return next(
            (agent for agent in self.agents if agent.id == uuid),
            None,
        )

    def get_interaction(self, uuid: str) -> Optional["Interaction"]:
        """Get an interaction from the session.

        Args:
            uuid: The uuid of the interaction to get.

        Returns:
            The interaction with the given uuid.
        """
        return next(
            (
                interaction
                for agent in self.agents
                for interaction in agent.stack.interactions
                if interaction.id == uuid
            ),
            None,
        )

    def step(self) -> bool:
        """Step the session and report an outcome at a terminal boundary.

        Returns:
            True if there is any activity in the session, False otherwise.
        """
        try:
            any_activity = False
            for agent in self.agents:
                agent_activity = agent.step()
                if agent_activity:
                    any_activity = True
        except Exception:
            self.finalize_router_outcome(error=True)
            raise

        # ``Session.step`` is the public execution boundary used by the CLI,
        # TUI, and several apps. A false step may mean either terminal work or
        # a resumable wait, so let the branch-aware finalizer distinguish them.
        if not any_activity:
            self.finalize_router_outcome()
        return any_activity

    def run(
        self,
        max_steps: Optional[int] = None,
        step_callback: Optional[Callable[[int, "Agent"], None]] = None,
    ) -> int:
        """Run the session.

        Args:
            max_steps: The maximum number of steps to run.
            step_callback: Optional callback called after each agent step.
                Signature: (step_number: int, agent: Agent) -> None
                Called for each agent that had activity in a step.

        Returns:
            The number of steps run.
        """
        step_count = 0
        max_steps_reached = False
        logger.info(f"Running session {self.id}")
        try:
            while True:
                # Track which agents had activity
                active_agents: List[Agent] = []
                for agent in self.agents:
                    if agent.step():
                        active_agents.append(agent)

                if not active_agents:
                    break

                if self.storage:
                    self.storage.save_session(self)
                step_count += 1

                # Call the callback for each active agent
                if step_callback:
                    for agent in active_agents:
                        step_callback(step_count, agent)

                if max_steps and step_count >= max_steps:
                    logger.info(f"Max steps reached ({max_steps})")
                    max_steps_reached = True
                    break
                logger.info(f"Step {step_count} completed")
            if self.storage:
                self.storage.save_session(self)

            self.finalize_router_outcome(max_steps_reached=max_steps_reached)
            return step_count
        except Exception:
            self.finalize_router_outcome(error=True)
            raise

    @staticmethod
    def _task_has_pending_continuation(task: "Task") -> bool:
        """Return whether an unstepped task result still has work to chain."""
        if task.next_task is not None:
            return True
        if not task.task_sequence:
            return False

        chain_index = task.parameters.get("_chain_sequence_index")
        stored_index = (
            chain_index.get("value") if isinstance(chain_index, dict) else None
        )
        if isinstance(stored_index, int):
            next_index = stored_index + 1
        elif stored_index is not None:
            # Corrupt/foreign internal state must not turn observability into a
            # run failure. Conservatively assume the continuation is pending.
            return True
        else:
            try:
                next_index = task.task_sequence.index(task.name) + 1
            except ValueError:
                next_index = 0
        return next_index < len(task.task_sequence)

    def _terminal_success(self) -> Optional[bool]:
        """Return the completed root-task result, or ``None`` while waiting.

        Child agents and named branches are inputs to their root task and must
        not overwrite the edition's final result. With several independent root
        agents, the edition succeeds only when every root task is terminal and
        successful.
        """
        from gimle.hugin.interaction.task_chain import TaskChain
        from gimle.hugin.interaction.task_definition import TaskDefinition
        from gimle.hugin.interaction.task_result import TaskResult

        results: List[bool] = []
        for agent in self.agents:
            main_interactions = [
                interaction
                for interaction in agent.stack.interactions
                if interaction.branch is None
            ]
            root_definition = next(
                (
                    interaction
                    for interaction in main_interactions
                    if isinstance(interaction, TaskDefinition)
                ),
                None,
            )
            if root_definition is None or root_definition.caller_id is not None:
                continue

            result_index = next(
                (
                    index
                    for index in range(len(main_interactions) - 1, -1, -1)
                    if isinstance(main_interactions[index], TaskResult)
                ),
                None,
            )
            if result_index is None:
                return None
            task_result = main_interactions[result_index]
            if not isinstance(task_result, TaskResult):
                return None

            task_definition = next(
                (
                    interaction
                    for interaction in reversed(
                        main_interactions[:result_index]
                    )
                    if isinstance(interaction, TaskDefinition)
                ),
                None,
            )
            if task_definition is None:
                return None

            # A later chain/definition means this result belongs to an earlier
            # stage, not the current root-task boundary.
            if any(
                isinstance(interaction, (TaskChain, TaskDefinition))
                for interaction in main_interactions[result_index + 1 :]
            ):
                return None

            # An oracle may create a TaskResult and stop before stepping it. It
            # is terminal only if that step would not schedule another task.
            if (
                result_index == len(main_interactions) - 1
                and task_definition.task is not None
                and self._task_has_pending_continuation(task_definition.task)
            ):
                return None

            if task_result.finish_type is None:
                return None
            results.append(task_result.finish_type == "success")
        return all(results) if results else None

    def finalize_router_outcome(
        self,
        *,
        max_steps_reached: bool = False,
        error: bool = False,
    ) -> None:
        """Report an edition outcome when this execution boundary is final.

        This is shared by ``run`` and the step-based CLI/app runners. A
        resumable wait remains unreported; an unhandled error or exhausted
        step budget is a failure. Reporting remains idempotent for the lifetime
        of this ``Session`` instance.
        """
        if error:
            self._report_router_outcome(False)
            return

        terminal_success = self._terminal_success()
        if terminal_success is not None:
            self._report_router_outcome(terminal_success)
        elif max_steps_reached:
            self._report_router_outcome(False)

    def _report_router_outcome(self, success: bool) -> None:
        """Best-effort, once-per-session bridge to gimle-router."""
        if self._router_outcome_reported:
            return
        self._router_outcome_reported = True
        try:
            report_outcome(self.id, success=success)
        except Exception as error:  # observability must never break an edition
            logger.warning("gimle-router outcome reporting failed: %s", error)

    def close(self) -> None:
        """Release session-owned resources (background jobs, then sandboxes).

        Idempotent and safe on a session that never created a sandbox. Order is
        load-bearing: stopping a sandbox is what *interrupts* an in-flight
        background ``exec`` (a ``ThreadPoolExecutor`` cannot cancel a thread
        already blocked in a command), so tear the sandboxes down first — that
        kills the running commands — then join the now-unblocking workers. This
        is the in-process seam; because it is skipped on an abrupt exit
        (SIGKILL, laptop sleep), it complements — not replaces — the reaper.
        """
        for manager in self.sandboxes.values():
            manager.close()
        self.background.shutdown()
        # Emit the audit counters only *after* the workers are joined, so an
        # interrupted background command's teardown-time outcome (the very
        # failure the summary is meant to surface) is already recorded. Guarded:
        # observability must never break teardown (close's never-raise contract).
        for manager in self.sandboxes.values():
            try:
                manager.log_summary()
            except Exception as error:  # never let logging break close()
                logger.warning("sandbox audit summary failed: %s", error)
        self.sandboxes.clear()

    def __enter__(self) -> "Session":
        """Enter a context that guarantees ``close`` on exit."""
        return self

    def __exit__(self, *exc: Any) -> None:
        """Close the session when leaving the context."""
        self.close()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the session to a dictionary.

        Returns:
            The dictionary representation of the session.
        """
        result: Dict[str, Any] = {
            "agents": [agent.id for agent in self.agents],
            "state": self.state.to_dict(),
        }
        # Add uuid if present (added by @with_uuid, not a dataclass field)
        if not hasattr(self, "uuid"):
            raise ValueError("Session must have a uuid")
        result["uuid"] = self.id
        # Add created_at if present (added by @with_uuid)
        if hasattr(self, "created_at"):
            result["created_at"] = self.created_at
        return result

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], environment: "Environment"
    ) -> "Session":
        """Deserialize the session from a dictionary.

        Args:
            data: The dictionary to deserialize the session from.
            environment: The environment to use for the session.

        Returns:
            The deserialized session.
        """
        # Deserialize state if present
        state = None
        if "state" in data:
            state = SessionState.from_dict(data["state"])

        # Prepare kwargs for session creation
        session_kwargs: Dict[str, Any] = {
            "environment": environment,
            "state": state,
        }

        # Pass uuid to constructor if present (for @with_uuid)
        if "uuid" in data:
            session_kwargs["uuid"] = data["uuid"]

        # Pass created_at to constructor if present (for @with_uuid)
        if "created_at" in data:
            session_kwargs["created_at"] = data["created_at"]

        # Deserialize agents first (they need session reference)
        temp_session = cls(**session_kwargs)
        agents_data = data.get("agents", [])
        if not temp_session.storage:
            raise ValueError("Session has no storage")
        for agent_uuid in agents_data:
            agent = temp_session.storage.load_agent(
                agent_uuid, session=temp_session
            )
            temp_session.agents.append(agent)

        return temp_session
