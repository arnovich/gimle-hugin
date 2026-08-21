"""State tools for shared state between agents."""

from typing import TYPE_CHECKING

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


NAMESPACE = "numbers"


def set_number(key: str, value: int, stack: "Stack") -> ToolResponse:
    """Set a number in the shared state."""
    stack.set_shared_state(key, value, namespace=NAMESPACE)
    return ToolResponse(
        is_error=False,
        content={
            "set": True,
            "key": key,
            "value": value,
            "namespace": NAMESPACE,
        },
    )


def get_number(key: str, stack: "Stack") -> ToolResponse:
    """Get a number from the shared state."""
    value = stack.get_shared_state(key, namespace=NAMESPACE)
    if value is None:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Key '{key}' not found in namespace '{NAMESPACE}'"
            },
        )
    return ToolResponse(
        is_error=False,
        content={
            "key": key,
            "value": value,
            "namespace": NAMESPACE,
        },
    )


def list_numbers(stack: "Stack") -> ToolResponse:
    """List all numbers in the shared state."""
    all_state = stack.get_all_shared_state(namespace=NAMESPACE)
    return ToolResponse(
        is_error=False,
        content={
            "numbers": all_state,
            "count": len(all_state),
            "namespace": NAMESPACE,
        },
    )
