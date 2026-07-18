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
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

from gimle.hugin.sandbox.policy import Allow, Policy, evaluate
from gimle.hugin.sandbox.sandbox import (
    DEFAULT_SANDBOX_ROOT,
    ExecResult,
    PolicyDenied,
    Sandbox,
    SandboxSpec,
    truncate_output,
)

logger = logging.getLogger(__name__)

# Warn once per process that the local backend is not a sandbox — an operator
# selecting ``backend: local`` should see it, not have to read a docstring.
_isolation_warned = False

_SPILL_RELATIVE = os.path.join(".hugin", "last_output.txt")
# Owner stamp read by the reaper to decide whether a workspace is abandoned.
OWNER_FILE = ".hugin_owner.json"


def process_start_time(pid: int) -> Optional[str]:
    """Return an opaque token identifying this PID's process *incarnation*.

    Paired with the PID in the owner stamp, this lets the reaper tell the
    original owner from an unrelated process that later recycled the same PID —
    without which a dead workspace whose PID got reused is kept forever (a leak)
    or, worse, a live one is deleted. Best-effort and dependency-free: Linux
    reads ``/proc/<pid>/stat`` (field 22, start time in clock ticks); macOS/BSD
    shell out to ``ps -o lstart=``. Returns ``None`` when it cannot be
    determined, in which case callers fall back to PID-only liveness.
    """
    try:
        stat_path = f"/proc/{pid}/stat"
        if os.path.exists(stat_path):
            with open(stat_path, encoding="utf-8") as handle:
                data = handle.read()
            # comm (field 2) may contain spaces/parens; split after the last ')'
            after_comm = data[data.rfind(")") + 2 :].split()
            return after_comm[19]  # field 22 overall -> starttime
        result = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip() or None
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


# Hard ceiling on output *buffered in this process* per command, across stdout
# and stderr combined. The model only ever sees ``max_output_bytes`` after
# truncation; this larger cap bounds parent memory (and the spill file) so a
# runaway ``yes`` / ``cat /dev/zero`` cannot OOM the orchestrator before the
# per-command truncation runs. Past it, the process group is killed.
_MAX_CAPTURE_BYTES = 2_000_000

# How long to wait, after killing the group, for the reader threads to drain
# and the process to be reaped — bounded so an escaped child that ``setsid``'d
# away and still holds the stdout pipe can never hang ``exec`` indefinitely.
_DRAIN_GRACE_S = 0.5


