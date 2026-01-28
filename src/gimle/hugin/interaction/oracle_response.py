"""Oracle response interaction module."""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.interaction.task_result import TaskResult
from gimle.hugin.interaction.tool_call import ToolCall
from gimle.hugin.utils.uuid import with_uuid


@Interaction.register()
@dataclass
@with_uuid
class OracleResponse(Interaction):
    """Oracle response interaction.

    Attributes:
        response: The response from the oracle.
    """

    response: Optional[Dict[str, Any]] = None

    @property
    def tool_call_id(self) -> Optional[str]:
        """Get the tool call id for the oracle response.

        Returns:
            The tool call id for the oracle response.
        """
        if self.response is None:
            raise ValueError("OracleResponse response is None")
        tool_name = self.response["tool_call"]
        tool = next(
            (tool for tool in self.stack.get_tools() if tool.name == tool_name),
            None,
        )
        if tool and tool.options.respond_with_text:
            return None
        return self.response.get("tool_call_id")

    def step(self) -> bool:
        """Step the oracle response interaction.

        Returns:
            True if the oracle response interaction was successful, False otherwise.
        """
        if self.response is None:
            raise ValueError("OracleResponse response is None")
        if self.response.get("tool_call") is not None:
            # Extract reason from args if present
            args = self.response["content"]
            reason = args.get("reason") if isinstance(args, dict) else None

            self.stack.add_interaction(
                ToolCall(
                    stack=self.stack,
                    branch=self.branch,
                    tool=self.response["tool_call"],
                    args=args,
                    tool_call_id=self.tool_call_id,
                    reason=reason,
                )
            )
        else:
            self.stack.add_interaction(
                TaskResult(
                    stack=self.stack,
                    branch=self.branch,
                    result=self.response["content"],
                    finish_type="success",
                )
            )
            return False
        return True
