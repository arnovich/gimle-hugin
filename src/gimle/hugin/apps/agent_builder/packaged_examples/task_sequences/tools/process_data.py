"""Data processing tool for the task_sequences example."""

from typing import TYPE_CHECKING

from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="process_data",
    description="Process data and mark current stage as complete",
    parameters={
        "stage": {
            "type": "string",
            "description": "Current stage name (extract, transform, analyze, report)",
        },
        "output": {
            "type": "string",
            "description": "Processed output from this stage",
        },
    },
    is_interactive=False,
)
def process_data(stack: "Stack", stage: str, output: str) -> ToolResponse:
    """Process data and mark current stage as complete.

    This tool simulates data processing and returns the output
    that will be passed to the next stage in the sequence.

    Args:
        stage: Current stage name
        output: Processed output from this stage

    Returns:
        ToolResponse with processed output
    """
    return ToolResponse(
        is_error=False,
        content={
            "stage": stage,
            "output": output,
            "message": f"Stage '{stage}' completed successfully",
            "result": output,  # This will be passed to next task
        },
    )
