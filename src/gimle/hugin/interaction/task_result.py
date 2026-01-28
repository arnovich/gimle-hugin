"""Task result interaction module."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.interaction.tool_result import ToolResult
from gimle.hugin.interaction.waiting import Waiting
from gimle.hugin.utils.uuid import with_uuid

logger = logging.getLogger(__name__)


@Interaction.register()
@dataclass
@with_uuid
class TaskResult(Interaction):
    """A task result is the result of a task.

    Attributes:
        finish_type: The type of finish for the task.
        result: The result of the task.
    """

    finish_type: Optional[Literal["success", "failure"]] = None
    result: Optional[Dict[str, Any]] = None

    @staticmethod
    def create_from_tool_result(tool_result: ToolResult) -> "TaskResult":
        """Create a task result interaction from a tool result.

        Args:
            tool_result: The tool result to create the task result from.

        Returns:
            The created task result interaction.
        """
        return TaskResult(
            stack=tool_result.stack,
            branch=tool_result.branch,
            finish_type=(
                tool_result.result["finish_type"]
                if tool_result.result
                else None
            ),
            result=tool_result.result,
        )

    def step(self) -> bool:
        """Step the task result interaction.

        Checks for task chaining (next_task or task_sequence) and creates
        a TaskChain interaction if configured. Otherwise, notifies the
        caller agent or stops execution.

        Returns:
            True if the task result interaction was successful, False otherwise.
        """
        # Import here to avoid circular import
        from gimle.hugin.interaction.agent_result import AgentResult
        from gimle.hugin.interaction.task_chain import TaskChain

        task_def = self.stack.get_task_definition_interaction()
        if task_def is None:
            raise ValueError("No task definition found for TaskResult")

        # Check for task chaining
        if task_def.task:
            task = task_def.task
            has_next = task.next_task is not None
            has_sequence = task.task_sequence is not None

            if has_next or has_sequence:
                # Determine sequence index for task_sequence
                sequence_index = 0
                if has_sequence and task.task_sequence:
                    # Check if we stored the index from a previous chain
                    chain_idx_param = task.parameters.get(
                        "_chain_sequence_index"
                    )
                    stored_index = (
                        chain_idx_param.get("value")
                        if chain_idx_param is not None
                        else None
                    )
                    if stored_index is not None:
                        sequence_index = stored_index + 1
                    else:
                        # Find current task in sequence, next one is index+1
                        try:
                            current_idx = task.task_sequence.index(task.name)
                            sequence_index = current_idx + 1
                        except ValueError:
                            # Current task not in sequence, start from 0
                            sequence_index = 0

                    # Check if we've exhausted the sequence
                    if sequence_index >= len(task.task_sequence):
                        logger.debug(
                            f"Task sequence complete at index {sequence_index}"
                        )
                        # Fall through to normal completion
                    else:
                        logger.debug(
                            f"Task chaining to sequence[{sequence_index}]"
                        )
                        self.stack.add_interaction(
                            TaskChain(
                                stack=self.stack,
                                branch=self.branch,
                                next_task_name=None,
                                task_sequence=task.task_sequence,
                                sequence_index=sequence_index,
                                previous_result=self.result,
                                chain_config=task.chain_config,
                            )
                        )
                        return True
                elif has_next:
                    logger.debug(f"Task chaining to: {task.next_task}")
                    self.stack.add_interaction(
                        TaskChain(
                            stack=self.stack,
                            branch=self.branch,
                            next_task_name=task.next_task,
                            task_sequence=None,
                            sequence_index=0,
                            previous_result=self.result,
                            chain_config=task.chain_config,
                        )
                    )
                    return True

        # No chaining - check for caller agent
        if task_def.caller:
            task_def.caller.stack.add_interaction(
                AgentResult(
                    stack=task_def.caller.stack,
                    branch=self.branch,
                    task_result_id=self.id,  # Pass the TaskResult interaction ID
                )
            )

        self.stack.add_interaction(
            Waiting(stack=self.stack, branch=self.branch)
        )
        return True
