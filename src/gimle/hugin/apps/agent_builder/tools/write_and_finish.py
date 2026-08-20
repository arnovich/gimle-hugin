"""Write the generated agent and finish, as one indivisible step."""

from typing import TYPE_CHECKING, Optional

from gimle.hugin.apps.agent_builder.tools.write_agent_files import (
    write_agent_files,
)
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def write_and_finish(
    stack: "Stack",
    result: str,
    output_path: Optional[str] = None,
) -> ToolResponse:
    """Write the generated agent to disk, then end the task.

    The finalize stage previously had ``write_agent_files`` and ``finish`` as
    two separate tools, with a prompt asking for both. A model that called only
    the second produced a complete, validated agent and threw it away -- 2 of 15
    builds in a golden-set eval, each reported to the user as "Build
    Incomplete" while the agent sat correct and unwritten in memory.

    Giving that stage this tool *instead of* ``finish`` removes the failure
    rather than detecting it: task-level tools replace the config's entirely,
    so there is no longer a way to end the stage without writing. A write that
    fails ends the task as a failure, carrying the reason, so nothing is
    silently reported as done.

    Args:
        stack: Agent stack (auto-injected)
        result: Summary of what was built, passed to the next task
        output_path: Where to write. Defaults to the path the run was started
            with, which is almost always what is wanted.

    Returns:
        ToolResponse that terminates the task.
    """
    env_vars = stack.agent.environment.env_vars
    user_input = env_vars.get("user_input", {})
    # An edit knows where it came from even when no output path was supplied,
    # and writing an edit anywhere but the directory it was loaded from would
    # silently fork the agent instead of changing it.
    destination = (
        output_path
        or user_input.get("output_path")
        or env_vars.get("loaded_agent_path")
    )
    if not destination:
        return ToolResponse(
            is_error=True,
            content={
                "error": "No output path is known; pass output_path.",
            },
        )

    written = write_agent_files(stack, destination)
    if written.is_error:
        # Surface the refusal rather than finishing successfully over it: the
        # validation gate lives inside write_agent_files, so this is how a
        # payload that does not validate ends the stage.
        return ToolResponse(
            is_error=True,
            content={
                "finish_type": "failure",
                "result": (
                    "Could not write the agent: "
                    f"{written.content.get('error')}"
                ),
                "errors": written.content.get("errors", []),
            },
            response_interaction="TaskResult",
        )

    return ToolResponse(
        is_error=False,
        content={
            "finish_type": "success",
            "result": result,
            "output_path": written.content.get("output_path"),
            "written": written.content.get("written", []),
        },
        response_interaction="TaskResult",
    )
