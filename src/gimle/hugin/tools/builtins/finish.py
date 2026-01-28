"""Finish tool for terminating task flows."""

from typing import Literal, Optional

from gimle.hugin.tools.tool import Tool, ToolResponse


@Tool.register(
    name="builtins.finish",
    description="""Finish the current task and terminate the flow.
    Use this when the task is complete.
    If you were given as input a task to complete, and you have completed it successfully, then call this tool with finish_type='success' to finish the task.
    If you were given as input a task to complete, and you have not completed it successfully, then call this tool with finish_type='failure' to finish the task.
    The summary is a string that summarizes the task completion.
    The reason is a string that describes the reason for the task completion.
    """,
    parameters={
        "finish_type": {
            "type": "string",
            "description": "Either 'success' or 'failure' to indicate task completion status",
            "required": True,
        },
        "result": {
            "type": "string",
            "description": "The result of the task. This will be passed to the next task as the result parameter.",
            "required": False,
        },
    },
    is_interactive=False,
    options={
        "include_reason": True,
        "respond_with_text": True,
    },
)
def finish_tool(
    finish_type: Literal["success", "failure"],
    result: Optional[str],
) -> ToolResponse:
    """
    Finish the current task and return a ToolResponse.

    This tool should be called when the task is complete. It returns a ToolResponse
    with the finish type and result.

    Args:
        finish_type: Either "success" or "failure" to indicate task completion status
        result: The result of the task. This will be passed to the next task as the result parameter.

    Returns:
        ToolResponse: A ToolResponse with the finish type and result
    """
    return ToolResponse(
        is_error=False,
        content={"finish_type": finish_type, "result": result},
        response_interaction="TaskResult",
    )
