"""Ask user builtin tool."""

import logging
from typing import TYPE_CHECKING, Optional

from gimle.hugin.interaction.ask_human import AskHuman
from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

logger = logging.getLogger(__name__)


@Tool.register(
    name="builtins.ask_user",
    description="""Ask the user a question and wait for their response.

Use this tool when you need input, clarification, or a decision from the user.
The user's response will be returned to you so you can continue your task.

This tool requires the agent to have interactive: true in its config.
""",
    parameters={
        "question": {
            "type": "string",
            "description": "The question to ask the user",
            "required": True,
        },
        "context": {
            "type": "string",
            "description": "Optional context or background information to help "
            "the user understand the question",
            "required": False,
        },
    },
    is_interactive=True,
)
def ask_user(
    stack: "Stack",
    question: str,
    context: Optional[str] = None,
) -> ToolResponse:
    """
    Ask the user a question and wait for their response.

    Args:
        stack: The agent stack (auto-injected)
        question: The question to ask
        context: Optional context for the question

    Returns:
        ToolResponse with AskHuman interaction
    """
    try:
        # Build the prompt for the user
        if context:
            full_question = f"{context}\n\n{question}"
        else:
            full_question = question

        # Create the AskHuman interaction
        ask_human = AskHuman(
            stack=stack,
            question=full_question,
        )

        return ToolResponse(
            is_error=False,
            content={"message": "Waiting for user response..."},
            response_interaction=ask_human,
        )

    except Exception as e:
        logger.error(f"Error creating ask_user interaction: {e}")
        return ToolResponse(
            is_error=True,
            content={"error": f"Failed to ask user: {str(e)}"},
        )
