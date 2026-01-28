"""Save file builtin tool module."""

import logging
import traceback
from typing import TYPE_CHECKING, Optional

from gimle.hugin.artifacts.code import Code
from gimle.hugin.artifacts.text import Text
from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


# Map file extensions to languages/formats
EXTENSION_MAP = {
    # Code files
    ".py": ("code", "python"),
    ".js": ("code", "javascript"),
    ".ts": ("code", "typescript"),
    ".java": ("code", "java"),
    ".c": ("code", "c"),
    ".cpp": ("code", "cpp"),
    ".h": ("code", "c"),
    ".hpp": ("code", "cpp"),
    ".cs": ("code", "csharp"),
    ".go": ("code", "go"),
    ".rs": ("code", "rust"),
    ".rb": ("code", "ruby"),
    ".php": ("code", "php"),
    ".swift": ("code", "swift"),
    ".kt": ("code", "kotlin"),
    ".scala": ("code", "scala"),
    ".sh": ("code", "shell"),
    ".bash": ("code", "bash"),
    ".sql": ("code", "sql"),
    ".html": ("code", "html"),
    ".css": ("code", "css"),
    # Config/data files
    ".yaml": ("code", "yaml"),
    ".yml": ("code", "yaml"),
    ".json": ("text", "json"),
    ".xml": ("text", "xml"),
    # Text files
    ".md": ("text", "markdown"),
    ".txt": ("text", "plain"),
    ".log": ("text", "plain"),
}


def _detect_format_from_filename(filename: str) -> tuple:
    """Detect artifact type and format from filename extension.

    Returns:
        Tuple of (artifact_type, format/language)
    """
    for ext, (artifact_type, fmt) in EXTENSION_MAP.items():
        if filename.lower().endswith(ext):
            return artifact_type, fmt
    return "text", "plain"


@Tool.register(
    name="builtins.save_file",
    description=(
        "Save a file as an artifact. Automatically detects the file type from "
        "the filename extension and creates the appropriate artifact (Code for "
        "source files, Text for documents). The file will be displayed in the "
        "monitor with proper formatting."
    ),
    parameters={
        "filename": {
            "type": "string",
            "description": (
                "The filename including extension (e.g., 'main.py', "
                "'config.yaml', 'README.md'). The extension determines how "
                "the content is rendered."
            ),
            "required": True,
        },
        "content": {
            "type": "string",
            "description": "The file content to save",
            "required": True,
        },
        "description": {
            "type": "string",
            "description": (
                "Optional description of the file's purpose or contents."
            ),
            "required": False,
        },
    },
    is_interactive=False,
)
def save_file(
    filename: str,
    content: str,
    stack: "Stack",
    description: Optional[str],
) -> ToolResponse:
    """
    Save a file as an artifact.

    Creates either a Code or Text artifact based on the file extension.
    The artifact will be displayed in the monitor with appropriate formatting.

    Args:
        filename: The filename with extension
        content: The file content
        stack: The stack (auto-injected)
        description: Optional description

    Returns:
        ToolResponse with the artifact uuid and detected type
    """
    try:
        artifact_type, fmt = _detect_format_from_filename(filename)

        if artifact_type == "code":
            artifact = Code(
                interaction=stack.interactions[-1],
                content=content,
                language=fmt,
                filename=filename,
                description=description,
            )
        else:
            artifact = Text(
                interaction=stack.interactions[-1],
                content=content,
                format=fmt,  # type: ignore
            )

        stack.interactions[-1].add_artifact(artifact)

        response_content = {
            "artifact": artifact.id,
            "filename": filename,
            "type": artifact_type,
            "format": fmt,
        }

        return ToolResponse(is_error=False, content=response_content)

    except Exception as e:
        logging.error(f"Error saving file: {e} {traceback.format_exc()}")
        return ToolResponse(is_error=True, content={"error": str(e)})
