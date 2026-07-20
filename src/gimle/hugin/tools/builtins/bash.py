"""The ``bash`` builtin: run a shell command in the agent's sandbox.

The tool resolves the policy and backend from ``config.options["bash"]``,
pre-checks the command with the policy engine (to render a friendly refusal),
then runs it through the session's sandbox. The mapping to ``ToolResponse`` is
deliberate about *what an error is to the model*: only a policy denial, a
timeout, or an infrastructure failure set ``is_error``. A process that ran to
completion is not an error even if it exited non-zero — ``grep`` finding
nothing exits 1, and flagging that as a failure just makes the model thrash.
"""

import dataclasses
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, Union

from gimle.hugin.sandbox.background import (
    DEFAULT_DEFER_AFTER_S,
    BackgroundLimit,
    result_content,
)
from gimle.hugin.sandbox.manager import SandboxManager
from gimle.hugin.sandbox.policy import (
    UNPARSEABLE_REASON,
    Allow,
    Deny,
    Escalate,
    Policy,
    evaluate,
)
from gimle.hugin.sandbox.sandbox import (
    ExecResult,
    PolicyDenied,
    SandboxSpec,
    sandbox_root_for,
)
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

Commands are killed after ~15s by default; pass a larger `timeout_s` for a \
slow command. Long commands are handled automatically: a command still running \
after a moment keeps running in the background and its result comes back to \
this same call once it finishes — you don't have to do anything. For a command \
you know will take a while (a build, a test suite, an install) and want to keep \
working during, pass `background: true`: it returns immediately with a `job_id`, \
and you MUST later call `bash_output` with that `job_id` to get the result (a \
backgrounded command you never collect is lost). Only the last few command \
outputs stay visible to you — write anything you need to keep into a file.

