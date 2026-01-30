"""Search files builtin tool."""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from gimle.hugin.tools.tool import Tool, ToolResponse

logger = logging.getLogger(__name__)


@Tool.register(
    name="builtins.search_files",
    description="""Search for a pattern in files (like grep).

Use this tool to find occurrences of text or regex patterns in files.
Returns matching lines with file paths and line numbers.

Supports searching a single file or recursively through a directory.
""",
    parameters={
        "pattern": {
            "type": "string",
            "description": "Search pattern (regex supported)",
            "required": True,
        },
        "path": {
            "type": "string",
            "description": "File or directory path to search in",
            "required": True,
        },
        "file_pattern": {
            "type": "string",
            "description": "Glob pattern to filter which files to search "
            "(e.g., '*.py', '*.yaml'). Only used when path is a directory. "
            "Default: '*' (all files)",
            "required": False,
        },
        "ignore_case": {
            "type": "boolean",
            "description": "Whether to ignore case when matching. Default: false",
            "required": False,
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of matching lines to return. "
            "Default: 50",
            "required": False,
        },
        "context_lines": {
            "type": "integer",
            "description": "Number of lines to show before and after each match. "
            "Default: 0",
            "required": False,
        },
    },
    is_interactive=False,
)
def search_files(
    pattern: str,
    path: str,
    file_pattern: Optional[str] = None,
    ignore_case: Optional[bool] = None,
    max_results: Optional[int] = None,
    context_lines: Optional[int] = None,
) -> ToolResponse:
    """
    Search for a pattern in files.

    Args:
        pattern: Search pattern (regex)
        path: File or directory to search in
        file_pattern: Glob pattern to filter files
        ignore_case: Whether to ignore case
        max_results: Maximum number of results
        context_lines: Lines of context around matches

    Returns:
        ToolResponse with search results or error
    """
    try:
        search_path = Path(path).resolve()

        if not search_path.exists():
            return ToolResponse(
                is_error=True,
                content={"error": f"Path not found: {path}"},
            )

        # Set defaults
        glob_pattern = file_pattern or "*"
        case_insensitive = ignore_case or False
        limit = max_results or 50
        context = context_lines or 0

        # Compile regex
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return ToolResponse(
                is_error=True,
                content={"error": f"Invalid regex pattern: {str(e)}"},
            )

        # Collect files to search
        files_to_search: List[Path] = []
        if search_path.is_file():
            files_to_search = [search_path]
        else:
            # Search directory recursively
            for file_path in search_path.glob(f"**/{glob_pattern}"):
                if file_path.is_file():
                    files_to_search.append(file_path)

        # Search files
        matches: List[Dict[str, Any]] = []
        files_searched = 0
        files_with_matches: set[str] = set()

        for file_path in files_to_search:
            if len(matches) >= limit:
                break

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                files_searched += 1
            except (UnicodeDecodeError, PermissionError):
                continue  # Skip binary files and permission errors

            for line_num, line in enumerate(lines, start=1):
                if len(matches) >= limit:
                    break

                if regex.search(line):
                    files_with_matches.add(str(file_path))

                    # Build match with context
                    match_info = {
                        "file": str(file_path),
                        "line_number": line_num,
                        "line": line.rstrip(),
                    }

                    if context > 0:
                        # Add context lines
                        start_ctx = max(0, line_num - 1 - context)
                        end_ctx = min(len(lines), line_num + context)
                        context_before = [
                            f"{i+1}: {lines[i].rstrip()}"
                            for i in range(start_ctx, line_num - 1)
                        ]
                        context_after = [
                            f"{i+1}: {lines[i].rstrip()}"
                            for i in range(line_num, end_ctx)
                        ]
                        match_info["context_before"] = context_before
                        match_info["context_after"] = context_after

                    matches.append(match_info)

        return ToolResponse(
            is_error=False,
            content={
                "pattern": pattern,
                "path": str(search_path),
                "files_searched": files_searched,
                "files_with_matches": len(files_with_matches),
                "total_matches": len(matches),
                "truncated": len(matches) >= limit,
                "matches": matches,
            },
        )

    except Exception as e:
        logger.error(f"Error searching files in {path}: {e}")
        return ToolResponse(
            is_error=True,
            content={"error": f"Failed to search files: {str(e)}"},
        )
