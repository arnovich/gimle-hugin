"""``LocalSandbox`` — run commands as subprocesses on the host.

This backend has **no isolation boundary**, and the design says so plainly: it
is the zero-dependency option for iterating and trusted tasks, not a sandbox.
It still does the honest, useful things it can: enforce policy fail-closed, run
in a per-agent workspace, scrub the environment (no inherited secrets, ``HOME``
pointed at the workspace), kill the whole process group on timeout, cap output,
and confine file access to the workspace. What it cannot do — bound CPU/memory,
contain a determined command, stop ``/dev/tcp`` egress — is the container's job,
not this backend's.
"""

import json
import logging
import os
import shutil
import signal
import subprocess
import time
from typing import Dict, Optional

from gimle.hugin.sandbox.policy import Allow, Policy, evaluate
from gimle.hugin.sandbox.sandbox import (
    ExecResult,
    PolicyDenied,
    Sandbox,
    SandboxSpec,
    truncate_output,
)

logger = logging.getLogger(__name__)

_SPILL_RELATIVE = os.path.join(".hugin", "last_output.txt")
# Owner stamp read by the reaper to decide whether a workspace is abandoned.
OWNER_FILE = ".hugin_owner.json"


class LocalSandbox(Sandbox):
    """Execute commands as host subprocesses under a per-session workspace."""

    def __init__(
        self,
        spec: SandboxSpec,
        session_id: str,
        workspace_root: str = "./storage/sandboxes",
    ) -> None:
        """Bind this sandbox to ``session_id`` under ``workspace_root``."""
        self._spec = spec
        self._session_root = os.path.abspath(
            os.path.join(workspace_root, session_id)
        )
        self._bash = shutil.which("bash") or "/bin/bash"

    # -- lifecycle --

    def start(self) -> None:
        """Create the session workspace root and stamp its owner. Idempotent."""
        os.makedirs(self._session_root, exist_ok=True)
        self._write_owner_stamp()

    def _write_owner_stamp(self) -> None:
        """Record the owning PID so the reaper can spot an abandoned workspace.

        Written once (the created time is preserved across restarts) and
        best-effort — a workspace we cannot stamp is simply reaped by age.
        """
        stamp = os.path.join(self._session_root, OWNER_FILE)
        if os.path.exists(stamp):
            return
        try:
            with open(stamp, "w", encoding="utf-8") as handle:
                json.dump({"pid": os.getpid(), "created": time.time()}, handle)
        except OSError as error:  # best-effort; the reaper falls back to age
            logger.debug("could not write owner stamp: %s", error)

    def stop(self) -> None:
        """No persistent resource to release. Idempotent, safe if unstarted."""

    # -- workspaces --

    def workspace_for(self, agent_id: str, branch: Optional[str]) -> str:
        """Return this ``(agent, branch)`` directory, creating it if absent."""
        path = os.path.join(
            self._session_root, "agents", agent_id, branch or "default"
        )
        os.makedirs(path, exist_ok=True)
        return path

    # -- execution --

    def exec(
        self,
        command: str,
        *,
        policy: Policy,
        cwd: str,
        timeout_s: int,
        max_output_bytes: int = 16_000,
    ) -> ExecResult:
        """Run ``command`` through ``bash -c``; enforce policy fail-closed."""
        decision = evaluate(command, policy)
        if not isinstance(decision, Allow):
            raise PolicyDenied(getattr(decision, "reason", "command refused"))

        effective_timeout = min(timeout_s, policy.max_timeout_s)
        env = self._scrubbed_env(cwd)

        started = time.monotonic()
        proc = subprocess.Popen(
            [self._bash, "-c", command],
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,  # own process group, so we can kill it all
        )
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=effective_timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_group(proc)
            stdout, stderr = proc.communicate()
        duration = time.monotonic() - started

        full_stdout, full_stderr = stdout or "", stderr or ""
        out, out_trunc = truncate_output(full_stdout, max_output_bytes)
        err, err_trunc = truncate_output(full_stderr, max_output_bytes)
        truncated = out_trunc or err_trunc
        if truncated:
            self._spill(cwd, full_stdout, full_stderr)

        return ExecResult(
            exit_code=proc.returncode if proc.returncode is not None else -1,
            stdout=out,
            stderr=err,
            duration_s=duration,
            truncated=truncated,
            timed_out=timed_out,
            oom_killed=False,  # a bare subprocess cannot bound or detect OOM
        )

    def _scrubbed_env(self, cwd: str) -> Dict[str, str]:
        """Build a minimal env: no inherited secrets, HOME in the workspace."""
        return {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": cwd,
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "TERM": "dumb",
        }

    @staticmethod
    def _kill_group(proc: "subprocess.Popen") -> None:
        """SIGKILL the command's whole process group (children included)."""
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass  # already gone

    def _spill(self, cwd: str, stdout: str, stderr: str) -> None:
        """Write full output to the workspace so the agent can read past the cap."""
        try:
            spill_path = os.path.join(cwd, _SPILL_RELATIVE)
            os.makedirs(os.path.dirname(spill_path), exist_ok=True)
            with open(spill_path, "w", encoding="utf-8") as handle:
                handle.write(stdout)
                if stderr:
                    handle.write("\n--- stderr ---\n")
                    handle.write(stderr)
        except OSError as error:  # best-effort; never fail the command over it
            logger.debug("could not spill full output: %s", error)

    # -- files --

    def put_file(self, path: str, content: bytes) -> None:
        """Write ``content`` to ``path`` inside the workspace."""
        target = self._confine(path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(content)

    def get_file(self, path: str) -> bytes:
        """Read ``path`` from the workspace, refusing a symlink escape."""
        target = self._confine(path)
        with open(target, "rb") as handle:
            return handle.read()

    def _confine(self, path: str) -> str:
        """Resolve ``path`` within the session workspace or raise PolicyDenied.

        ``realpath`` dereferences symlinks first, so a link planted inside the
        workspace that points outside it resolves to an outside path and is
        rejected — the harvest/escape hole the security review flagged.
        """
        root = os.path.realpath(self._session_root)
        candidate = path if os.path.isabs(path) else os.path.join(root, path)
        resolved = os.path.realpath(candidate)
        if resolved != root and not resolved.startswith(root + os.sep):
            raise PolicyDenied(f"path escapes the workspace: {path}")
        return resolved
