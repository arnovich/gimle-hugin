"""Sensor: check a folder for new files.

This is the "sensor" in the heartbeat pattern. Replace this tool
with your own to monitor a different source (API, database, etc.).
"""

import os
from typing import TYPE_CHECKING, List

from gimle.hugin.interaction.conditions import Condition
from gimle.hugin.interaction.waiting import Waiting
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def check_folder(
    stack: "Stack", folder_path: str, interval: int = 3
) -> ToolResponse:
    """Check a folder for new files since the last check.

    Compares current folder contents against previously seen files
    stored in shared state.

    - **New files found**: returns them to the LLM for analysis
      (no ``response_interaction``).
    - **No new files**: returns a ``Waiting`` that silently loops
      back to this tool after ``interval`` ticks.

    Args:
        stack: The agent stack.
        folder_path: Path to the folder to monitor.
        interval: Ticks to wait before the next check.

    Returns:
        ToolResponse with new file list or a silent heartbeat loop.
    """
    try:
        current_files: List[str] = sorted(os.listdir(folder_path))
    except FileNotFoundError:
        return ToolResponse(
            is_error=True,
            content={"error": f"Folder not found: {folder_path}"},
        )
    except OSError as e:
        return ToolResponse(
            is_error=True,
            content={"error": (f"Cannot read folder {folder_path}: {e}")},
        )

    # Compare against previously seen files
    seen: List[str] = stack.get_shared_state("seen_files", default=[])
    seen_set = set(seen)
    new_files = [f for f in current_files if f not in seen_set]

    if new_files:
        # Update seen files and return to LLM for analysis
        stack.set_shared_state("seen_files", seen + new_files)
        return ToolResponse(
            is_error=False,
            content={
                "new_files": new_files,
                "message": (f"Found {len(new_files)} new file(s)"),
            },
        )

    # Nothing new — silent heartbeat loop (skip the LLM)
    return ToolResponse(
        is_error=False,
        content={"message": "No new files"},
        response_interaction=Waiting(
            stack=stack,
            branch=None,
            condition=Condition(
                evaluator="wait_for_ticks",
                parameters={"ticks": interval},
            ),
            next_tool="check_folder",
            next_tool_args={
                "folder_path": folder_path,
                "interval": interval,
            },
        ),
    )
