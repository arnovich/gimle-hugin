"""The ``bash`` builtin: run a shell command in the agent's sandbox.

The tool resolves the policy and backend from ``config.options["bash"]``,
pre-checks the command with the policy engine (to render a friendly refusal),
then runs it through the session's sandbox. The mapping to ``ToolResponse`` is
deliberate about *what an error is to the model*: only a policy denial, a
timeout, or an infrastructure failure set ``is_error``. A process that ran to
completion is not an error even if it exited non-zero — ``grep`` finding
nothing exits 1, and flagging that as a failure just makes the model thrash.
"""

import logging
import os
from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from gimle.hugin.sandbox.manager import SandboxManager
from gimle.hugin.sandbox.policy import Allow, Deny, Escalate, Policy, evaluate
from gimle.hugin.sandbox.sandbox import ExecResult, PolicyDenied, SandboxSpec
from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

logger = logging.getLogger(__name__)

_DESCRIPTION = """Run a shell command and return its stdout, stderr, and exit \
code.

Working directory: your private per-agent workspace. Persist state by writing \
files there — each call is a FRESH shell, so `cd`, `export`, `source`, and \
background jobs do NOT carry over between calls. Use the `cwd` argument to run \
in a subdirectory for a single call.

Large output is truncated (tail-biased); the full output is written to \
`.hugin/last_output.txt` in your workspace — inspect it with `rg` or `sed -n`. \
A non-zero exit code is normal information (e.g. `grep` finding no matches), \
not a tool failure. A command refused by policy comes back with a `denied` \
reason — that is information, so try a permitted alternative."""


@Tool.register(
    name="builtins.bash",
    description=_DESCRIPTION,
    parameters={
        "command": {
            "type": "string",
            "description": "The shell command to run.",
            "required": True,
        },
        "cwd": {
            "type": "string",
            "description": "Optional subdirectory of the workspace to run in.",
            "required": False,
        },
    },
    is_interactive=False,
    options={
        # Old bash output falls out of context (this knob actually drops it,
        # unlike reduced_context_window which only reformats DataFrames).
        "include_only_in_context_window": True,
        "context_window": 5,
    },
)
def bash(
    command: str,
    stack: Optional["Stack"] = None,
    cwd: Optional[str] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """Run ``command`` in the agent's sandbox and map the outcome for the model.

    Args:
        command: The shell command to run.
        stack: Injected agent stack (gives config, session, env_vars, agent id).
        cwd: Optional workspace-relative subdirectory to run in.
        branch: Injected branch, so branches get isolated working directories.

    Returns:
        A ToolResponse. ``is_error`` is set only for a policy denial, a timeout,
        or an infrastructure failure — never for a plain non-zero exit.
    """
    if stack is None:
        return ToolResponse(
            is_error=True, content={"error": "bash requires an agent stack"}
        )

    config = stack.agent.config
    bash_opts = dict(getattr(config, "options", {}) or {}).get("bash") or {}

    try:
        policy = Policy.from_dict(bash_opts.get("policy"))
    except ValueError as error:
        return ToolResponse(
            is_error=True,
            content={"error": f"invalid bash policy config: {error}"},
        )

    decision = evaluate(command, policy)
    if isinstance(decision, Deny):
        return ToolResponse(
            is_error=True,
            content={"denied": decision.reason, "command": command},
        )
    if isinstance(decision, Escalate):
        # Human-approval routing lands in phase 3; until then, refuse cleanly
        # rather than run an out-of-policy command.
        return ToolResponse(
            is_error=True,
            content={
                "needs_approval": decision.reason,
                "command": command,
                "note": "human approval is not available in this session",
            },
        )
    assert isinstance(decision, Allow)

    try:
        manager = _resolve_manager(stack, bash_opts)
        sandbox = manager.get()
    except (ValueError, NotImplementedError) as error:
        return ToolResponse(
            is_error=True,
            content={"error": f"sandbox unavailable: {error}"},
        )

    workspace = sandbox.workspace_for(stack.agent.id, branch)
    effective_cwd = _resolve_cwd(workspace, cwd)
    if effective_cwd is None:
        return ToolResponse(
            is_error=True,
            content={"error": f"cwd escapes the workspace: {cwd}"},
        )

    try:
        result = sandbox.exec(
            command,
            policy=policy,
            cwd=effective_cwd,
            timeout_s=policy.timeout_s,
            max_output_bytes=policy.max_output_bytes,
        )
    except PolicyDenied as denied:  # backstop; pre-check should have caught it
        return ToolResponse(
            is_error=True,
            content={"denied": denied.reason, "command": command},
        )
    except Exception as error:  # infrastructure failure (daemon down, etc.)
        logger.warning("bash infra failure: %s", error)
        return ToolResponse(
            is_error=True,
            content={"infra_error": str(error), "command": command},
        )

    return _to_response(command, result)


def _resolve_manager(
    stack: "Stack", bash_opts: Dict[str, Any]
) -> SandboxManager:
    """Return the session's SandboxManager, creating and caching it if absent.

    A pre-seeded ``env_vars['sandbox']`` (an app, or a test) wins; otherwise the
    manager is built from ``options.bash`` and cached for the session.
    """
    env_vars = stack.agent.environment.env_vars
    manager = env_vars.get("sandbox")
    if manager is not None:
        return cast(SandboxManager, manager)
    spec = SandboxSpec.from_dict(bash_opts)
    manager = SandboxManager(spec, stack.agent.session.id)
    env_vars["sandbox"] = manager
    return manager


def _resolve_cwd(workspace: str, cwd: Optional[str]) -> Optional[str]:
    """Resolve ``cwd`` inside ``workspace``; None if it escapes."""
    if not cwd:
        return workspace
    candidate = os.path.normpath(os.path.join(workspace, cwd))
    if candidate == workspace or candidate.startswith(workspace + os.sep):
        return candidate
    return None


def _to_response(command: str, result: ExecResult) -> ToolResponse:
    """Map an ExecResult to a ToolResponse (see the module docstring on errors)."""
    return ToolResponse(
        is_error=result.timed_out,
        content={
            "command": command,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_s": round(result.duration_s, 3),
            "truncated": result.truncated,
            "timed_out": result.timed_out,
            "oom_killed": result.oom_killed,
        },
    )
