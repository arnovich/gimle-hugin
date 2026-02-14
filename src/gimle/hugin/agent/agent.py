"""Agent module."""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from gimle.hugin.agent.config import Config
from gimle.hugin.agent.config_state_machine import ConfigStateMachine
from gimle.hugin.agent.environment import Environment
from gimle.hugin.interaction.stack import Stack
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.utils.uuid import with_uuid

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from gimle.hugin.agent.session import Session
    from gimle.hugin.agent.task import Task
    from gimle.hugin.storage.storage import Storage


@with_uuid
class Agent:
    """An agent is a collection of interactions.

    Supports optional config state machine for dynamic configuration
    transitions based on rules during execution.
    """

    def __init__(
        self, session: "Session", config: Config, stack: Optional[Stack] = None
    ):
        """Initialize an agent.

        Args:
            session: The session to create the agent in.
            config: The config to use for the agent.
            stack: The stack to use for the agent.

        """
        self.stack = stack if stack else Stack(agent=self)
        self.session = session
        self.config = config

        # State machine tracking
        self._current_state: Optional[str] = None
        self._state_machine: Optional[ConfigStateMachine] = None
        self._config_history: List[Dict[str, Any]] = []

        # Initialize state machine if configured
        if config.state_machine:
            self._state_machine = config.state_machine
            initial = config.state_machine.initial_state
            # Load the initial state config (_transition_to sets
            # _current_state; old_state=None skips history append)
            self._transition_to(initial)
            # Record initial state (before stack has interactions)
            self._record_config_history(initial, None)

    @staticmethod
    def create_from_task(
        session: "Session",
        config: Config,
        task: "Task",
        caller: Optional["Agent"] = None,
    ) -> "Agent":
        """Create an agent from a task.

        Args:
            session: The session to create the agent in.
            config: The config to use for the agent.
            task: The task to create the agent from.
            caller: The agent that is calling this agent.

        Returns:
            The created agent.
        """
        agent = Agent(session=session, config=config)
        agent.stack.add_interaction(
            TaskDefinition.create_from_task(task, agent.stack, caller)
        )
        return agent

    @property
    def environment(self) -> Environment:
        """Get the environment of the agent.

        Returns:
            The environment of the agent.
        """
        return self.session.environment

    @property
    def id(self) -> str:
        """Get the uuid of the agent.

        Returns:
            The uuid of the agent.
        """
        if not hasattr(self, "uuid"):
            raise ValueError("Agent uuid not set")
        return str(self.uuid)

    @id.setter
    def id(self, id: str) -> None:
        """Set the uuid of the agent.

        Args:
            id: The uuid to set for the agent.
        """
        self.uuid = id

    @property
    def current_state(self) -> Optional[str]:
        """Get the current config state name."""
        return self._current_state

    @property
    def config_history(self) -> List[Dict[str, Any]]:
        """Get the config state transition history."""
        return [dict(entry) for entry in self._config_history]

    def step(self) -> bool:
        """Step the agent.

        Increments step count, executes the stack step, tracks tool calls,
        and checks for state machine transitions.

        Returns:
            True if the agent stepped, False otherwise.
        """
        logger.debug(f"Stepping agent {self.id}")

        result = self.stack.step()

        # Check for state machine transitions after step
        if self._state_machine:
            next_state = self._check_transitions()
            if next_state:
                self._transition_to(next_state)

        return result

    def rewind_to(self, index: int) -> int:
        """Rewind the agent's stack to a specific interaction index.

        Removes all interactions after the given index and deletes them from
        storage. Also trims config history entries that reference removed
        interactions and restores the current state accordingly.

        Args:
            index: The index to rewind to (0-based). Interactions at this
                   index and before are kept.

        Returns:
            Number of interactions removed.

        Raises:
            ValueError: If index is out of bounds.
        """
        storage = self.session.environment.storage
        removed = self.stack.rewind_to(index, storage=storage)

        # Trim config history entries referencing removed interactions
        if removed and self._config_history:
            removed_ids = {str(r.uuid) for r in removed}
            self._config_history = [
                entry
                for entry in self._config_history
                if entry["interaction_id"] is None
                or entry["interaction_id"] not in removed_ids
            ]
            # Restore current state to last history entry
            if self._config_history:
                last_state = self._config_history[-1]["state"]
                if last_state != self._current_state:
                    # Load the config for the restored state
                    # without recording a new history entry
                    registry = self.environment.config_registry
                    if last_state in registry.registered():
                        sm = self._state_machine
                        self.config = registry.get(last_state)
                        self._current_state = last_state
                        if self._state_machine is None:
                            self._state_machine = sm

        logger.info(
            f"Agent {self.id} rewound to interaction {index}, "
            f"removed {len(removed)} interactions"
        )

        return len(removed)

    def _check_transitions(self) -> Optional[str]:
        """Check if any transition should fire.

        Evaluates transitions in priority order and returns the target
        state if a transition matches, None otherwise.

        Returns:
            The next state if a transition matches, None otherwise.
        """
        if not self._state_machine:
            return None

        for transition in self._state_machine.get_transitions_by_priority():
            # Check from_state matches
            if (
                transition.from_state != "*"
                and transition.from_state != self._current_state
            ):
                continue

            # Check trigger
            if self._trigger_matches(transition.trigger):
                logger.debug(
                    f"Transition '{transition.name}' triggered: "
                    f"{self._current_state} -> {transition.to_state}"
                )
                return transition.to_state

        return None

    def _trigger_matches(self, trigger: Any) -> bool:
        """Check if a trigger condition is satisfied.

        Args:
            trigger: The trigger to check.

        Returns:
            True if the trigger matches, False otherwise.
        """
        from gimle.hugin.agent.config_state_machine import TransitionTrigger

        if not isinstance(trigger, TransitionTrigger):
            return False

        if trigger.type == "tool_call":
            # Check for a completed tool result, not just a tool call,
            # so the transition fires after the tool executes, not before.
            last_result = self.stack.get_last_tool_result_interaction(
                tool_name=trigger.tool_name
            )
            if last_result is None:
                return False
            # Ensure this result is the most recent tool result
            any_result = self.stack.get_last_tool_result_interaction()
            return any_result is not None and any_result.id == last_result.id
        elif trigger.type == "step_count":
            return (
                trigger.min_steps is not None
                and self.stack.ninteractions() >= trigger.min_steps
            )
        else:  # trigger.type == "state_pattern"
            return self._pattern_matches(trigger.pattern)

    def _pattern_matches(self, pattern: Optional[Dict[str, Any]]) -> bool:
        """Check if shared state matches a pattern.

        Supports simple equality checks and comparison operators:
        - {"key": "value"} - exact match
        - {"key": {"$gte": 3}} - greater than or equal
        - {"key": {"$gt": 3}} - greater than
        - {"key": {"$lte": 3}} - less than or equal
        - {"key": {"$lt": 3}} - less than
        - {"key": {"$ne": "value"}} - not equal

        Args:
            pattern: The pattern to check.

        Returns:
            True if the pattern matches, False otherwise.
        """
        if not pattern:
            return False

        try:
            for key, expected in pattern.items():
                actual = self.stack.get_shared_state(key)

                if isinstance(expected, dict):
                    # Handle comparison operators
                    for op, value in expected.items():
                        if op == "$gte" and not (actual >= value):
                            return False
                        elif op == "$gt" and not (actual > value):
                            return False
                        elif op == "$lte" and not (actual <= value):
                            return False
                        elif op == "$lt" and not (actual < value):
                            return False
                        elif op == "$ne" and not (actual != value):
                            return False
                else:
                    # Simple equality check
                    if actual != expected:
                        return False

            return True
        except Exception as e:
            logger.warning(f"Error matching pattern: {e}")
            return False

    def _record_config_history(
        self,
        state: str,
        interaction_id: Optional[str],
    ) -> None:
        """Append a config history entry.

        Args:
            state: The config state name.
            interaction_id: UUID of the triggering interaction,
                or None for the initial state.
        """
        self._config_history.append(
            {
                "state": state,
                "interaction_id": interaction_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def _transition_to(self, state_name: str) -> None:
        """Transition to a new config state.

        Loads the new config from the registry and updates the agent.

        Args:
            state_name: The name of the state to transition to.
        """
        config_registry = self.environment.config_registry
        if state_name not in config_registry.registered():
            logger.error(f"Config state '{state_name}' not found in registry")
            return

        new_config = config_registry.get(state_name)
        old_state = self._current_state

        # Update config (preserve state machine reference)
        state_machine = self._state_machine
        self.config = new_config
        self._current_state = state_name

        # Restore state machine if the new config doesn't have one
        if self._state_machine is None:
            self._state_machine = state_machine

        # Record transition in history (skip initial setup)
        if old_state is not None:
            interaction_id = None
            if self.stack.interactions:
                interaction_id = str(self.stack.interactions[-1].uuid)
            self._record_config_history(state_name, interaction_id)

        agent_id = self.uuid if hasattr(self, "uuid") else "initializing"
        logger.info(
            f"Agent {agent_id} transitioned: {old_state} -> {state_name}"
        )

    def message_agent(self, message: str) -> None:
        """Message the agent.

        Args:
            message: The message to send to the agent.
        """
        logger.info(f"Message received by {self.id}: {message}")
        self.stack.insert_external_input(message)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the agent to a dictionary.

        Returns:
            The dictionary representation of the agent.
        """
        result: Dict[str, Any] = {
            "config": self.config.to_dict(),
            "stack": self.stack.to_dict(),
        }
        # Add uuid if present (added by @with_uuid, not a dataclass field)
        if not hasattr(self, "uuid"):
            raise ValueError("Agent must have a uuid")
        result["uuid"] = self.id
        # Add created_at if present (added by @with_uuid)
        if hasattr(self, "created_at"):
            result["created_at"] = self.created_at

        # Serialize state machine tracking
        result["_current_state"] = self._current_state
        result["_config_history"] = self._config_history
        if self._state_machine:
            result["_state_machine"] = self._state_machine.to_dict()

        return result

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], storage: "Storage", session: "Session"
    ) -> "Agent":
        """Deserialize the agent from a dictionary.

        Args:
            data: The dictionary to deserialize the agent from.
            storage: The storage to use for the agent.
            session: The session to use for the agent.

        Returns:
            The deserialized agent.
        """
        config_data = data.get("config", {})
        config = Config.from_dict(config_data)

        # Prepare kwargs for agent creation, including uuid and created_at for @with_uuid
        agent_kwargs: Dict[str, Any] = {
            "session": session,
            "config": config,
            "stack": None,
        }
        if "uuid" in data:
            agent_kwargs["uuid"] = data["uuid"]
        if "created_at" in data:
            agent_kwargs["created_at"] = data["created_at"]

        # Create agent
        agent = cls(**agent_kwargs)

        # Restore state machine tracking
        agent._current_state = data.get("_current_state")
        agent._config_history = data.get("_config_history", [])
        if "_state_machine" in data:
            agent._state_machine = ConfigStateMachine.from_dict(
                data["_state_machine"]
            )

        # Deserialize stack (needs agent reference)
        stack_data = data.get("stack", {})
        agent.stack = Stack.from_dict(stack_data, agent=agent, storage=storage)

        return agent
