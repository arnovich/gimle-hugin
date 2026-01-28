"""Planning mode tools for the plan/execute agent."""

from typing import Any

from gimle.hugin.interaction.stack import Stack
from gimle.hugin.tools.tool import ToolResponse


def analyze_task(
    task_description: str, stack: Stack, **kwargs: Any
) -> ToolResponse:
    """Analyze a task and identify key components."""
    # Store the task in shared state for later reference
    stack.set_shared_state("current_task", task_description)

    return ToolResponse(
        is_error=False,
        content={
            "status": "analyzed",
            "task": task_description,
            "message": "Task analyzed. Now create a plan with the create_plan tool.",
        },
    )


def create_plan(steps: str, stack: Stack, **kwargs: Any) -> ToolResponse:
    """Create a plan with the given steps."""
    # Parse steps (expecting newline-separated steps)
    step_list = [s.strip() for s in steps.strip().split("\n") if s.strip()]

    # Store plan in shared state
    stack.set_shared_state("plan", step_list)
    stack.set_shared_state("current_step_index", 0)
    stack.set_shared_state("completed_steps", [])

    return ToolResponse(
        is_error=False,
        content={
            "status": "plan_created",
            "steps": step_list,
            "total_steps": len(step_list),
            "message": "Plan created. Review it and call approve_plan to start execution.",
        },
    )


def approve_plan(
    confirmation: str, stack: Stack, **kwargs: Any
) -> ToolResponse:
    """Approve the plan and transition to execution mode."""
    plan = stack.get_shared_state("plan")

    if not plan:
        return ToolResponse(
            is_error=True,
            content={"error": "No plan found. Create a plan first."},
        )

    return ToolResponse(
        is_error=False,
        content={
            "status": "plan_approved",
            "message": "Plan approved! Transitioning to execution mode.",
            "plan": plan,
            "next_step": plan[0] if plan else None,
        },
    )
