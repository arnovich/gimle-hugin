"""``SSHSandbox`` — run commands on a disposable remote machine over SSH.

The boundary here is *where the command runs*: a throwaway box the operator
stands up and doesn't mind the agent breaking (the "BYO host" model — see
``tasks/open/026-bash-sandbox-ssh-backend/design.md``). Hugin does not create or
destroy the machine; it connects, runs each session in an isolated remote
workspace, and cleans up only its own footprint (running jobs, the ControlMaster
socket). It therefore cannot leak a VM — only a remote workspace, which the
same-host startup TTL sweep reaps.

No new Python dependency: this shells out to ``ssh``/``scp`` (no ``paramiko``),
so ``ssh`` stays a true peer of ``local``/``docker``. Connection hygiene is
mandatory — ``ForwardAgent=no`` (never hand the operator's agent to a box the
agent controls), ``BatchMode=yes`` (no interactive prompts), and
``ConnectTimeout``/``ServerAliveInterval`` so a network partition surfaces as a
fast error instead of hanging the client while the remote job runs on.

Two correctness properties the design note calls out:

- **A partition cannot hang the turn** — the streamed read is bounded by a
  host-side deadline (like the docker backend), and ssh's own keepalive bounds
  the client.
- **A partition is not silently retried** — an ssh *transport* failure (exit
  255) raises a clear, do-not-retry error rather than re-running a command whose
  fate is unknown (a half-run ``rm``/``git push`` must not be blindly repeated).

The remote command runs under a scrubbed env (``env -i``, ``HOME`` at the
workspace) and a remote ``timeout`` so the remote job is bounded and killable,
and the untrusted command travels over stdin (``bash -c "$(cat)"``) so it never
passes through a second layer of shell quoting.

Remote assumption: a Linux box with ``bash`` + coreutils (``timeout``, ``base64
-d``, ``find``) — the ordinary disposable-VPS baseline.
"""

import base64
import hashlib
import json
import logging
import os
import posixpath
import shlex
import subprocess
import tempfile
import threading
import time
from typing import List, Optional, Set, Tuple

from gimle.hugin.sandbox.local import OWNER_FILE, process_start_time
from gimle.hugin.sandbox.policy import Allow, Policy, evaluate
from gimle.hugin.sandbox.sandbox import (
    DEFAULT_SANDBOX_ROOT,
    ExecResult,
    PolicyDenied,
    Sandbox,
    SandboxSpec,
    classify_timeout_exit,
    truncate_output,
)

logger = logging.getLogger(__name__)

# Remote workspace base, under the remote user's $HOME.
REMOTE_BASE = ".hugin-sandbox"
OWNER_MARKER = OWNER_FILE  # reuse the local backend's stamp filename

# ssh option values (fixed for v1; tunable config is deferred — see design note).
CONNECT_TIMEOUT_S = 10
SERVER_ALIVE_INTERVAL_S = 15
SERVER_ALIVE_COUNT_MAX = 3
CONTROL_PERSIST_S = 60

# Grace on top of a command's own timeout before ``timeout`` SIGKILLs it, and
# before the host-side read gives up (covers ssh/network latency) — mirrors the
# docker backend so a backgrounded remote child can't hang the agent's turn.
_KILL_AFTER_S = 5
_HOST_GRACE_S = 10

# Fixed deadline for short control-plane calls (mkdir, put/get, start, stop).
_CONTROL_DEADLINE_S = CONNECT_TIMEOUT_S + 30

# Hard ceiling on bytes buffered per command (matches the other backends).
_MAX_CAPTURE_BYTES = 2_000_000

# Reap sibling remote workspaces not modified within this many minutes (an
# active session keeps its mtime fresh, so it is never swept out from under
# itself). 24h — generous; a proper dead-owner remote reaper is task 030.
_TTL_MINUTES = 24 * 60

# ssh exits 255 for its *own* transport failures (host down, auth, dropped
# connection) — distinct from any exit code the remote command could return.
SSH_TRANSPORT_EXIT = 255

_SPILL_RELATIVE = ".hugin/last_output.txt"


def _safe_component(value: str) -> str:
    """Return ``value`` reduced to a shell/path-safe remote directory name."""
    return "".join(c if (c.isalnum() or c in "._-") else "-" for c in value)


