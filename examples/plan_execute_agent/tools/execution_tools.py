"""Execution mode tools for the plan/execute agent."""

from typing import Any, Dict, List

from gimle.hugin.interaction.stack import Stack
from gimle.hugin.tools.tool import ToolResponse


def execute_step(action: str, stack: Stack, **kwargs: Any) -> ToolResponse:
    """Execute the current step with the given action."""
    plan: List[str] = stack.get_shared_state("plan", default=[])
    current_index: int = stack.get_shared_state("current_step_index", default=0)

    if not plan:
        return ToolResponse(
            is_error=True,
            content={"error": "No plan found. Request a replan."},
        )

    if current_index >= len(plan):
        return ToolResponse(
            is_error=False,
            content={
                "status": "all_complete",
                "message": "All steps completed! Call finish to complete the task.",
            },
        )

    current_step = plan[current_index]

    # Simulate execution (in a real scenario, this would do actual work)
    return ToolResponse(
        is_error=False,
        content={
            "status": "executed",
            "step_number": current_index + 1,
            "step": current_step,
            "action_taken": action,
            "message": f"Step {current_index + 1} executed. Call mark_step_complete to proceed.",
        },
    )


def mark_step_complete(notes: str, stack: Stack, **kwargs: Any) -> ToolResponse:
    """Mark the current step as complete and move to the next."""
    plan: List[str] = stack.get_shared_state("plan", default=[])
    current_index: int = stack.get_shared_state("current_step_index", default=0)
    completed: List[Dict[str, Any]] = stack.get_shared_state(
        "completed_steps", default=[]
    )

    if current_index >= len(plan):
        return ToolResponse(
            is_error=False,
            content={
                "status": "all_complete",
                "message": "All steps already completed! Call finish.",
            },
        )

    # Record completion
    completed.append(
        {
            "step_number": current_index + 1,
            "step": plan[current_index],
            "notes": notes,
        }
    )
    stack.set_shared_state("completed_steps", completed)

    # Move to next step
    next_index = current_index + 1
    stack.set_shared_state("current_step_index", next_index)

    if next_index >= len(plan):
        return ToolResponse(
            is_error=False,
            content={
                "status": "all_complete",
                "completed_count": len(completed),
                "message": "All steps completed! Call finish to complete the task.",
            },
        )

    return ToolResponse(
        is_error=False,
        content={
            "status": "step_complete",
            "completed_step": current_index + 1,
            "next_step_number": next_index + 1,
            "next_step": plan[next_index],
            "remaining": len(plan) - next_index,
            "message": f"Step {current_index + 1} complete. Moving to step {next_index + 1}.",
        },
    )


def request_replan(reason: str, stack: Stack, **kwargs: Any) -> ToolResponse:
    """Request to go back to planning mode."""
    current_index: int = stack.get_shared_state("current_step_index", default=0)
    completed: List[Dict[str, Any]] = stack.get_shared_state(
        "completed_steps", default=[]
    )

    # Clear blocked state if it was set
    stack.set_shared_state("blocked", False)

    return ToolResponse(
        is_error=False,
        content={
            "status": "replan_requested",
            "reason": reason,
            "progress": {
                "completed_steps": len(completed),
                "stopped_at_step": current_index + 1,
            },
            "message": "Returning to planning mode. Create a new plan considering the issue.",
        },
    )