Large output is truncated (tail-biased); when that happens the response \
carries a `full_output` path holding the complete output — inspect that path \
with `rg` or `sed -n`. A non-zero exit code is normal \
information (e.g. `grep` finding no matches), not a tool failure. A command \
refused by policy comes back with a `denied` reason — try a permitted \
alternative; an `unparseable` reason means the guard's parser choked, so \
rephrase the command (avoid `[[ ]]`, `$(( ))`, arrays)."""


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
        "timeout_s": {
            "type": "integer",
            "description": "Optional per-command timeout in seconds for a slow "
            "command (default ~15s, capped by policy).",
            "required": False,
        },
        "background": {
            "type": "boolean",
            "description": "Run the command in the background and return a "
            "job_id immediately so you can keep working; collect the result "
            "later with bash_output. Use for known-long commands (builds, "
            "test suites, installs).",
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
    timeout_s: Optional[int] = None,
    background: Optional[bool] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """Run ``command`` in the agent's sandbox and map the outcome for the model.

    The command runs on a worker thread so it never freezes sibling agents: a
    fast command returns inline; one still running after a short grace
    auto-backgrounds and its branch parks (siblings run) until it finishes. With
    ``background=True`` it returns a ``job_id`` immediately for
    collect-via-``bash_output``.

    Args:
        command: The shell command to run.
        stack: Injected agent stack (gives config, session, env_vars, agent id).
        cwd: Optional workspace-relative subdirectory to run in.
        timeout_s: Optional per-command timeout; clamped to the policy ceiling.
        background: Return a ``job_id`` immediately instead of waiting.
        branch: Injected branch, so branches get isolated working directories.

    Returns:
        A ToolResponse. ``is_error`` is set only for a policy denial, a timeout,
        an out-of-memory kill, or an infrastructure failure — never for a plain
        non-zero exit.
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
            _record(
                manager, stack, command, "unparseable", reason=decision.reason
            )
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
        _record(manager, stack, command, "denied", reason=decision.reason)
        return ToolResponse(
            is_error=True,
            content={"denied": decision.reason, "command": command},
        )
    if isinstance(decision, Escalate):
        _record(manager, stack, command, "escalated", reason=decision.reason)
        if getattr(config, "interactive", False):
            # Interactive: ask a human. The command parks on a BashApproval;
            # approval runs exactly this command, denial refuses it.
            from gimle.hugin.interaction.bash_approval import BashApproval

            return ToolResponse(
                is_error=False,
                content={
                    "awaiting_approval": decision.reason,
                    "command": command,
                },
                response_interaction=BashApproval(
                    stack=stack,
                    branch=branch,
                    command=command,
                    cwd=cwd,
                    timeout_s=timeout_s,
                    reason=decision.reason,
                ),
            )
        # Non-interactive: no human can answer, so refuse cleanly (a park would
        # stall the run forever). This is a plain policy denial.
        return ToolResponse(
            is_error=True,
            content={
                "denied": decision.reason,
                "command": command,
                "note": "this command needs human approval, which a "
                "non-interactive session cannot provide; choose a permitted "
                "alternative",
            },
        )
    assert isinstance(decision, Allow)

    prepared = _prepare_run(manager, manager_error, stack, command, cwd, branch)
    if isinstance(prepared, ToolResponse):
        return prepared
    sandbox, effective_cwd = prepared

    background_run = bool(background)
    requested_timeout = (
        timeout_s
        if timeout_s is not None and timeout_s > 0
        else (policy.max_timeout_s if background_run else policy.timeout_s)
    )

    session = stack.agent.session
    bg = getattr(session, "background", None)
    if bg is None:  # a hand-rolled session without the executor: run inline
        response = _run_sync(
            manager,
            stack,
            command,
            sandbox,
            policy,
            effective_cwd,
            requested_timeout,
        )
        return _with_env_note(response, manager, stack, sandbox, branch)

    try:
        job = bg.submit(
            sandbox=sandbox,
            manager=manager,
            session_id=session.id,
            agent_id=stack.agent.id,
            command=command,
            cwd=effective_cwd,
            policy=policy,
            timeout_s=requested_timeout,
            max_output_bytes=policy.max_output_bytes,
        )
    except BackgroundLimit as error:
        return ToolResponse(
            is_error=True, content={"error": str(error), "command": command}
        )

    if background_run:
        # Fire-and-forget: return the handle now; the agent keeps working and
        # siblings run. The result (and its audit) are collected via bash_output.
        return ToolResponse(
            is_error=False,
            content={
                "job_id": job.job_id,
                "status": "running",
                "note": "the command is running in the background; call "
                "bash_output with this job_id to get its result. A "
                "backgrounded command you never collect is lost.",
            },
        )

    # Automatic: block up to the grace, then defer if it is still running so a
    # long command stops freezing siblings. The parked branch resolves into the
    # normal result when the command finishes.
    from gimle.hugin.interaction.bash_waiting import BashWaiting

    if bg.wait(job.job_id, DEFAULT_DEFER_AFTER_S):
        content, is_error = bg.collect(job.job_id, agent_id=stack.agent.id)
        response = ToolResponse(is_error=is_error, content=content)
        return _with_env_note(response, manager, stack, sandbox, branch)
    return ToolResponse(
        is_error=False,
        content={"job_id": job.job_id, "status": "running"},
        response_interaction=BashWaiting(
            stack=stack, branch=branch, job_id=job.job_id
        ),
    )


def _prepare_run(
    manager: Optional[SandboxManager],
    manager_error: Optional[str],
    stack: "Stack",
    command: str,
    cwd: Optional[str],
    branch: Optional[str],
) -> Union[ToolResponse, Tuple[Any, str]]:
    """Return the started sandbox + resolved cwd, or a ToolResponse error.

    Shared by the normal allow path and the human-approved run path: bring the
    backend up (a start failure is a clean, non-retryable ``infra_error``) and
    resolve the effective cwd inside the workspace (an escape is refused).
    """
    if manager is None:
        return ToolResponse(
            is_error=True,
            content={"error": f"sandbox unavailable: {manager_error}"},
        )
    try:
        sandbox = manager.get()
    except Exception as error:
        # Bringing a backend up is the classic infra failure (daemon down,
        # image not built, remote host unreachable); surface it cleanly.
        _record(manager, stack, command, "infra_error", reason=str(error))
        return ToolResponse(
            is_error=True,
            content={
                "infra_error": str(error),
                "command": command,
                "note": "the sandbox backend could not start; retrying will "
                "not fix this — an operator needs to fix the backend (e.g. "
                "start the docker daemon / build the image / install the "
                "sandbox extra, or make the ssh host reachable)",
            },
        )
    workspace = sandbox.workspace_for(stack.agent.id, branch)
    effective_cwd = _resolve_cwd(workspace, cwd)
    if effective_cwd is None:
        return ToolResponse(
            is_error=True,
            content={"error": f"cwd escapes the workspace: {cwd}"},
        )
    return sandbox, effective_cwd


def _run_sync(
    manager: Optional[SandboxManager],
    stack: "Stack",
    command: str,
    sandbox: Any,
    policy: Policy,
    cwd: str,
    timeout_s: int,
    reason: Optional[str] = None,
) -> ToolResponse:
    """Run the command synchronously (fallback when no background executor).

    ``reason`` tags the audit entry (e.g. ``"human-approved"`` for a policy-
    bypass run, so the audit distinguishes it from an ordinarily-allowed one).
    """
    try:
        result = sandbox.exec(
            command,
            policy=policy,
            cwd=cwd,
            timeout_s=timeout_s,
            max_output_bytes=policy.max_output_bytes,
        )
    except PolicyDenied as denied:  # backstop; pre-check should have caught it
        _record(manager, stack, command, "denied", reason=denied.reason)
        return ToolResponse(
            is_error=True,
            content={"denied": denied.reason, "command": command},
        )
    except Exception as error:  # infrastructure failure (daemon down, etc.)
        logger.warning("bash infra failure: %s", error)
        _record(manager, stack, command, "infra_error", reason=str(error))
        return ToolResponse(
            is_error=True,
            content={"infra_error": str(error), "command": command},
        )
    _record(
        manager,
        stack,
        command,
        "timed_out" if result.timed_out else "run",
        exit_code=result.exit_code,
        duration_s=round(result.duration_s, 3),
        truncated=result.truncated,
        timed_out=result.timed_out,
        oom_killed=result.oom_killed,
        reason=reason,
    )
    return _to_response(command, result)


def run_approved(
    stack: "Stack",
    command: str,
    cwd: Optional[str],
    timeout_s: Optional[int],
    branch: Optional[str],
) -> ToolResponse:
    """Run a human-approved command, bypassing the policy for exactly it.

    Called **only** by :class:`BashApproval` after a human approved this exact
    command — it is a plain function, not a tool parameter, so the model cannot
    reach it (a model-settable ``_approved`` flag would let it self-approve and
    bypass the policy: ``execute_tool`` passes a tool_call's args straight to the
    function, undeclared keys included). Runs synchronously under an
    ``unrestricted`` policy variant (the human is the authority for this one
    command string), preserving the policy's timeout/output caps.
    """
    config = stack.agent.config
    bash_opts = dict(getattr(config, "options", {}) or {}).get("bash") or {}
    try:
        policy = Policy.from_dict(bash_opts.get("policy"))
    except ValueError as error:
        return ToolResponse(
            is_error=True,
            content={"error": f"invalid bash policy config: {error}"},
        )
    try:
        manager: Optional[SandboxManager] = _resolve_manager(stack, bash_opts)
        manager_error: Optional[str] = None
    except (ValueError, NotImplementedError) as error:
        manager, manager_error = None, str(error)
    prepared = _prepare_run(manager, manager_error, stack, command, cwd, branch)
    if isinstance(prepared, ToolResponse):
        return prepared
    sandbox, effective_cwd = prepared
    run_timeout = (
        timeout_s
        if timeout_s is not None and timeout_s > 0
        else policy.timeout_s
    )
    run_policy = dataclasses.replace(policy, mode="unrestricted")
    return _run_sync(
        manager,
        stack,
        command,
        sandbox,
        run_policy,
        effective_cwd,
        run_timeout,
        reason="human-approved",
    )


def record_denied_by_human(
    stack: "Stack", command: str, reason: Optional[str]
) -> None:
    """Audit a command a human explicitly refused (best-effort).

    Called by :class:`BashApproval` on a deny, so the audit distinguishes a human
    "no" from an escalation that was never answered (a stall).
    """
    config = stack.agent.config
    bash_opts = dict(getattr(config, "options", {}) or {}).get("bash") or {}
    try:
        manager: Optional[SandboxManager] = _resolve_manager(stack, bash_opts)
    except (ValueError, NotImplementedError):
        return
    _record(manager, stack, command, "denied_by_human", reason=reason)


def _resolve_manager(
    stack: "Stack", bash_opts: Dict[str, Any]
) -> SandboxManager:
    """Return the SandboxManager for this agent's spec — one per distinct spec.

    The session owns a sandbox per :class:`SandboxSpec` (``session.sandboxes``),
    so agents that share an isolation profile share a backend (and its per-agent
    workspaces) while an agent with a different profile gets its own — the
    agent's own ``options.bash`` decides where its shell runs, not whichever
    agent happened to run bash first. ``Session.close`` tears them all down.
    """
    session = stack.agent.session
    spec = SandboxSpec.from_dict(bash_opts)
    existing = session.sandboxes.get(spec)
    if existing is not None:
        return existing
    manager = SandboxManager(
        spec,
        session.id,
        workspace_root=_sandbox_root(session),
        record_audit_to_file=True,
    )
    session.sandboxes[spec] = manager
    return manager


def _sandbox_root(session: Any) -> str:
    """Sandbox root for this session — beside its storage, so both agree.

    Derived from the session's storage base path (``<base>/sandboxes``); falls
    back to the default when storage is in-memory / has no path. This keeps a
    custom ``--storage-path`` run's sandboxes with its sessions and lets the
    startup reaper find them.
    """
    storage = getattr(getattr(session, "environment", None), "storage", None)
    base = getattr(storage, "base_path", None)
    return sandbox_root_for(str(base) if base else None)


def _record(
    manager: Optional[SandboxManager],
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
    """Record an outcome in ``manager``'s audit, if a manager was resolved.

    A denial can happen before any manager is built (a missing/invalid backend),
    in which case ``manager`` is None and this is a no-op. Recording is
    best-effort and must never disrupt the command result.
    """
    if manager is None:
        return
    try:
        manager.audit.record(
            session_id=stack.agent.session.id,
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
    """Map an ExecResult to a ToolResponse (see the module docstring on errors).

    An OOM kill / timeout returns partial output for a process that did not
    finish — an error the model must react to, unlike a plain non-zero exit.
    """
    return ToolResponse(
        is_error=result.timed_out or result.oom_killed or result.output_capped,
        content=result_content(command, result),
    )


def _network_note(spec: SandboxSpec) -> str:
    """Return a one-line, spec-derived description of what the shell can reach.

    The load-bearing field of the environment note: an agent that doesn't know
    the network is off wastes turns on ``curl``/``pip``/``npm`` that can't
    connect. Derived from the resolved spec so it can never drift from reality.
    """
    if spec.backend == "local":
        return "on (host network — the local backend has no isolation)"
    if spec.backend == "ssh":
        return "the remote host's network (whatever that host can reach)"
    # docker
    if not spec.network:
        return "OFF — curl/uv/pip/npm cannot reach the internet; work offline"
    if spec.egress_allowlist:
        allowed = ", ".join(spec.egress_allowlist)
        return f"filtered — only these hosts are reachable: {allowed}"
    if spec.allow_unrestricted_egress:
        return "on (unrestricted egress)"
    return "OFF"  # network:true without a policy is refused at start()


def _environment_note(spec: SandboxSpec, workspace: str) -> Dict[str, Any]:
    """Return a one-time description of the shell's environment for the agent.

    Rendered from the resolved spec (no probe command), so it never drifts: the
    backend, whether the network is reachable (and how), where files persist,
    and the fresh-shell reminder.
    """
    return {
        "backend": spec.backend,
        "network": _network_note(spec),
        "workspace": workspace,
        "note": "Each call is a FRESH shell — cd/export/source do not persist. "
        "Write files in the workspace to keep state between calls.",
    }


def _with_env_note(
    response: ToolResponse,
    manager: Optional[SandboxManager],
    stack: "Stack",
    sandbox: Any,
    branch: Optional[str],
) -> ToolResponse:
    """Attach a one-time environment note to an agent's first successful bash use.

    Only on a non-error, dict-content result, and the announcement is consumed
    (``announce_once``) *only* when the note is actually attached — so a first
    command that errored or was backgrounded still gets the note next time.
    """
    if (
        manager is None
        or response.is_error
        or not isinstance(response.content, dict)
    ):
        return response
    try:
        workspace = sandbox.workspace_for(stack.agent.id, branch)
        note = _environment_note(manager.spec, workspace)
    except Exception as error:  # the note is a nicety; never break the result
        logger.debug("environment note skipped: %s", error)
        return response
    if manager.announce_once(stack.agent.id):
        response.content["environment"] = note
    return response