class SSHSandbox(Sandbox):
    """Execute commands on a disposable remote host over one SSH connection."""

    def __init__(
        self,
        spec: SandboxSpec,
        session_id: str,
        workspace_root: str = DEFAULT_SANDBOX_ROOT,
    ) -> None:
        """Bind to ``spec.host``; fail loud if no host was configured."""
        if not spec.host:
            raise ValueError(
                "backend: ssh requires options.bash.host (user@host or an "
                "ssh_config alias)"
            )
        self._spec = spec
        self._session_id = session_id
        self._host = spec.host
        self._key = spec.ssh_key
        # Our ControlMaster socket lives in the system temp dir under a short,
        # collision-resistant name (unix socket paths have a ~104-char limit).
        digest = hashlib.sha256(
            f"{session_id}|{spec.host}".encode("utf-8")
        ).hexdigest()[:12]
        self._control_path = os.path.join(
            tempfile.gettempdir(), f"hugin-cm-{digest}"
        )
        self._remote_root: Optional[str] = None
        self._created: Set[str] = set()
        self._started = False

    # -- pure command construction (SDK/host-free, unit-tested) --

    def _ssh_opts(self) -> List[str]:
        """Return the mandatory ssh hardening + connection-reuse options."""
        opts = [
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={CONNECT_TIMEOUT_S}",
            "-o",
            f"ServerAliveInterval={SERVER_ALIVE_INTERVAL_S}",
            "-o",
            f"ServerAliveCountMax={SERVER_ALIVE_COUNT_MAX}",
            "-o",
            "ForwardAgent=no",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ControlMaster=auto",
            "-o",
            f"ControlPath={self._control_path}",
            "-o",
            f"ControlPersist={CONTROL_PERSIST_S}",
        ]
        if self._key:
            opts += ["-i", self._key]
        return opts

    def _ssh_argv(self, remote_command: str) -> List[str]:
        """Return the full ``ssh`` argv running ``remote_command`` on the host."""
        return ["ssh", *self._ssh_opts(), self._host, remote_command]

    def _remote_wrapper(self, remote_cwd: str, timeout_s: int) -> str:
        """Return the remote shell string that runs the stdin command safely.

        cd into the workspace, scrub the environment (``env -i`` — no inherited
        remote secrets — with ``HOME`` at the workspace), and run under a remote
        ``timeout`` so the job is bounded/killable. The untrusted command is read
        from stdin (``bash -c "$(cat)"``) so it never passes through a second
        shell-quoting layer.
        """
        q_cwd = shlex.quote(remote_cwd)
        return (
            f"cd {q_cwd} && "
            f"env -i HOME={q_cwd} PATH=/usr/local/bin:/usr/bin:/bin "
            f"LANG=C.UTF-8 TERM=dumb "
            f'timeout -k {_KILL_AFTER_S} {int(timeout_s)} bash -c "$(cat)"'
        )

    def _remote_start_script(self) -> str:
        """Return the one-shot remote script: TTL-sweep, create root, stamp owner.

        Sweeps sibling session dirs not modified within the TTL (an active
        session's mtime stays fresh, so it is protected), (re)creates this
        session's root, writes the owner marker (base64 so no quoting games), and
        prints the resolved absolute root path for the caller to capture.
        """
        marker = json.dumps(
            {
                "pid": os.getpid(),
                "start_time": process_start_time(os.getpid()),
                "created": time.time(),
                "session": self._session_id,
            }
        )
        b64 = base64.b64encode(marker.encode("utf-8")).decode("ascii")
        session = _safe_component(self._session_id)
        return (
            "set -e; "
            f'base="$HOME/{REMOTE_BASE}"; '
            'mkdir -p "$base"; '
            f'find "$base" -mindepth 1 -maxdepth 1 -type d -mmin +{_TTL_MINUTES}'
            " -exec rm -rf {} + 2>/dev/null || true; "
            f'root="$base/{session}"; '
            'mkdir -p "$root"; '
            f'printf %s {b64} | base64 -d > "$root/{OWNER_MARKER}"; '
            'printf %s "$root"'
        )

    # -- lifecycle --

    def start(self) -> None:
        """Open the connection, create the remote workspace, stamp the owner.

        Idempotent: a second call on a live sandbox returns at once. On a resume
        (new process) the remote script re-creates the root (``mkdir -p``) and
        rewrites the owner marker with the live PID, so the TTL sweep never
        removes an active session's workspace. Raises a clear error if the host
        is unreachable or the setup command fails (the tool maps it to a
        do-not-retry ``infra_error``).
        """
        if self._started:
            return
        rc, out, err, _capped, hung = self._run(
            self._ssh_argv(self._remote_start_script()),
            deadline_s=_CONTROL_DEADLINE_S,
        )
        if hung or rc == SSH_TRANSPORT_EXIT:
            raise RuntimeError(
                f"cannot reach ssh host {self._host!r} "
                f"(transport error / timeout): {err.decode('utf-8', 'replace')}"
            )
        if rc != 0:
            raise RuntimeError(
                f"failed to initialise the remote workspace on {self._host!r}: "
                f"{err.decode('utf-8', 'replace')}"
            )
        self._remote_root = out.decode("utf-8", "replace").strip()
        if not self._remote_root:
            raise RuntimeError(
                f"remote workspace path was empty on {self._host!r}"
            )
        self._started = True

    def stop(self) -> None:
        """Best-effort kill this session's remote jobs; close/clean the socket.

        The remote workspace is intentionally left in place (it persists for a
        resume, like the docker bind mount) and is reaped by the same-host TTL
        sweep. Idempotent and never raises.
        """
        if not self._started:
            return
        if self._remote_root:
            # Best-effort: kills the still-running command wrapper for this
            # session (matched by its unique root path). A backgrounded remote
            # child that reparented away escapes this and is bounded only by the
            # box's disposal — documented in the design note.
            self._safe_run(
                self._ssh_argv(
                    f"pkill -f {shlex.quote(self._remote_root)} "
                    "2>/dev/null || true"
                )
            )
        self._safe_run(["ssh", *self._ssh_opts(), "-O", "exit", self._host])
        try:
            if os.path.exists(self._control_path):
                os.remove(self._control_path)
        except OSError as error:  # best-effort
            logger.debug("could not remove control socket: %s", error)
        self._started = False

    # -- workspaces --

    def workspace_for(self, agent_id: str, branch: Optional[str]) -> str:
        """Return the remote ``(agent, branch)`` path, creating it once."""
        if self._remote_root is None:
            raise RuntimeError("sandbox not started")
        path = posixpath.join(
            self._remote_root, "agents", agent_id, branch or "default"
        )
        if path not in self._created:
            self._safe_run(self._ssh_argv(f"mkdir -p {shlex.quote(path)}"))
            self._created.add(path)
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
        """Run ``command`` on the remote host; enforce policy fail-closed.

        Raises :class:`PolicyDenied` on a refused command and ``RuntimeError`` on
        an ssh transport failure (a partition — not safe to retry). A remote
        wall-clock timeout / OOM is reported in the result, not raised.
        """
        decision = evaluate(command, policy)
        if not isinstance(decision, Allow):
            raise PolicyDenied(getattr(decision, "reason", "command refused"))
        if not self._started:
            raise RuntimeError("sandbox not started")

        effective_timeout = min(timeout_s, policy.max_timeout_s)
        argv = self._ssh_argv(self._remote_wrapper(cwd, effective_timeout))
        host_deadline = effective_timeout + _KILL_AFTER_S + _HOST_GRACE_S

        started = time.monotonic()
        rc, out_bytes, err_bytes, capped, hung = self._run(
            argv, input_bytes=command.encode("utf-8"), deadline_s=host_deadline
        )
        duration = time.monotonic() - started

        if rc == SSH_TRANSPORT_EXIT and not hung:
            # ssh could not run the command at all (host down / dropped
            # connection / auth). The command may or may not have run remotely —
            # its fate is unknown, so refuse to retry rather than double-execute.
            raise RuntimeError(
                f"ssh transport error to {self._host!r}: the command did not "
                "complete over the connection; do not retry (its remote effect "
                "is unknown)"
            )

        timed_out, oom_killed = classify_timeout_exit(
            rc, hung, duration, effective_timeout
        )
        stdout_raw = out_bytes.decode("utf-8", "replace")
        stderr_raw = err_bytes.decode("utf-8", "replace")
        if capped:
            stderr_raw += (
                f"\n[hugin: output exceeded {_MAX_CAPTURE_BYTES} bytes; "
                "stopped reading]"
            )
        if hung:
            stderr_raw += (
                "\n[hugin: command exceeded its time budget and was abandoned "
                "(it may have left a background process on the remote)]"
            )

        out, out_trunc = truncate_output(stdout_raw, max_output_bytes)
        err, err_trunc = truncate_output(stderr_raw, max_output_bytes)
        truncated = out_trunc or err_trunc or capped
        if truncated:
            self._spill_remote(cwd, out_bytes, err_bytes)

        return ExecResult(
            exit_code=rc,
            stdout=out,
            stderr=err,
            duration_s=duration,
            truncated=truncated,
            timed_out=timed_out,
            oom_killed=oom_killed,
        )

    def _spill_remote(
        self, remote_cwd: str, stdout: bytes, stderr: bytes
    ) -> None:
        """Write the full output to the remote workspace so the agent can read it."""
        blob = stdout
        if stderr:
            blob = blob + b"\n--- stderr ---\n" + stderr
        spill = posixpath.join(remote_cwd, _SPILL_RELATIVE)
        parent = posixpath.dirname(spill)
        self._safe_run(
            self._ssh_argv(
                f"mkdir -p {shlex.quote(parent)} && cat > {shlex.quote(spill)}"
            ),
            input_bytes=blob,
        )

    # -- files --

    def put_file(self, path: str, content: bytes) -> None:
        """Write ``content`` into the remote workspace (confined)."""
        remote = self._confine(path)
        parent = posixpath.dirname(remote)
        rc, _out, err, _capped, hung = self._run(
            self._ssh_argv(
                f"mkdir -p {shlex.quote(parent)} && cat > {shlex.quote(remote)}"
            ),
            input_bytes=content,
            deadline_s=_CONTROL_DEADLINE_S,
        )
        if hung or rc != 0:
            raise RuntimeError(
                f"put_file failed for {path!r}: {err.decode('utf-8', 'replace')}"
            )

    def get_file(self, path: str) -> bytes:
        """Read ``path`` from the remote workspace (confined)."""
        remote = self._confine(path)
        rc, out, err, _capped, hung = self._run(
            self._ssh_argv(f"cat {shlex.quote(remote)}"),
            deadline_s=_CONTROL_DEADLINE_S,
        )
        if hung or rc != 0:
            raise RuntimeError(
                f"get_file failed for {path!r}: {err.decode('utf-8', 'replace')}"
            )
        return bytes(out)

    def _confine(self, path: str) -> str:
        """Resolve ``path`` within the remote workspace root or raise.

        Lexical (posix) confinement only — a remote ``realpath`` per call is a
        round-trip we skip on a disposable box; a remote symlink escape is out of
        scope for v1 (documented). ``..`` traversal is rejected.
        """
        if self._remote_root is None:
            raise RuntimeError("sandbox not started")
        root = self._remote_root
        candidate = (
            path if posixpath.isabs(path) else posixpath.join(root, path)
        )
        normalized = posixpath.normpath(candidate)
        if normalized != root and not normalized.startswith(root + "/"):
            raise PolicyDenied(f"path escapes the workspace: {path}")
        return normalized

    # -- subprocess seam (mocked in unit tests) --

    def _safe_run(self, argv: List[str], *, input_bytes: bytes = b"") -> None:
        """Run a best-effort control call, swallowing every failure."""
        try:
            self._run(
                argv, input_bytes=input_bytes, deadline_s=_CONTROL_DEADLINE_S
            )
        except Exception as error:  # best-effort; never disrupt teardown/setup
            logger.debug("ssh control call failed: %s", error)

    def _run(
        self,
        argv: List[str],
        *,
        input_bytes: bytes = b"",
        deadline_s: float,
    ) -> Tuple[int, bytes, bytes, bool, bool]:
        """Run ``argv``, feed ``input_bytes`` on stdin, drain under a cap+deadline.

        Returns ``(returncode, stdout, stderr, capped, hung)``. Output is drained
        in reader threads bounded by :data:`_MAX_CAPTURE_BYTES`; the process is
        killed on the cap or the deadline (``hung``), so a stalled connection or
        a runaway can never block the caller.
        """
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out = bytearray()
        err = bytearray()
        total = [0]
        capped = threading.Event()

        def feed() -> None:
            try:
                if proc.stdin is not None:
                    proc.stdin.write(input_bytes)
                    proc.stdin.close()
            except OSError:  # peer closed stdin early
                pass

        def reader(stream: object, buf: bytearray) -> None:
            try:
                while True:
                    chunk = stream.read(65536)  # type: ignore[attr-defined]
                    if not chunk:
                        break
                    total[0] += len(chunk)
                    room = _MAX_CAPTURE_BYTES - len(buf)
                    if room > 0:
                        buf.extend(chunk[:room])
                    if total[0] > _MAX_CAPTURE_BYTES:
                        capped.set()
                        break
            except (OSError, ValueError):  # pipe closed under us
                pass

        threads = [threading.Thread(target=feed, daemon=True)]
        for stream, buf in ((proc.stdout, out), (proc.stderr, err)):
            if stream is not None:
                threads.append(
                    threading.Thread(
                        target=reader, args=(stream, buf), daemon=True
                    )
                )
        for thread in threads:
            thread.start()

        hung = False
        deadline = time.monotonic() + deadline_s
        while True:
            if proc.poll() is not None:
                break
            if capped.is_set():
                proc.kill()
                break
            if time.monotonic() >= deadline:
                hung = True
                proc.kill()
                break
            time.sleep(0.02)
        for thread in threads:
            thread.join(timeout=0.5)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:  # pragma: no cover - escaped child
            pass

        rc = proc.returncode if proc.returncode is not None else -1
        return rc, bytes(out), bytes(err), capped.is_set(), hung
