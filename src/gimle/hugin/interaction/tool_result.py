"""Tool result interaction."""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.utils.uuid import with_uuid

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from gimle.hugin.interaction.tool_call import ToolCall
    from gimle.hugin.tools.tool import ToolResponse


@Interaction.register()
@dataclass
@with_uuid
class ToolResult(Interaction):
    """A tool result interaction.

    Attributes:
        result: The result data from the tool.
        tool_call_id: ID from the oracle's tool call (None for deterministic).
        tool_name: Name of the tool that was called.
        is_error: Whether the tool call resulted in an error.
        response_interaction: Override the default interaction to create next.
        next_tool: Name of tool to call next (deterministic chaining).
        next_tool_args: Arguments for the next tool call.
        include_in_context: Whether this result appears in LLM context.
    """

    result: Optional[Dict[str, Any]] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    is_error: Optional[bool] = None
    response_interaction: Optional[Union[str, Interaction]] = None
    # Deterministic tool chaining
    next_tool: Optional[str] = None
    next_tool_args: Optional[Dict[str, Any]] = None
    include_in_context: bool = True

    @staticmethod
    def create_from_tool_response(
        caller: "ToolCall", tool_response: "ToolResponse"
    ) -> "ToolResult":
        """Create a tool result interaction from a tool response.

        Args:
            caller: The tool call that called the tool.
            tool_response: The tool response from the tool.

        Returns:
            The created tool result interaction.
        """
        return ToolResult(
            stack=caller.stack,
            branch=caller.branch,
            result=tool_response.content,
            tool_call_id=caller.tool_call_id,
            tool_name=caller.tool,
            is_error=tool_response.is_error,
            response_interaction=tool_response.response_interaction,
            # Pass through deterministic chaining fields
            next_tool=tool_response.next_tool,
            next_tool_args=tool_response.next_tool_args,
            include_in_context=tool_response.include_in_context,
        )

    def step(self) -> bool:
        """Step the tool result interaction.

        If next_tool is set, creates a deterministic ToolCall instead of
        returning to the oracle. Otherwise, follows the normal flow.

        Returns:
            True if the tool result interaction was successful, False otherwise.
        """
        if self.result is None:
            raise ValueError("ToolResult result is None")

        # Check for deterministic tool chaining
        if self.next_tool:
            from gimle.hugin.interaction.tool_call import ToolCall

            logger.debug(
                f"Deterministic chain: {self.tool_name} -> {self.next_tool}"
            )
            self.stack.add_interaction(
                ToolCall(
                    stack=self.stack,
                    branch=self.branch,
                    tool=self.next_tool,
                    args=self.next_tool_args or {},
                    # tool_call_id=None,
                    tool_call_id=self.tool_call_id,
                )
            )
            return True

        # Normal flow: return to oracle or custom interaction
        response_interaction = self.response_interaction

        # If response_interaction is already an Interaction instance, add it
        if isinstance(response_interaction, Interaction):
            self.stack.add_interaction(response_interaction)
            return True

        # Otherwise, treat as string name and create via factory method
        if response_interaction is None:
            response_interaction = "AskOracle"
        interaction_type = Interaction.get_interaction(response_interaction)
        tool_result_creation = getattr(
            interaction_type, "create_from_tool_result", None
        )
        if tool_result_creation is None:
            raise ValueError(
                f"Interaction type {response_interaction} does not have a create_from_tool_result method"
            )
        self.stack.add_interaction(tool_result_creation(tool_result=self))
        return True
