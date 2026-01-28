"""Create branch tool for the simple branching example."""

from typing import TYPE_CHECKING

from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def create_single_branch(
    stack: "Stack", branch_name: str, question: str
) -> ToolResponse:
    """Create a branch to explore a question.

    This spawns an explorer in a separate branch to investigate
    a specific question. The branch runs in parallel and saves
    its result as an artifact.

    Args:
        stack: The stack to add the branch to
        branch_name: Short name for the branch (use snake_case)
        question: The question to explore in this branch

    Returns:
        ToolResponse confirming branch creation
    """
    branch_task_template = stack.agent.environment.task_registry.get(
        "explore_branch"
    )

    branch_task = branch_task_template.set_input_parameters(
        {
            "question": question,
        }
    )

    task_def = TaskDefinition(
        stack=stack,
        task=branch_task,
        branch=branch_name,
    )

    stack.add_interaction(task_def, branch=branch_name)

    return ToolResponse(
        is_error=False,
        content={
            "branch_name": branch_name,
            "question": question,
            "message": f"Created branch '{branch_name}' to explore: {question}",
            "note": "The branch will run in parallel and save its findings as an artifact.",
        },
    )
