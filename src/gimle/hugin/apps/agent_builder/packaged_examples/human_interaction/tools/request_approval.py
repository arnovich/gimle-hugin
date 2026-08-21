"""Human approval tool for the human_interaction example."""

from typing import TYPE_CHECKING

from gimle.hugin.interaction.ask_human import AskHuman
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def request_approval(
    stack: "Stack", action: str, reason: str, considerations: str
) -> ToolResponse:
    """Request approval from a human for a proposed action.

    This creates an AskHuman interaction that pauses execution until
    the human provides a response.

    Args:
        action: The action you want to take
        reason: Why this action is needed
        considerations: Risks or important factors to consider

    Returns:
        ToolResponse that creates AskHuman interaction
    """
    question = f"""APPROVAL REQUEST

Action: {action}

Reason: {reason}

Considerations: {considerations}

Do you approve this action? (yes/no)
If you have feedback or conditions, please provide them."""

    ask_human = AskHuman(
        stack=stack,
        question=question,
        response_template_name="request_approval_response",
    )

    return ToolResponse(
        is_error=False,
        content={
            "action": action,
            "message": "Waiting for human approval...",
        },
        response_interaction=ask_human,
    )
