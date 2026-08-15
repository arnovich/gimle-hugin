"""Tool call interaction."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from gimle.hugin.interaction.agent_call import AgentCall
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.interaction.tool_result import (
    ToolResult,
    snapshot_tool_context_policy,
)
from gimle.hugin.tools.tool import Tool, ToolResponse
from gimle.hugin.utils.uuid import with_uuid

logger = logging.getLogger(__name__)


@Interaction.register()
@dataclass
@with_uuid
class ToolCall(Interaction):
    """A tool call interaction.

    Attributes:
        tool: The tool to call.
        args: The arguments to pass to the tool.
        tool_call_id: The ID of the tool call.
        reason: The reason for the tool call.
        tool_context_policy: Context options captured before execution.
    """

    tool: Optional[str] = None
    args: Optional[Dict[str, Any]] = None
    tool_call_id: Optional[str] = None
    reason: Optional[str] = None
    tool_context_policy: Optional[Dict[str, Any]] = None

    def step(self) -> bool:
        """Step the tool call interaction.

        Returns:
            True if the tool call interaction was successful, False otherwise.
        """
        tool = None
        try:
            tools = self.stack.get_tools(branch=self.branch)
            tool = next(
                (tool for tool in tools if tool.name == self.tool), None
            )
            if tool is None:
                raise ValueError(f"Tool {self.tool} not found")
            # Results may complete asynchronously (AgentCall, BashWaiting).
            # Capture the policy on the originating call before execution so
            # later registry loads cannot change how its history is rendered.
            self.tool_context_policy = snapshot_tool_context_policy(tool)
            result = Tool.execute_tool(
                tool, stack=self.stack, branch=self.branch, **(self.args or {})
            )
        except TypeError as e:
            logger.error(f"Error executing tool: {e}")
            result = ToolResponse(is_error=True, content={"error": str(e)})

        if isinstance(result, AgentCall):
            self.stack.add_interaction(result, branch=self.branch)
        else:
            if not isinstance(result, ToolResponse):
                raise ValueError(
                    f"Tool {self.tool} returned unexpected result: {result}"
                )
            if not self.tool:
                raise ValueError("Tool is required")
            self.stack.add_interaction(
                ToolResult.create_from_tool_response(self, result, tool=tool)
            )

        return True
