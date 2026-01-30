"""Read file builtin tool."""

import logging
from pathlib import Path
from typing import Optional

from gimle.hugin.tools.tool import Tool, ToolResponse

logger = logging.getLogger(__name__)


@Tool.register(
    name="builtins.read_file",
    description="""Read the contents of a file from the local filesystem.

Use this tool to read text files. For large files, use start_line and
max_lines to read specific portions.

Returns the file contents as text. Binary files are not supported.
""",
    parameters={
        "path": {
            "type": "string",
            "description": "Path to the file to read (absolute or relative)",
            "required": True,
        },
        "start_line": {
            "type": "integer",
            "description": "Line number to start reading from (1-indexed). "
            "Default: 1",
            "required": False,
        },
        "max_lines": {
            "type": "integer",
            "description": "Maximum number of lines to read. Default: 500",
            "required": False,
        },
    },
    is_interactive=False,
)
def read_file(
    path: str,
    start_line: Optional[int] = None,
    max_lines: Optional[int] = None,
) -> ToolResponse:
    """
    Read the contents of a file.

    Args:
        path: Path to the file to read
        start_line: Line number to start reading from (1-indexed)
        max_lines: Maximum number of lines to read

    Returns:
        ToolResponse with file contents or error
    """
    try:
        file_path = Path(path).resolve()

        if not file_path.exists():
            return ToolResponse(
                is_error=True,
                content={"error": f"File not found: {path}"},
            )

        if not file_path.is_file():
            return ToolResponse(
                is_error=True,
                content={"error": f"Not a file: {path}"},
            )

        # Set defaults
        start = max(1, start_line or 1)
        limit = max_lines or 500

        # Read file
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            return ToolResponse(
                is_error=True,
                content={"error": f"Cannot read binary file: {path}"},
            )

        total_lines = len(lines)

        # Extract requested lines (convert to 0-indexed)
        start_idx = start - 1
        end_idx = start_idx + limit
        selected_lines = lines[start_idx:end_idx]

        # Format with line numbers
        numbered_lines = []
        for i, line in enumerate(selected_lines, start=start):
            numbered_lines.append(f"{i:6d}  {line.rstrip()}")

        content = "\n".join(numbered_lines)

        return ToolResponse(
            is_error=False,
            content={
                "path": str(file_path),
                "total_lines": total_lines,
                "start_line": start,
                "lines_read": len(selected_lines),
                "content": content,
            },
        )

    except PermissionError:
        return ToolResponse(
            is_error=True,
            content={"error": f"Permission denied: {path}"},
        )
    except Exception as e:
        logger.error(f"Error reading file {path}: {e}")
        return ToolResponse(
            is_error=True,
            content={"error": f"Failed to read file: {str(e)}"},
        )
