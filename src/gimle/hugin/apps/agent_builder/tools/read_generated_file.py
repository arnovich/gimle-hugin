"""Read one generated file back out of the in-progress payload."""

from typing import TYPE_CHECKING

from gimle.hugin.apps.agent_builder.tools.agent_paths import (
    is_exempt,
    validate_generated_key,
)
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

# A generated file is small by construction, but a repair loop can read
# several, so cap what one call can put into context.
MAX_CHARS = 20_000


def read_generated_file(stack: "Stack", path: str) -> ToolResponse:
    """Return the current content of one generated file.

    Without this the only way to see generated content is ``preview_files``,
    which dumps every file at once, and the ``generate_*`` tools overwrite
    wholesale. "Repair this tool" therefore meant re-emitting a whole file from
    a one-line error message, with the previous version buried far back in a
    context that is never truncated -- so the third attempt was worse informed
    than the first.

    Args:
        stack: Agent stack (auto-injected)
        path: Key of the generated file, e.g. ``tools/fetch_prices.py``

    Returns:
        ToolResponse with the file's content, or an error naming what exists.
    """
    generated_files = stack.agent.environment.env_vars.get(
        "generated_files", {}
    )
    if not generated_files:
        return ToolResponse(
            is_error=True,
            content={"error": "No files have been generated yet"},
        )

    if not is_exempt(path):
        problem = validate_generated_key(path)
        if problem:
            return ToolResponse(is_error=True, content={"error": problem})

    if path not in generated_files:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"'{path}' has not been generated",
                "available": sorted(generated_files),
            },
        )

    content = generated_files[path]
    truncated = len(content) > MAX_CHARS
    return ToolResponse(
        is_error=False,
        content={
            "path": path,
            "content": content[:MAX_CHARS],
            "truncated": truncated,
            "characters": len(content),
        },
    )
