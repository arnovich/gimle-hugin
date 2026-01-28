"""Session module."""

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.config import Config
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session_state import SessionState
from gimle.hugin.utils.uuid import with_uuid

if TYPE_CHECKING:
    from gimle.hugin.agent.task import Task
    from gimle.hugin.interaction.interaction import Interaction
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
        """Step the session.

        Returns:
            True if there is any activity in the session, False otherwise.
        """
        any_activity = False
        for agent in self.agents:
            agent_activity = agent.step()
            if agent_activity:
                any_activity = True
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
        logger.info(f"Running session {self.id}")
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
                break
            logger.info(f"Step {step_count} completed")
        if self.storage:
            self.storage.save_session(self)
        return step_count

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
