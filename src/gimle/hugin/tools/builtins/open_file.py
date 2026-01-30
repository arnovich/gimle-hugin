"""Open file builtin tool - opens files with the system default application."""

import logging
import platform
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="builtins.open_file",
    description="Open a file with the system's default application. "
    "Use this to open HTML files in a browser, images in a viewer, "
    "PDFs in a reader, etc.",
    parameters={
        "file_path": {
            "type": "string",
            "description": "Path to the file to open",
            "required": True,
        },
    },
    is_interactive=False,
)
def open_file(stack: "Stack", file_path: str) -> ToolResponse:
    """Open a file with the system's default application.

    Args:
        stack: The stack (auto-injected)
        file_path: Path to the file to open

    Returns:
        ToolResponse indicating success or failure
    """
    try:
        path = Path(file_path)

        # Check if file exists
        if not path.exists():
            return ToolResponse(
                is_error=True,
                content={"error": f"File not found: {file_path}"},
            )

        # Get absolute path
        abs_path = str(path.resolve())

        # Determine the command based on the platform
        system = platform.system()
        if system == "Darwin":  # macOS
            cmd = ["open", abs_path]
        elif system == "Windows":
            cmd = ["start", "", abs_path]
        else:  # Linux and others
            cmd = ["xdg-open", abs_path]

        # Run the command
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        logging.info(f"Opened file: {abs_path}")

        return ToolResponse(
            is_error=False,
            content={
                "message": f"Opened {path.name}",
                "file_path": abs_path,
                "file_type": path.suffix or "unknown",
            },
        )

    except Exception as e:
        logging.error(f"Error opening file: {e}")
        return ToolResponse(
            is_error=True,
            content={"error": f"Failed to open file: {str(e)}"},
        )
