"""Agent result interaction."""

import logging
from dataclasses import dataclass
from typing import Optional

from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.interaction.task_result import TaskResult
from gimle.hugin.llm.prompt.prompt import Prompt
from gimle.hugin.utils.uuid import with_uuid

logger = logging.getLogger(__name__)


@Interaction.register()
@dataclass
@with_uuid
class AgentResult(Interaction):
    """An agent call interaction.

    Attributes:
        task_result_id: The ID of the task result to use for the agent result.
    """

    task_result_id: Optional[str] = None

    def step(self) -> bool:
        """Step the agent result interaction.

        Returns:
            True if the agent result interaction was successful, False otherwise.
        """
        logger.info("Adding result interaction from child agent")
        if self.task_result_id is None:
            raise ValueError("Task result id is required")

        # Get the TaskResult interaction directly by ID
        task_result_interaction = self.stack.agent.session.get_interaction(
            self.task_result_id
        )
        if task_result_interaction is None:
            raise ValueError(f"TaskResult {self.task_result_id} not found")

        if not isinstance(task_result_interaction, TaskResult):
            raise ValueError(
                f"Interaction {self.task_result_id} is not a TaskResult"
            )

        tool_call_interaction = self.stack.get_last_tool_call_interaction()
        if tool_call_interaction is None:
            raise ValueError("ToolCall interaction not found")

        prompt = Prompt(
            type="tool_result",
            tool_name=tool_call_interaction.tool,
            tool_use_id=tool_call_interaction.tool_call_id,
        )

        self.stack.add_interaction(
            AskOracle(
                stack=self.stack,
                branch=self.branch,
                prompt=prompt,
                template_inputs=task_result_interaction.result or {},
            )
        )

        return True
