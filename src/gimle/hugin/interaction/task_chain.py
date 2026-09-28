"""Task chain interaction module."""

import logging
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.utils.uuid import with_uuid

if TYPE_CHECKING:
    from gimle.hugin.artifacts.artifact import Artifact
    from gimle.hugin.interaction.stack import Stack

logger = logging.getLogger(__name__)


@Interaction.register()
@dataclass
@with_uuid
class TaskChain(Interaction):
    """Chains to the next task deterministically.

    This interaction is created when a TaskResult completes and the
    task has chaining configured (next_task or task_sequence).

    Attributes:
        next_task_name: Name of the next task to execute.
        task_sequence: Ordered list of tasks in the sequence.
        sequence_index: Current index in the task_sequence.
        previous_result: Result from the previous task.
        chain_config: Optional config name to use for the chained task.
    """

    next_task_name: Optional[str] = None
    task_sequence: Optional[List[str]] = None
    sequence_index: int = 0
    previous_result: Optional[Dict[str, Any]] = None
    chain_config: Optional[str] = None

    @classmethod
    def _from_dict(
        cls, data: Dict[str, Any], stack: "Stack", artifacts: List["Artifact"]
    ) -> "TaskChain":
        """Construct from dictionary.

        Args:
            data: The data to construct the task chain from.
            stack: The stack to use for the task chain.
            artifacts: The artifacts to use for the task chain.

        Returns:
            The constructed task chain.
        """
        uuid_value = data.pop("uuid", None)
        created_at_value = data.pop("created_at", None)

        kwargs: Dict[str, Any] = {
            "stack": stack,
            "branch": data.get("branch"),
            "next_task_name": data.get("next_task_name"),
            "task_sequence": data.get("task_sequence"),
            "sequence_index": data.get("sequence_index", 0),
            "previous_result": data.get("previous_result"),
            "chain_config": data.get("chain_config"),
        }
        if uuid_value is not None:
            kwargs["uuid"] = uuid_value
        if created_at_value is not None:
            kwargs["created_at"] = created_at_value

        instance = cls(**kwargs)
        instance.artifacts = artifacts
        return instance

    def step(self) -> bool:
        """Step to the next task in the chain.

        Determines the next task from either task_sequence or next_task_name,
        retrieves it from the registry, injects the previous result if
        configured, and creates a new TaskDefinition.

        Returns:
            True if the task chain interaction was successful, False otherwise.
        """
        # Determine next task name
        task_name: Optional[str] = None

        if self.task_sequence and self.sequence_index < len(self.task_sequence):
            task_name = self.task_sequence[self.sequence_index]
        elif self.next_task_name:
            task_name = self.next_task_name

        if not task_name:
            logger.debug("No more tasks in chain, stopping")
            return False

        current_task_def = self.stack.get_task_definition_interaction(
            branch=self.branch
        )
        if current_task_def is None:
            raise ValueError("No task definition found for TaskChain")
        current_task = current_task_def.task
        if current_task is None:
            raise ValueError("Task definition is not a task")

        # Get task template from registry
        task_registry = self.stack.agent.environment.task_registry
        if task_name not in task_registry.registered():
            raise ValueError(f"Task '{task_name}' not found in registry")

        task_template = task_registry.get(task_name)

        # Carry only declared inputs; defaults are fallbacks to live values.
        # Clone both sides so mutable inputs cannot change earlier stages or
        # the registry template. Result injection keeps its historical raw
        # mapping shape, even when the receiving schema says "string".
        chained_task = task_template.clone()
        inputs = {
            name: deepcopy(spec["value"])
            for name, spec in current_task.parameters.items()
            if name in chained_task.parameters
            and name != "_chain_sequence_index"
            and spec.get("value") is not None
        }
        if self.previous_result is not None and current_task.pass_result_as:
            param_name = current_task.pass_result_as
            inputs.pop(param_name, None)
            if param_name not in chained_task.parameters:
                chained_task.parameters[param_name] = {
                    "type": "object",
                    "description": "Result from previous task",
                    "required": False,
                }
            chained_task.parameters[param_name]["value"] = deepcopy(
                self.previous_result
            )

        # Validate before changing the config or appending a task definition.
        chained_task = chained_task.set_input_parameters(inputs)
        chained_task.task_sequence = deepcopy(self.task_sequence) or None
        chained_task.chain_config = (
            task_template.chain_config or self.chain_config
        )

        # Handle config switching if the NEXT task specifies a chain_config
        # Use the next task's chain_config, not the previous task's
        next_chain_config = task_template.chain_config
        if next_chain_config:
            config_registry = self.stack.agent.environment.config_registry
            if next_chain_config in config_registry.registered():
                new_config = config_registry.get(next_chain_config)
                self.stack.agent.config = new_config
                logger.debug(f"Switched to config: {next_chain_config}")
            else:
                logger.warning(
                    f"Config '{next_chain_config}' not found, keeping current"
                )

        # Store current sequence index for the next TaskResult
        # We use a custom attribute on the task to track position
        chained_task.parameters["_chain_sequence_index"] = {
            "type": "integer",
            "description": "Internal: task sequence index",
            "required": False,
            "default": 0,
            "value": self.sequence_index,
        }

        logger.debug(
            f"Chaining to task: {task_name} (index {self.sequence_index})"
        )

        # Create TaskDefinition for the chained task
        self.stack.add_interaction(
            TaskDefinition(
                stack=self.stack,
                branch=self.branch,
                task=chained_task,
                caller_id=None,  # Chained tasks don't have a caller
            )
        )

        return True
