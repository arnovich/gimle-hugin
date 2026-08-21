"""Read an agent's historic runs into a report the builder can cite.

The analysis itself is deterministic aggregation in ``analysis.traces`` -- the
model never sees a raw trace, only a small redacted report. This tool is the
builder-facing wrapper, and its second job is the one that matters: it keeps
the report in ``env_vars`` so ``propose_change`` can check a citation against
it rather than trusting the model to remember a number correctly.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from gimle.hugin.analysis.traces import analyze_traces as analyse
from gimle.hugin.apps.agent_builder.tools.propose_change import REPORT_KEY
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

# The subdirectories a Hugin storage root actually holds. Requiring one of
# them means a mistyped path fails here rather than reporting "0 runs", which
# reads as "this agent has never been run" and is a different conclusion.
STORAGE_MARKERS = ("agents", "sessions", "interactions")

MAX_LIMIT = 500


def analyze_traces(
    stack: "Stack",
    storage_path: str,
    limit: int = 50,
    agent_name: Optional[str] = None,
) -> ToolResponse:
    """Summarise an agent's historic runs.

    Args:
        stack: Agent stack (auto-injected)
        storage_path: The storage directory the agent ran against
        limit: Most recent runs to read
        agent_name: Only consider runs whose config has this name

    Returns:
        ToolResponse carrying the report, which is also stored for
        ``propose_change`` to validate citations against.
    """
    if not storage_path or not storage_path.strip():
        return ToolResponse(
            is_error=True, content={"error": "no storage path specified"}
        )

    root = Path(storage_path).expanduser()
    if not root.is_dir():
        return ToolResponse(
            is_error=True,
            content={"error": f"no such storage directory: {root}"},
        )
    if not any((root / marker).is_dir() for marker in STORAGE_MARKERS):
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    f"{root} is not a Hugin storage directory -- expected "
                    f"one of {', '.join(STORAGE_MARKERS)}/ inside it"
                )
            },
        )

    try:
        capped = max(1, min(int(limit), MAX_LIMIT))
    except (TypeError, ValueError):
        capped = 50

    report = analyse(
        str(Path(os.path.realpath(root))),
        limit=capped,
        agent_name=agent_name,
    )

    stack.agent.environment.env_vars[REPORT_KEY] = report
    return ToolResponse(is_error=False, content=report)