class LocalSandbox(Sandbox):
    """Execute commands as host subprocesses under a per-session workspace."""

    def __init__(
        self,
        spec: SandboxSpec,
        session_id: str,
        workspace_root: str = DEFAULT_SANDBOX_ROOT,
    ) -> None:
        """Bind this sandbox to ``session_id`` under ``workspace_root``."""
        self._spec = spec
        self._session_root = os.path.abspath(
            os.path.join(workspace_root, session_id)
        )
        self._bash = shutil.which("bash") or "/bin/bash"
        # Live subprocesses, so a background command running on a worker thread
        # can be killed at teardown (a ThreadPoolExecutor cannot interrupt a
        # thread blocked in a command, and the reaper only GCs directories).
        self._active: Set["subprocess.Popen"] = set()
        self._active_lock = threading.Lock()
        global _isolation_warned
        if not _isolation_warned:
            logger.warning(
                "LocalSandbox has NO isolation boundary: commands run as host "
                "subprocesses with your PATH and full filesystem access, and "
                "policy 'workspace_only'/'network' are NOT enforced. Use the "
                "docker or ssh backend for untrusted input."
            )
            _isolation_warned = True

    # -- lifecycle --

    def start(self) -> None:
        """Create the session workspace root and stamp its owner. Idempotent."""
        os.makedirs(self._session_root, exist_ok=True)
        self._write_owner_stamp()

    def _write_owner_stamp(self) -> None:
        """Record the owning PID + start time so the reaper spots abandonment.

        Rewritten on **every** ``start()`` with the current live PID — a
        resumed session (same session id, new process) must re-stamp, or the
        stale dead PID would make the reaper delete the running session's
        workspace. Best-effort: a workspace we cannot stamp is reaped by age.
        """
        stamp = os.path.join(self._session_root, OWNER_FILE)
        pid = os.getpid()
        record = {
            "pid": pid,
            "start_time": process_start_time(pid),
            "created": time.time(),
        }
        try:  # preserve the original creation time, if any, for debugging
            with open(stamp, encoding="utf-8") as handle:
                existing = json.load(handle)
            if isinstance(existing, dict) and "created" in existing:
                record["created"] = existing["created"]
        except (OSError, ValueError):
            pass
        try:
            with open(stamp, "w", encoding="utf-8") as handle:
                json.dump(record, handle)
        except OSError as error:  # best-effort; the reaper falls back to age
            logger.debug("could not write owner stamp: %s", error)

    def stop(self) -> None:
        """Kill any still-running command's process group. Idempotent.

        A foreground command is already gone by the time ``stop`` runs, but a
        **background** command running on a worker thread is not — so killing its
        group here is what lets ``Session.close`` interrupt an in-flight ``exec``
        (the worker's ``_capture`` loop then returns) instead of leaking a live
        subprocess. Best-effort; safe if never started (empty set).
        """
        with self._active_lock:
            procs = list(self._active)
        for proc in procs:
            self._kill_group(proc)

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
            start_new_session=True,  # own process group, so we can kill it all
        )
        with self._active_lock:
            self._active.add(proc)
        try:
            full_stdout, full_stderr, timed_out, capped = self._capture(
                proc, effective_timeout
            )
        finally:
            with self._active_lock:
                self._active.discard(proc)
        duration = time.monotonic() - started

        if capped:
            full_stderr += (
                f"\n[hugin: output exceeded {_MAX_CAPTURE_BYTES} bytes; "
                "process terminated]"
            )

        out, out_trunc = truncate_output(full_stdout, max_output_bytes)
        err, err_trunc = truncate_output(full_stderr, max_output_bytes)
        truncated = out_trunc or err_trunc or capped
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

    def _capture(
        self, proc: "subprocess.Popen", timeout_s: int
    ) -> Tuple[str, str, bool, bool]:
        """Drain the process's output under a byte ceiling and a wall-clock cap.

        Reads stdout and stderr concurrently into buffers bounded by
        :data:`_MAX_CAPTURE_BYTES`, and kills the whole process group when the
        command exceeds either the output ceiling or ``timeout_s``. After the
        kill it waits only ``_DRAIN_GRACE_S`` for the readers, so a child that
        escaped the group and still holds the pipe cannot block the caller.

        Returns ``(stdout, stderr, timed_out, capped)``.
        """
        buffers: Dict[str, bytearray] = {"out": bytearray(), "err": bytearray()}
        total = [0]
        lock = threading.Lock()
        capped = threading.Event()

        def reader(stream: object, key: str) -> None:
            try:
                while True:
                    chunk = stream.read(65536)  # type: ignore[attr-defined]
                    if not chunk:
                        break
                    with lock:
                        total[0] += len(chunk)
                        room = _MAX_CAPTURE_BYTES - len(buffers[key])
                        if room > 0:
                            buffers[key].extend(chunk[:room])
                        over = total[0] > _MAX_CAPTURE_BYTES
                    if over:
                        capped.set()
            except (OSError, ValueError):  # pipe closed under us on kill
                pass

        threads: List[threading.Thread] = []
        for stream, key in ((proc.stdout, "out"), (proc.stderr, "err")):
            if stream is None:
                continue
            thread = threading.Thread(
                target=reader, args=(stream, key), daemon=True
            )
            thread.start()
            threads.append(thread)

        timed_out = False
        deadline = time.monotonic() + timeout_s
        while True:
            if proc.poll() is not None:
                break
            if capped.is_set():
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
            time.sleep(0.02)

        if proc.poll() is None:
            self._kill_group(proc)
        for thread in threads:
            thread.join(timeout=_DRAIN_GRACE_S)
        try:
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:  # escaped child; leave it to the OS
            pass

        stdout = bytes(buffers["out"]).decode("utf-8", "replace")
        stderr = bytes(buffers["err"]).decode("utf-8", "replace")
        return stdout, stderr, timed_out, capped.is_set()

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
        """SIGKILL the command's whole process group (children included).

        ``start_new_session=True`` makes the child a group leader whose pgid
        equals its pid, so we target ``proc.pid`` directly rather than
        ``os.getpgid(proc.pid)`` — the latter raises if the leader has already
        exited while group members remain, silently leaving them alive. The
        unreaped process still holds its pid, so the group id is stable here.
        """
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass  # already gone, or not ours to kill

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
