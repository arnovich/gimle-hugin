"""The ``bash_output`` builtin: collect the result of a background bash command.

Pairs with ``bash(background=true)``. If the command has finished, its result
comes back in the same shape a synchronous ``bash`` call returns (so the model
learns no second format). If it is still running, the tool parks the branch on a
:class:`BashWaiting` — the agent waits (siblings keep running) and the finished
result is delivered as a single ``tool_result``, so the model calls
``bash_output`` once rather than polling in a loop.
"""

import logging
from typing import TYPE_CHECKING, Optional

from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

logger = logging.getLogger(__name__)

_DESCRIPTION = """Get the result of a background command started with \
`bash(background: true)`. Pass the `job_id` you were given. This BLOCKS until \
the command finishes, then returns the same result shape as a normal `bash` \
call (`exit_code`, `stdout`, `stderr`, `truncated`, `timed_out`, …) — call it \
once, do not poll it in a loop. An unknown or already-collected `job_id` returns \
an error; start a fresh command rather than retrying the id."""


@Tool.register(
    name="builtins.bash_output",
    description=_DESCRIPTION,
    parameters={
        "job_id": {
            "type": "string",
            "description": "The job_id returned by bash(background: true).",
            "required": True,
        },
    },
    is_interactive=False,
    options={
        "include_only_in_context_window": True,
        "context_window": 5,
    },
)
def bash_output(
    job_id: str,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """Collect a background job's result, parking until it finishes if needed.

    Args:
        job_id: The id returned by ``bash(background=true)``.
        stack: Injected agent stack (gives the session's background executor).
        branch: Injected branch.

    Returns:
        A ToolResponse with the finished command's result, or a parked
        :class:`BashWaiting` while it is still running.
    """
    if stack is None:
        return ToolResponse(
            is_error=True,
            content={"error": "bash_output requires an agent stack"},
        )
    bg = getattr(stack.agent.session, "background", None)
    if bg is None:
        return ToolResponse(
            is_error=True,
            content={"error": "background execution is unavailable"},
        )

    if not bg.is_done(job_id):
        # Still running: park until done, then resolve as a real tool_result.
        from gimle.hugin.interaction.bash_waiting import BashWaiting

        return ToolResponse(
            is_error=False,
            content={"job_id": job_id, "status": "running"},
            response_interaction=BashWaiting(
                stack=stack, branch=branch, job_id=job_id
            ),
        )

    content, is_error = bg.collect(job_id, agent_id=stack.agent.id)
    return ToolResponse(is_error=is_error, content=content)
