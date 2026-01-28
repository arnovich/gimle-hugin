"""Agent call interaction."""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from gimle.hugin.agent.config import Config
from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.interaction.waiting import Waiting
from gimle.hugin.utils.uuid import with_uuid

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Interaction.register()
@dataclass
@with_uuid
class AgentCall(Interaction):
    """An agent call interaction.

    Attributes:
        config: The config to use for the agent.
        task: The task to run.
        agent_id: The ID of the agent to call.
    """

    config: Optional[Config] = None
    task: Optional[Task] = None
    agent_id: Optional[str] = None

    @classmethod
    def _from_dict(
        cls, data: Dict[str, Any], stack: "Stack", artifacts: List["Artifact"]
    ) -> "AgentCall":
        """Construct from dictionary, handling AgentCall deserialization.

        Args:
            data: The data to construct the AgentCall from.
            stack: The stack to use for the AgentCall.
            artifacts: The artifacts to use for the AgentCall.

        Returns:
            The constructed AgentCall.
        """
        # Extract uuid and created_at if present (they're not dataclass fields, so pass to __init__)
        uuid_value = data.get("uuid", None)
        created_at_value = data.get("created_at", None)

        # Config is serialized as a dict, use Config.from_dict to reconstruct it
        config_data = data.get("config", {})
        config = Config.from_dict(config_data)

        # Task is serialized as a dict, use Task.from_dict to reconstruct it
        task_data = data.get("task", {})
        task = Task.from_dict(task_data)

        # Create instance, passing uuid and created_at to avoid generating new ones
        kwargs: Dict[str, Any] = {
            "stack": stack,
            "branch": data.get("branch"),
            "task": task,
            "config": config,
        }
        if uuid_value is not None:
            kwargs["uuid"] = uuid_value
        if created_at_value is not None:
            kwargs["created_at"] = created_at_value
        kwargs["agent_id"] = data.get("agent_id", None)

        instance = cls(**kwargs)
        instance.artifacts = artifacts

        return instance

    def step(self) -> bool:
        """Step the agent call interaction.

        Returns:
            True if the agent call interaction was successful, False otherwise.
        """
        logger.info(f"Launching child agent with originator_id={self.id}")

        parent_agent = self.stack.agent
        if self.config is None:
            raise ValueError("Config is required")
        if self.task is None:
            raise ValueError("Task is required")

        # Check if we should reuse an existing agent
        if self.agent_id is not None:
            # Reuse existing agent - add new task to its stack
            child_agent = parent_agent.session.get_agent(self.agent_id)
            if child_agent is None:
                raise ValueError(f"Agent {self.agent_id} not found")
            child_agent.stack.add_interaction(
                TaskDefinition.create_from_task(
                    self.task, child_agent.stack, self.stack.agent
                )
            )
        else:
            # Create new agent
            child_agent = parent_agent.session.create_agent_from_task(
                config=self.config, task=self.task, caller=self.stack.agent
            )
            self.agent_id = child_agent.id

        self.stack.add_interaction(
            Waiting(stack=self.stack, branch=self.branch)
        )
        return True
