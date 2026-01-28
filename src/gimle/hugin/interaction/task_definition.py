"""Task definition interaction module."""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from gimle.hugin.agent.task import Task
from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.utils.uuid import with_uuid

if TYPE_CHECKING:
    from gimle.hugin.agent.agent import Agent
    from gimle.hugin.artifacts.artifact import Artifact
    from gimle.hugin.interaction.stack import Stack

logger = logging.getLogger(__name__)


@Interaction.register()
@dataclass
@with_uuid
class TaskDefinition(Interaction):
    """Task definition interaction.

    Attributes:
        task: The task to execute.
        caller_id: The ID of the caller.
    """

    task: Optional[Task] = None
    caller_id: Optional[str] = None

    @property
    def caller(self) -> Optional["Agent"]:
        """Get the caller of the task definition.

        Returns:
            The caller of the task definition.
        """
        if self.caller_id is not None:
            return self.stack.agent.session.get_agent(self.caller_id)
        return None

    @classmethod
    def create_from_task(
        cls, task: Task, stack: "Stack", caller: Optional["Agent"] = None
    ) -> "TaskDefinition":
        """Create a task definition from a task.

        Args:
            task: The task to create the task definition from.
            stack: The stack to use for the task definition.
            caller: The caller of the task definition.

        Returns:
            The created task definition.
        """
        return cls(
            stack=stack, task=task, caller_id=caller.id if caller else None
        )

    @classmethod
    def _from_dict(
        cls, data: Dict[str, Any], stack: "Stack", artifacts: List["Artifact"]
    ) -> "TaskDefinition":
        """Construct from dictionary, handling Task deserialization.

        Args:
            data: The data to construct the task definition from.
            stack: The stack to use for the task definition.
            artifacts: The artifacts to use for the task definition.

        Returns:
            The constructed task definition.
        """
        # Extract uuid and created_at if present (they're not dataclass fields, so pass to __init__)
        uuid_value = data.pop("uuid", None)
        created_at_value = data.pop("created_at", None)

        # Task is serialized as a dict, use Task.from_dict to reconstruct it
        task_data = data.get("task", {})
        task = Task.from_dict(task_data)

        caller_id = data.get("caller_id", None)

        # Create instance, passing uuid and created_at to avoid generating new ones
        kwargs: Dict[str, Any] = {
            "stack": stack,
            "branch": data.get("branch"),
            "task": task,
            "caller_id": caller_id,
        }
        if uuid_value is not None:
            kwargs["uuid"] = uuid_value
        if created_at_value is not None:
            kwargs["created_at"] = created_at_value

        instance = cls(**kwargs)
        instance.artifacts = artifacts

        return instance

    def step(self) -> bool:
        """Step the task definition interaction.

        Returns:
            True if the task definition interaction was successful, False otherwise.
        """
        logger.debug(f"Stepping task definition {self.id}")
        self.stack.add_interaction(
            AskOracle.create_from_task_definition(task_definition=self)
        )
        return True
