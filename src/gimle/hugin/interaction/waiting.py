"""Waiting interaction."""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from gimle.hugin.interaction.conditions import Condition
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.utils.uuid import with_uuid

if TYPE_CHECKING:
    from gimle.hugin.artifacts.artifact import Artifact
    from gimle.hugin.interaction.stack import Stack

logger = logging.getLogger(__name__)


@Interaction.register()
@dataclass
@with_uuid
class Waiting(Interaction):
    """A waiting interaction that can optionally wait for a condition.

    Attributes:
        condition: The condition to wait for.
        next_tool: The tool to chain to if the condition is satisfied.
        next_tool_args: The arguments to pass to the next tool.

    When condition is not set, this is a terminal state (branch complete),
    unless the previous interaction is an AgentCall — in that case, the
    branch stays alive while the child agent runs.
    When condition is set, step() will:
    - Evaluate the condition
    - If condition returns True: continue waiting (return True to keep stepping)
    - If condition returns False: chain to next_tool (return True)
    """

    condition: Optional[Condition] = None
    next_tool: Optional[str] = None
    next_tool_args: Dict[str, Any] = field(default_factory=dict)

    def step(self) -> bool:
        """Step the waiting interaction.

        Returns:
            False if no condition (terminal state) or done waiting with no next tool.
            True if still waiting (condition True) or chaining to next tool.
        """
        # No condition - check if waiting for a child agent
        if not self.condition:
            from gimle.hugin.interaction.agent_call import AgentCall

            # Find the previous interaction on the same branch
            prev = None
            for interaction in reversed(self.stack.interactions):
                if (
                    interaction.branch == self.branch
                    and interaction is not self
                ):
                    prev = interaction
                    break

            if isinstance(prev, AgentCall):
                # Keep alive while child agent runs
                return True

            return False

        # Load and check the condition
        still_waiting = self.condition.evaluate(self.stack, self.branch)

        if still_waiting:
            logger.debug(
                f"Condition {self.condition.evaluator} returned True, waiting"
            )
            return True

        # Condition satisfied - chain to next tool if specified
        if self.next_tool:
            from gimle.hugin.interaction.tool_call import ToolCall

            logger.debug(
                f"Condition satisfied, chaining to tool: {self.next_tool}"
            )
            self.stack.add_interaction(
                ToolCall(
                    stack=self.stack,
                    branch=self.branch,
                    tool=self.next_tool,
                    args=self.next_tool_args,
                    tool_call_id=None,  # Deterministic chain
                )
            )
            return True

        # No next tool - just done waiting
        return False

    @classmethod
    def _from_dict(
        cls, data: Dict[str, Any], stack: "Stack", artifacts: List["Artifact"]
    ) -> "Waiting":
        """Construct from dictionary.

        Args:
            data: The data to construct the waiting from.
            stack: The stack to use for the waiting.
            artifacts: The artifacts to use for the waiting.

        Returns:
            The constructed waiting.
        """
        uuid_value = data.pop("uuid", None)
        created_at_value = data.pop("created_at", None)

        condition_data = data.get("condition")
        kwargs: Dict[str, Any] = {
            "stack": stack,
            "branch": data.get("branch"),
            "condition": (
                Condition.from_dict(condition_data) if condition_data else None
            ),
            "next_tool": data.get("next_tool"),
            "next_tool_args": data.get("next_tool_args", {}),
        }
        if uuid_value is not None:
            kwargs["uuid"] = uuid_value
        if created_at_value is not None:
            kwargs["created_at"] = created_at_value

        instance = cls(**kwargs)
        instance.artifacts = artifacts

        return instance
