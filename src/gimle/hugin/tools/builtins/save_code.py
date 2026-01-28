"""Save code builtin tool module."""

import logging
import traceback
from typing import TYPE_CHECKING, Optional

from gimle.hugin.artifacts.code import Code
from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="builtins.save_code",
    description=(
        "Save generated code as an artifact. Use this to store source code, "
        "scripts, configuration files, or any text with a specific programming "
        "language for syntax highlighting in the monitor."
    ),
    parameters={
        "content": {
            "type": "string",
            "description": "The source code content to save",
            "required": True,
        },
        "language": {
            "type": "string",
            "description": (
                "Programming language for syntax highlighting. Common values: "
                "python, javascript, typescript, yaml, json, shell, sql, html, "
                "css, markdown, text"
            ),
            "required": True,
        },
        "filename": {
            "type": "string",
            "description": (
                "Optional filename (e.g., 'main.py', 'config.yaml'). "
                "Displayed in the artifact header."
            ),
            "required": False,
        },
        "description": {
            "type": "string",
            "description": (
                "Optional description of what this code does or its purpose."
            ),
            "required": False,
        },
    },
    is_interactive=False,
)
def save_code(
    content: str,
    language: str,
    stack: "Stack",
    filename: Optional[str],
    description: Optional[str],
) -> ToolResponse:
    """
    Save code as a Code artifact.

    Creates a Code artifact with the source code, language metadata for
    syntax highlighting, and optional filename and description. The artifact
    will be displayed in the monitor with proper formatting.

    Args:
        content: The source code content to save
        language: Programming language for syntax highlighting
        stack: The stack (auto-injected)
        filename: Optional filename to display
        description: Optional description of the code

    Returns:
        ToolResponse with the artifact uuid
    """
    try:
        artifact = Code(
            interaction=stack.interactions[-1],
            content=content,
            language=language.lower(),
            filename=filename,
            description=description,
        )
        stack.interactions[-1].add_artifact(artifact)

        response_content = {
            "artifact": artifact.id,
            "language": artifact.language,
        }
        if filename:
            response_content["filename"] = filename

        return ToolResponse(is_error=False, content=response_content)

    except Exception as e:
        logging.error(f"Error saving code: {e} {traceback.format_exc()}")
        return ToolResponse(is_error=True, content={"error": str(e)})
