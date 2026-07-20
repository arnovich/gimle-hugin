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
- **A partition is not silently retried** — the remote wrapper prints a
  completion sentinel (``__HUGIN_EXIT_…=<code>``) *after* the command. Its
  presence means the command ran to completion and we trust the exit code it
  carries (even ``255``, which a remote command may legitimately return);
  its *absence* means the connection dropped mid-command, so we raise a clear
  do-not-retry error rather than re-running a command whose fate is unknown (a
  half-run ``rm``/``git push`` must not be blindly repeated). This distinguishes
  a real ssh transport failure from a command that merely exited 255, which a
  bare ``rc == 255`` check cannot.

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
import re
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
    fsize_ulimit_blocks,
    new_spill_relpath,
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
# connection) — but a remote command can *also* exit 255, so ``rc == 255`` alone
# is ambiguous. We disambiguate with the completion sentinel below rather than
# this exit code.
SSH_TRANSPORT_EXIT = 255

# The remote wrapper prints this (with the command's ``$?``) *after* the command
# returns. Seeing it in stdout proves the command completed and tells us the real
# exit code; not seeing it (and not having truncated output) proves the
# connection dropped mid-command. The random-looking suffix makes an accidental
# collision with a command's own output astronomically unlikely, and we always
# read the *last* occurrence, which is the wrapper's.
_EXIT_SENTINEL = "__HUGIN_EXIT_b9f2c1a4__"
# Matched against raw bytes (not decoded text) so byte-exact output — including
# invalid UTF-8 — is preserved for the spill file.
_SENTINEL_RE = re.compile(
    rb"\n" + re.escape(_EXIT_SENTINEL.encode("ascii")) + rb"=(-?\d+)\n?$"
)


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
        self._port = spec.port
        # Our ControlMaster socket lives in a per-user 0700 directory under the
        # system temp dir (so another local user cannot connect to or hijack the
        # multiplexed session), under a short collision-resistant name (unix
        # socket paths have a ~104-char limit).
        self._control_dir = os.path.join(
            tempfile.gettempdir(), f"hugin-ssh-{os.getuid()}"
        )
        digest = hashlib.sha256(
            f"{session_id}|{spec.host}".encode("utf-8")
        ).hexdigest()[:12]
        self._control_path = os.path.join(self._control_dir, f"cm-{digest}")
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
        if self._port:
            opts += ["-p", str(self._port)]
        return opts

    def _ssh_argv(self, remote_command: str) -> List[str]:
        """Return the full ``ssh`` argv running ``remote_command`` on the host."""
        return ["ssh", *self._ssh_opts(), self._host, remote_command]

    def _remote_wrapper(self, remote_cwd: str, timeout_s: int) -> str:
        """Return the remote shell string that runs the stdin command safely.

        Touch the session root first so its mtime stays fresh and the TTL sweep
        never reaps a long-lived active session (nested writes do *not* refresh
        the root dir's mtime, so this heartbeat is what protects it). Then cd
        into the workspace, scrub the environment (``env -i`` — no inherited
        remote secrets — with ``HOME`` at the workspace), and run under a remote
        ``timeout`` so the job is bounded/killable. The untrusted command is read
        from stdin (``bash -c "$(cat)"``) so it never passes through a second
        shell-quoting layer. Finally print the completion sentinel carrying the
        command's ``$?`` — its presence is how :meth:`exec` distinguishes a
        completed command (any exit code, including 255) from a dropped
        connection.
        """
        q_cwd = shlex.quote(remote_cwd)
        touch = ""
        if self._remote_root:
            touch = f"touch {shlex.quote(self._remote_root)} 2>/dev/null; "
        # Cap any single file the command writes (rlimits inherit across
        # ``env -i`` and ``exec``, so this bounds the command even though the env
        # is scrubbed) — a runaway ``yes > f`` can't fill the remote disk.
        fsize = f"ulimit -f {fsize_ulimit_blocks()} 2>/dev/null; "
        return (
            f"{fsize}"
            f"{touch}"
            f"cd {q_cwd} && "
            f"env -i HOME={q_cwd} PATH=/usr/local/bin:/usr/bin:/bin "
            f"LANG=C.UTF-8 TERM=dumb "
            f'timeout -k {_KILL_AFTER_S} {int(timeout_s)} bash -c "$(cat)"; '
            f"printf '\\n{_EXIT_SENTINEL}=%s\\n' \"$?\""
        )

    def _remote_start_script(self) -> str:
        """Return the one-shot remote script: TTL-sweep, create root, stamp owner.

        Sweeps sibling session dirs not modified within the TTL. An active
        session is protected because every :meth:`exec` touches its root (see
        :meth:`_remote_wrapper`) — a nested file write alone would *not* refresh
        the root dir's mtime, so the heartbeat touch is load-bearing here.
        (Re)creates this session's root, writes the owner marker (base64 so no
        quoting games), and prints the resolved absolute root path for the caller
        to capture.
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

    def _provision_host(self) -> str:
        """Return the host to connect to (the provisioner seam for Option B).

        v1 (Option A / BYO host) connects to the operator-supplied host as-is.
        A future managed-VM provisioner (Option B — see the design note)
        overrides this to create a fresh VM per session and return its address,
        pairing with :meth:`_destroy_host` on teardown. Kept as an explicit,
        no-op seam so the backend does not need reshaping when B lands.
        """
        return self._host

    def _destroy_host(self) -> None:
        """Tear down a host created by :meth:`_provision_host` (Option B seam).

        No-op under Option A: Hugin never created the machine, so it must never
        destroy it (and therefore cannot leak a VM). A future provisioner
        overrides this to reap the VM it created.
        """

    def _prepare_control_dir(self) -> None:
        """Create the 0700 ControlMaster dir and clear a stale socket.

        The per-user directory keeps other local users out of the multiplexed
        session. A leftover socket from an abrupt prior run against the same
        (session, host) is removed first — session ids are unique per process,
        so no live peer can own it.
        """
        try:
            os.makedirs(self._control_dir, exist_ok=True)
            os.chmod(self._control_dir, 0o700)
        except OSError as error:
            logger.debug("could not prepare control dir: %s", error)
        try:
            if os.path.exists(self._control_path):
                os.remove(self._control_path)
        except OSError as error:  # best-effort
            logger.debug("could not remove stale control socket: %s", error)

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
        self._host = self._provision_host()
        self._prepare_control_dir()
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
            # Best-effort. This matches the wrapper process by its unique root
            # path, so it kills the current command's wrapper — but the real
            # bound on a runaway is the remote ``timeout`` the wrapper runs
            # under (a backgrounded child that reparented away escapes ``pkill``
            # and is bounded only by that timeout and the box's disposal).
            # Documented in the design note.
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
        self._destroy_host()
        self._started = False

    # -- workspaces --

    def _agent_root(self, agent_id: str, branch: Optional[str]) -> str:
        """Compute the remote ``(agent, branch)`` path (pure, no remote I/O).

        ``agent_id`` and ``branch`` can carry LLM-chosen text (e.g. a
        ``create_branch`` name), so both are reduced to a single safe path
        component — :func:`_safe_component` maps ``/`` to ``-``, which alone
        defeats traversal — and the joined path is re-checked to be strictly
        under the session root.
        """
        if self._remote_root is None:
            raise RuntimeError("sandbox not started")
        agent = _safe_component(agent_id) or "agent"
        leaf = _safe_component(branch or "default") or "default"
        path = posixpath.normpath(
            posixpath.join(self._remote_root, "agents", agent, leaf)
        )
        if not path.startswith(self._remote_root + "/agents/"):
            raise PolicyDenied(
                f"invalid agent/branch workspace: {agent_id!r}/{branch!r}"
            )
        return path

    def workspace_for(self, agent_id: str, branch: Optional[str]) -> str:
        """Return the remote ``(agent, branch)`` path, creating it once."""
        path = self._agent_root(agent_id, branch)
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
        a network partition (the command did not complete over the connection —
        not safe to retry). A remote wall-clock timeout / OOM is reported in the
        result, not raised.

        The outcome is decided by the completion sentinel the remote wrapper
        prints after the command, not by ssh's own exit code:

        - **Sentinel present** → the command completed; trust the exit code it
          carries (even ``255``). ``hung`` in this case only means a backgrounded
          remote child kept the pipe open past the deadline — the command itself
          still finished, so it is *not* a partition.
        - **Sentinel absent, output truncated** → the command ran but its tail
          (including the sentinel) was past the byte cap; treat as completed with
          an unknown exit code.
        - **Sentinel absent, not truncated** → the connection dropped
          mid-command (transport failure or a wedged pipe hitting the deadline);
          raise a do-not-retry error.
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
        _rc, out_bytes, err_bytes, capped, hung = self._run(
            argv, input_bytes=command.encode("utf-8"), deadline_s=host_deadline
        )
        duration = time.monotonic() - started

        stdout_bytes, remote_exit = self._extract_sentinel(out_bytes)
        if remote_exit is None and not capped:
            # No completion sentinel and the output was not truncated: the
            # command did not finish over the connection (a real ssh transport
            # failure, or a pipe that wedged until the host deadline). Its remote
            # effect is unknown, so refuse to retry rather than double-execute.
            raise RuntimeError(
                f"ssh transport error to {self._host!r}: the command did not "
                "complete over the connection; do not retry (its remote effect "
                "is unknown)"
            )
        # Sentinel absent but output was capped → the command ran; we just lost
        # its exit code past the byte cap. Report an unknown (-1) exit.
        exit_code = remote_exit if remote_exit is not None else -1

        # A completed command is never a partition, so classify timeout/OOM on
        # the real exit code alone (hung here is only a lingering background
        # child, not an abandonment).
        timed_out, oom_killed = classify_timeout_exit(
            exit_code, False, duration, effective_timeout
        )
        stdout_raw = stdout_bytes.decode("utf-8", "replace")
        stderr_raw = err_bytes.decode("utf-8", "replace")
        if capped:
            stderr_raw += (
                f"\n[hugin: output exceeded {_MAX_CAPTURE_BYTES} bytes; "
                "stopped reading]"
            )
        if hung:
            stderr_raw += (
                "\n[hugin: command finished but left a background process "
                "holding its output stream on the remote]"
            )

        out, out_trunc = truncate_output(stdout_raw, max_output_bytes)
        err, err_trunc = truncate_output(stderr_raw, max_output_bytes)
        truncated = out_trunc or err_trunc or capped
        spill_path = (
            self._spill_remote(cwd, stdout_bytes, err_bytes)
            if truncated
            else None
        )

        return ExecResult(
            exit_code=exit_code,
            stdout=out,
            stderr=err,
            duration_s=duration,
            truncated=truncated,
            timed_out=timed_out,
            oom_killed=oom_killed,
            output_capped=capped,
            spill_path=spill_path,
        )

    @staticmethod
    def _extract_sentinel(out_bytes: bytes) -> Tuple[bytes, Optional[int]]:
        """Split the completion sentinel off stdout.

        Returns ``(stdout_without_sentinel, exit_code)``; ``exit_code`` is
        ``None`` when no sentinel is present (a dropped connection). The wrapper
        prints a newline-delimited ``<sentinel>=<code>`` as the *last* thing on
        stdout, so we anchor the match at the end — the command's own stdout
        (even if it happens to contain the marker earlier) is preserved ahead of
        it.
        """
        match = _SENTINEL_RE.search(out_bytes)
        if match is None:
            return out_bytes, None
        return out_bytes[: match.start()], int(match.group(1))

    def _spill_remote(
        self, remote_cwd: str, stdout: bytes, stderr: bytes
    ) -> Optional[str]:
        """Write the full output to the remote workspace so the agent can read it.

        Returns the absolute remote path written (readable from any cwd), or None
        if the best-effort write failed — never fails the command over it.
        """
        blob = stdout
        if stderr:
            blob = blob + b"\n--- stderr ---\n" + stderr
        spill = posixpath.join(remote_cwd, new_spill_relpath())
        parent = posixpath.dirname(spill)
        try:
            self._safe_run(
                self._ssh_argv(
                    f"mkdir -p {shlex.quote(parent)} && "
                    f"cat > {shlex.quote(spill)}"
                ),
                input_bytes=blob,
            )
            return spill
        except (
            Exception
        ) as error:  # best-effort; never fail the command over it
            logger.debug("could not spill full output remotely: %s", error)
            return None

    # -- files --

    def put_file(
        self, agent_id: str, branch: Optional[str], path: str, content: bytes
    ) -> None:
        """Write ``content`` into the agent's remote workspace (confined)."""
        remote = self._confine(agent_id, branch, path)
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

    def get_file(
        self, agent_id: str, branch: Optional[str], path: str
    ) -> bytes:
        """Read ``path`` from the agent's remote workspace (confined).

        Raises rather than return a truncated file: the read goes through the
        byte-capped ``_run`` seam, so a file larger than
        :data:`_MAX_CAPTURE_BYTES` (or a stalled read) must surface as an error,
        never as silently short bytes a caller would mistake for the whole file.
        """
        remote = self._confine(agent_id, branch, path)
        rc, out, err, capped, hung = self._run(
            self._ssh_argv(f"cat {shlex.quote(remote)}"),
            deadline_s=_CONTROL_DEADLINE_S,
        )
        if capped:
            raise RuntimeError(
                f"get_file: {path!r} exceeds the {_MAX_CAPTURE_BYTES}-byte "
                "transfer cap; read it in chunks or via a smaller slice"
            )
        if hung or rc != 0:
            raise RuntimeError(
                f"get_file failed for {path!r}: {err.decode('utf-8', 'replace')}"
            )
        return bytes(out)

    def _confine(self, agent_id: str, branch: Optional[str], path: str) -> str:
        """Resolve ``path`` within the ``(agent, branch)`` remote workspace, or raise.

        Confined to the *agent's own* workspace (not the whole session), so a
        traversal into a sibling agent's tree is refused. Lexical (posix)
        confinement only — a remote ``realpath`` per call is a round-trip we skip
        on a disposable box; a remote symlink escape is out of scope for v1
        (documented). ``..`` traversal is rejected.
        """
        root = self._agent_root(agent_id, branch)
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
        lock = threading.Lock()

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
                    # The two reader threads share ``total`` and the cap check;
                    # guard both so the combined-stream cap is enforced exactly.
                    with lock:
                        total[0] += len(chunk)
                        room = _MAX_CAPTURE_BYTES - len(buf)
                        if room > 0:
                            buf.extend(chunk[:room])
                        over = total[0] > _MAX_CAPTURE_BYTES
                    if over:
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
