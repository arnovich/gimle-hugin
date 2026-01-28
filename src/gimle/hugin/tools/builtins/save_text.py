"""Save text builtin tool module."""

import logging
import traceback
from typing import TYPE_CHECKING, Literal, Optional

from gimle.hugin.artifacts.text import Text
from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="builtins.save_text",
    description=(
        "Save text content as an artifact. Use this to store generated text, "
        "reports, documentation, analysis results, or any text output that "
        "should be visible in the monitor. Supports multiple formats for "
        "proper rendering."
    ),
    parameters={
        "content": {
            "type": "string",
            "description": "The text content to save",
            "required": True,
        },
        "format": {
            "type": "string",
            "description": (
                "The format of the text. One of: markdown (for formatted text, "
                "reports), plain (for simple text), html (for rich content), "
                "json (for structured data), xml (for XML data)"
            ),
            "required": True,
        },
        "title": {
            "type": "string",
            "description": (
                "Optional title for the artifact (shown in preview)"
            ),
            "required": False,
        },
    },
    is_interactive=False,
)
def save_text(
    content: str,
    format: Literal["markdown", "plain", "html", "json", "xml"],
    stack: "Stack",
    title: Optional[str],
) -> ToolResponse:
    """
    Save text content as a Text artifact.

    Creates a Text artifact with the content in the specified format.
    The artifact will be displayed in the monitor with appropriate rendering.

    Args:
        content: The text content to save
        format: The format of the text (markdown, plain, html, json, xml)
        stack: The stack (auto-injected)
        title: Optional title for the artifact

    Returns:
        ToolResponse with the artifact uuid and format
    """
    try:
        # If title is provided, prepend it to markdown content
        if title and format == "markdown":
            content = f"# {title}\n\n{content}"

        artifact = Text(
            interaction=stack.interactions[-1],
            content=content,
            format=format,
        )
        stack.interactions[-1].add_artifact(artifact)

        response_content = {
            "artifact": artifact.id,
            "format": format,
        }
        if title:
            response_content["title"] = title

        return ToolResponse(is_error=False, content=response_content)

    except Exception as e:
        logging.error(f"Error saving text: {e} {traceback.format_exc()}")
        return ToolResponse(is_error=True, content={"error": str(e)})
