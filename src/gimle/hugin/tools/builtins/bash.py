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
from gimle.hugin.sandbox.policy import (
    UNPARSEABLE_REASON,
    Allow,
    Deny,
    Escalate,
    Policy,
    evaluate,
)
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

    # Resolve the manager up front so its audit exists even for a denial — the
    # first (or only) command in a session may be denied, and a denied command
    # is exactly the security event worth recording. A bad/missing backend is
    # tolerated here and only reported when a command is actually allowed.
    try:
        manager: Optional[SandboxManager] = _resolve_manager(stack, bash_opts)
        manager_error: Optional[str] = None
    except (ValueError, NotImplementedError) as error:
        manager, manager_error = None, str(error)

    decision = evaluate(command, policy)
    if isinstance(decision, Deny):
        if decision.reason == UNPARSEABLE_REASON:
            # A parser limitation, NOT a policy refusal — tell the model to
            # rephrase rather than to try a different (permitted) command.
            _record(stack, command, "unparseable", reason=decision.reason)
            return ToolResponse(
                is_error=True,
                content={
                    "unparseable": decision.reason,
                    "command": command,
                    "hint": "the policy guard uses a limited bash parser; "
                    "rephrase without [[ ]], $(( )), or arrays "
                    "(use [ ], test, or expr)",
                },
            )
        _record(stack, command, "denied", reason=decision.reason)
        return ToolResponse(
            is_error=True,
            content={"denied": decision.reason, "command": command},
        )
    if isinstance(decision, Escalate):
        # Human-approval routing lands in phase 3; until then, refuse cleanly
        # rather than run an out-of-policy command.
        _record(stack, command, "escalated", reason=decision.reason)
        return ToolResponse(
            is_error=True,
            content={
                "needs_approval": decision.reason,
                "command": command,
                "note": "human approval is unavailable in this session and "
                "will not become available; do not retry — choose a "
                "different approach",
            },
        )
    assert isinstance(decision, Allow)

    if manager is None:
        return ToolResponse(
            is_error=True,
            content={"error": f"sandbox unavailable: {manager_error}"},
        )
    try:
        sandbox = manager.get()
    except (ValueError, NotImplementedError) as error:
        _record(stack, command, "infra_error", reason=str(error))
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
        _record(stack, command, "denied", reason=denied.reason)
        return ToolResponse(
            is_error=True,
            content={"denied": denied.reason, "command": command},
        )
    except Exception as error:  # infrastructure failure (daemon down, etc.)
        logger.warning("bash infra failure: %s", error)
        _record(stack, command, "infra_error", reason=str(error))
        return ToolResponse(
            is_error=True,
            content={"infra_error": str(error), "command": command},
        )

    _record(
        stack,
        command,
        "timed_out" if result.timed_out else "run",
        exit_code=result.exit_code,
        duration_s=round(result.duration_s, 3),
        truncated=result.truncated,
        timed_out=result.timed_out,
        oom_killed=result.oom_killed,
    )
    return _to_response(command, result)


def _resolve_manager(
    stack: "Stack", bash_opts: Dict[str, Any]
) -> SandboxManager:
    """Return the session's SandboxManager, creating and caching it if absent.

    The session owns the sandbox (``session.sandbox``) so there is a single,
    typed owner that ``Session.close`` can tear down — a pre-created one (an
    app, or a test) wins; otherwise it is built from ``options.bash`` and
    cached on the session.
    """
    session = stack.agent.session
    manager = getattr(session, "sandbox", None)
    if manager is not None:
        return cast(SandboxManager, manager)
    spec = SandboxSpec.from_dict(bash_opts)
    manager = SandboxManager(spec, session.id, record_audit_to_file=True)
    session.sandbox = manager
    return manager


def _record(
    stack: "Stack",
    command: str,
    outcome: str,
    *,
    exit_code: Optional[int] = None,
    duration_s: Optional[float] = None,
    truncated: bool = False,
    timed_out: bool = False,
    oom_killed: bool = False,
    reason: Optional[str] = None,
) -> None:
    """Record an outcome in the session's audit, if a sandbox manager exists.

    Denials can happen before the manager is built (no command has run yet); in
    that rare case there is nothing to record to, so this is a no-op. Recording
    is best-effort and must never disrupt the command result.
    """
    session = stack.agent.session
    manager = getattr(session, "sandbox", None)
    if manager is None:
        return
    try:
        manager.audit.record(
            session_id=session.id,
            agent_id=stack.agent.id,
            command=command,
            outcome=outcome,
            exit_code=exit_code,
            duration_s=duration_s,
            truncated=truncated,
            timed_out=timed_out,
            oom_killed=oom_killed,
            reason=reason,
        )
    except Exception as error:  # audit must never break the tool
        logger.debug("audit record failed: %s", error)


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
