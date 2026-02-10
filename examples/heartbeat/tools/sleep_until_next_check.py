"""Go back to sleep and resume the heartbeat after a delay.

Called by the LLM after it has finished analyzing new data from
the sensor. Returns a Waiting that loops back to the sensor tool.
"""

from typing import TYPE_CHECKING

from gimle.hugin.interaction.conditions import Condition
from gimle.hugin.interaction.waiting import Waiting
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def sleep_until_next_check(
    stack: "Stack", folder_path: str, interval: int = 3
) -> ToolResponse:
    """Pause for ``interval`` ticks, then call check_folder again.

    Args:
        stack: The agent stack.
        folder_path: Path to the folder to monitor.
        interval: Ticks to wait before the next check.

    Returns:
        ToolResponse with a Waiting that resumes the heartbeat.
    """
    return ToolResponse(
        is_error=False,
        content={"message": "Going back to sleep"},
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
