"""Counter tools for the parallel agents example."""

from typing import TYPE_CHECKING

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


# Store counts per agent


def increment(stack: "Stack") -> ToolResponse:
    """Increment this agent's counter by 1."""
    count = stack.get_shared_state(key="count", default=0)
    count += 1
    stack.set_shared_state(key="count", value=count)
    return ToolResponse(
        is_error=False,
        content={
            "count": count,
            "message": "Incremented by 1",
        },
    )


def get_count(stack: "Stack") -> ToolResponse:
    """Get this agent's current count."""
    count = stack.get_shared_state(key="count", default=0)
    return ToolResponse(
        is_error=False,
        content={"count": count},
    )
