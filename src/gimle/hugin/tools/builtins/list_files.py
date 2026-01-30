"""List files builtin tool."""

import logging
from pathlib import Path
from typing import List, Optional

from gimle.hugin.tools.tool import Tool, ToolResponse

logger = logging.getLogger(__name__)


@Tool.register(
    name="builtins.list_files",
    description="""List files in a directory.

Use this tool to explore the filesystem and find files. Supports glob
patterns for filtering (e.g., "*.py", "**/*.yaml").

Returns a list of file paths matching the criteria.
""",
    parameters={
        "path": {
            "type": "string",
            "description": "Directory path to list (absolute or relative)",
            "required": True,
        },
        "pattern": {
            "type": "string",
            "description": "Glob pattern to filter files (e.g., '*.py', "
            "'**/*.yaml'). Default: '*' (all files in directory)",
            "required": False,
        },
        "recursive": {
            "type": "boolean",
            "description": "Whether to search recursively into subdirectories. "
            "Default: false. Use '**/' in pattern for recursive glob.",
            "required": False,
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of results to return. Default: 100",
            "required": False,
        },
    },
    is_interactive=False,
)
def list_files(
    path: str,
    pattern: Optional[str] = None,
    recursive: Optional[bool] = None,
    max_results: Optional[int] = None,
) -> ToolResponse:
    """
    List files in a directory.

    Args:
        path: Directory path to list
        pattern: Glob pattern to filter files
        recursive: Whether to search recursively
        max_results: Maximum number of results

    Returns:
        ToolResponse with list of files or error
    """
    try:
        dir_path = Path(path).resolve()

        if not dir_path.exists():
            return ToolResponse(
                is_error=True,
                content={"error": f"Path not found: {path}"},
            )

        if not dir_path.is_dir():
            return ToolResponse(
                is_error=True,
                content={"error": f"Not a directory: {path}"},
            )

        # Set defaults
        glob_pattern = pattern or "*"
        is_recursive = recursive or False
        limit = max_results or 100

        # If recursive flag is set but pattern doesn't include **,
        # prepend **/ to make it recursive
        if is_recursive and "**" not in glob_pattern:
            glob_pattern = f"**/{glob_pattern}"

        # Collect files
        files: List[str] = []
        dirs: List[str] = []
        try:
            for item in dir_path.glob(glob_pattern):
                if len(files) + len(dirs) >= limit:
                    break
                if item.is_file():
                    files.append(str(item.relative_to(dir_path)))
                elif item.is_dir() and not is_recursive:
                    dirs.append(str(item.relative_to(dir_path)) + "/")
        except PermissionError:
            pass  # Skip directories we can't access

        # Sort results
        files.sort()
        dirs.sort()

        return ToolResponse(
            is_error=False,
            content={
                "path": str(dir_path),
                "pattern": glob_pattern,
                "directories": dirs,
                "files": files,
                "total_directories": len(dirs),
                "total_files": len(files),
                "truncated": (len(files) + len(dirs)) >= limit,
            },
        )

    except PermissionError:
        return ToolResponse(
            is_error=True,
            content={"error": f"Permission denied: {path}"},
        )
    except Exception as e:
        logger.error(f"Error listing files in {path}: {e}")
        return ToolResponse(
            is_error=True,
            content={"error": f"Failed to list files: {str(e)}"},
        )
