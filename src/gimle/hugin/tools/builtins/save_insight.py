"""Save insight builtin tool module."""

import logging
import traceback
from typing import TYPE_CHECKING, Literal

from gimle.hugin.artifacts.text import Text
from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="builtins.save_insight",
    description="Save an insight or finding as an artifact. Use this to document important discoveries, patterns, or conclusions from your task.",
    parameters={
        "insight": {
            "type": "string",
            "description": "The insight or finding to save",
            "required": True,
        },
        "format": {
            "type": "string",
            "description": "The format of the insight. One of: markdown, plain, html, json",
            "required": True,
            "default": "markdown",
        },
    },
    is_interactive=False,
)
def save_insight(
    insight: str,
    stack: "Stack",
    format: Literal["markdown", "plain", "html", "json"],
) -> ToolResponse:
    """
    Save an insight as a Text artifact.

    Creates a Text artifact with the insight content in the specified format.
    The artifact will be automatically created and added to the interaction.

    Args:
        insight: The insight or finding to save
        stack: The stack
        format: The format of the insight (markdown, plain, html, json)

    Returns:
        ToolResponse with the artifact uuid
    """
    try:
        artifact = Text(
            interaction=stack.interactions[-1], content=insight, format=format
        )
        stack.interactions[-1].add_artifact(artifact)

        return ToolResponse(is_error=False, content={"artifact": artifact.id})

    except Exception as e:
        logging.error(f"Error saving insight: {e} {traceback.format_exc()}")
        return ToolResponse(is_error=True, content={"error": str(e)})
