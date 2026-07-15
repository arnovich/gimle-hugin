"""``DockerSandbox`` — run commands inside a hardened, throwaway container.

This is the first backend with a *real* isolation boundary. The container — not
the policy allowlist — is what makes running an interpreter safe: a denylist by
design lets ``python3 -c '...'`` through, and the whole point is that it can,
because the runtime contains it. Every hardening flag below is therefore
**mandatory** when this backend is chosen (no network, all caps dropped,
no-new-privileges, read-only root, resource caps, non-root user, no docker
socket) — they are not tuning knobs, they are the boundary.

The ``docker`` SDK is imported lazily, inside methods, so a user who never
selects this backend needs neither the library nor a daemon: ``local`` and
``ssh`` stay true peers. Selecting ``backend: docker`` without the ``sandbox``
extra installed fails with a clear remediation message at ``start()``.

Workspace model: the session's host directory (``<workspace_root>/<session>``)
is bind-mounted to ``/workspace`` in the container, so the existing host-side
machinery — per-``(agent, branch)`` directories, output spill, ``put_file`` /
``get_file``, and the startup reaper's filesystem GC — all keep working
unchanged, and a resumed session reattaches its files instead of getting an
empty container. The container runs as the host user so those files stay
host-readable.
"""

import logging
import os
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from gimle.hugin.sandbox.local import (
    OWNER_FILE,
    process_start_time,
)
from gimle.hugin.sandbox.policy import Allow, Policy, evaluate
from gimle.hugin.sandbox.sandbox import (
    DEFAULT_SANDBOX_ROOT,
    ExecResult,
    PolicyDenied,
    Sandbox,
    SandboxSpec,
    truncate_output,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from docker.models.containers import Container

logger = logging.getLogger(__name__)

# The image ships thick and boring on purpose (see docker/sandbox.Dockerfile):
# a missing binary is a wasted agent turn. Override per-config with ``image:``.
DEFAULT_IMAGE = "gimle/hugin-sandbox:latest"

# The container's single writable, bind-mounted tree; the host side is
# ``<workspace_root>/<session_id>``.
CONTAINER_WORKSPACE = "/workspace"

_NAME_PREFIX = "hugin-sbx-"
_SPILL_RELATIVE = os.path.join(".hugin", "last_output.txt")

# Container labels the reaper reads to decide abandonment (mirrors the local
# backend's owner stamp: PID + process-incarnation token, never session alone).
LABEL_SESSION = "hugin.session"
LABEL_OWNER_PID = "hugin.owner_pid"
LABEL_OWNER_START = "hugin.owner_start"
LABEL_CREATED = "hugin.created"
LABEL_TTL = "hugin.ttl"

# Backstop lifetime for a container whose owner we can no longer positively
# identify (PID reused, start-time unreadable). Owner-liveness is the primary
# signal; this only bounds the pathological case.
DEFAULT_TTL_S = 24 * 3600

# Hard ceiling on output buffered per command (matches LocalSandbox): a runaway
# ``yes`` must not OOM the orchestrator. On hitting it we stop draining; the
# container's pipe buffer fills, the writer blocks, and the in-container
# ``timeout`` kills it.
_MAX_CAPTURE_BYTES = 2_000_000

# Grace after the wall-clock timeout before the in-container ``timeout`` sends
# SIGKILL (so a process ignoring SIGTERM cannot hang past its limit).
_KILL_AFTER_S = 5


def import_docker() -> Any:
    """Import and return the docker SDK module, typed ``Any`` for callers.

    Central lazy entry point for the SDK: returning the module as ``Any`` keeps
    every ``docker.from_env()`` / ``docker.errors`` call site free of mypy
    attribute noise, and keeps the import in one place so ``local``/``ssh`` never
    pull it in. Raises ``ImportError`` if the optional ``sandbox`` extra is
    absent; callers translate that into a remediation message or a no-op.
    """
    import docker

    return docker


def _sanitize_name(session_id: str) -> str:
    """Return a docker-legal container name for ``session_id``."""
    safe = "".join(
        c if (c.isalnum() or c in "_.-") else "-" for c in session_id
    )
    return f"{_NAME_PREFIX}{safe}"


class DockerSandbox(Sandbox):
    """Execute commands inside one hardened, session-scoped container."""

    def __init__(
        self,
        spec: SandboxSpec,
        session_id: str,
        workspace_root: str = DEFAULT_SANDBOX_ROOT,
    ) -> None:
        """Bind this sandbox to ``session_id``'s container and host workspace."""
        self._spec = spec
        self._session_id = session_id
        self._host_root = os.path.abspath(
            os.path.join(workspace_root, session_id)
        )
        self._name = _sanitize_name(session_id)
        self._image = spec.image or DEFAULT_IMAGE
        self._client: Any = None
        self._container: Optional["Container"] = None

    # -- docker SDK access (lazy) --

    def _docker(self) -> Any:
        """Import the docker SDK on demand, or raise a clear remediation error.

        Kept out of module import so selecting ``local`` / ``ssh`` never needs
        the library; the error names the extra to install.
        """
        try:
            return import_docker()
        except ImportError as error:  # pragma: no cover - env-dependent
            raise RuntimeError(
                "the docker backend needs the 'docker' SDK; install it with "
                '`pip install "gimle-hugin[sandbox]"` (or `uv pip install '
                "docker>=7.1`)"
            ) from error

    # -- lifecycle --

    def start(self) -> None:
        """Create or reattach the session container; refresh its liveness stamp.

        Idempotent: a running container is reused (resume reattaches the same
        bind-mounted files), a stopped one is restarted, and only a missing one
        is created with the mandatory hardening flags. Also writes the host-side
        owner stamp so the filesystem reaper treats this exactly like a local
        workspace.
        """
        docker = self._docker()
        if self._client is None:
            self._client = docker.from_env()
        os.makedirs(self._host_root, exist_ok=True)
        self._write_owner_stamp()

        container = self._existing_container()
        if container is None:
            container = self._create_container(docker)
        elif container.status != "running":
            container.start()
        self._container = container
        self._touch_heartbeat()

    def _existing_container(self) -> Optional["Container"]:
        """Return the session's container if one already exists, else None."""
        docker = self._docker()
        try:
            return self._client.containers.get(self._name)
        except docker.errors.NotFound:
            return None

    def _create_container(self, docker: Any) -> "Container":
        """Create and start the hardened container from ``_container_kwargs``."""
        kwargs = self._container_kwargs()
        kwargs["ulimits"] = [
            docker.types.Ulimit(name=name, soft=soft, hard=hard)
            for (name, soft, hard) in kwargs["ulimits"]
        ]
        return self._client.containers.run(self._image, **kwargs)

    def _container_kwargs(self) -> Dict[str, Any]:
        """Build the container-creation kwargs — the whole hardening contract.

        Pure and SDK-free (``ulimits`` are plain ``(name, soft, hard)`` tuples,
        finalized into ``docker.types.Ulimit`` in :meth:`_create_container`) so
        the flags can be asserted in a unit test without a daemon. Every value
        here is load-bearing for containment; changing one weakens the boundary.
        """
        uid_gid = self._host_uid_gid()
        return {
            "name": self._name,
            "command": ["sleep", "infinity"],  # idle PID; we exec per command
            "detach": True,
            "init": True,  # PID 1 reaps double-forked children (local can't)
            # No network at all unless the operator opts in; the default is the
            # safe path (a container that cannot reach the metadata endpoint).
            "network_mode": "bridge" if self._spec.network else "none",
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "read_only": True,  # rootfs is immutable; only the mounts below write
            "tmpfs": {"/tmp": "rw,noexec,nosuid,size=256m"},
            "mem_limit": self._spec.memory,
            "nano_cpus": int(self._spec.cpu * 1_000_000_000),
            "pids_limit": self._spec.pids,
            "ulimits": [
                ("nofile", 1024, 4096),
                ("nproc", self._spec.pids, self._spec.pids),
            ],
            # Run as the host user so bind-mounted files stay host-readable and
            # the process is provably non-root inside the container.
            "user": uid_gid,
            "hostname": "sandbox",
            "working_dir": CONTAINER_WORKSPACE,
            # Empty of inherited secrets; HOME is set per-command to the agent's
            # own workspace in exec().
            "environment": {
                "HOME": CONTAINER_WORKSPACE,
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "TERM": "dumb",
            },
            "volumes": {
                self._host_root: {"bind": CONTAINER_WORKSPACE, "mode": "rw"}
            },
            "labels": self._labels(),
        }

    @staticmethod
    def _host_uid_gid() -> str:
        """Return ``"uid:gid"`` of the host user (``"0:0"`` where unavailable)."""
        getuid = getattr(os, "getuid", None)
        getgid = getattr(os, "getgid", None)
        if getuid is None or getgid is None:  # pragma: no cover - non-POSIX
            return "0:0"
        return f"{getuid()}:{getgid()}"

    def _labels(self) -> Dict[str, str]:
        """Labels the container reaper reads to find and judge abandonment."""
        pid = os.getpid()
        return {
            LABEL_SESSION: self._session_id,
            LABEL_OWNER_PID: str(pid),
            LABEL_OWNER_START: process_start_time(pid) or "",
            LABEL_CREATED: str(int(time.time())),
            LABEL_TTL: str(DEFAULT_TTL_S),
        }

    def _write_owner_stamp(self) -> None:
        """Stamp the host workspace with the live owner (reused by the reaper).

        Mirrors ``LocalSandbox``: rewritten every ``start()`` with the current
        PID + start time, so a resumed session (new process, same id) is not
        mistaken for a dead one and swept out from under itself.
        """
        import json

        stamp = os.path.join(self._host_root, OWNER_FILE)
        pid = os.getpid()
        record = {
            "pid": pid,
            "start_time": process_start_time(pid),
            "created": time.time(),
        }
        try:
            with open(stamp, encoding="utf-8") as handle:
                existing = json.load(handle)
            if isinstance(existing, dict) and "created" in existing:
                record["created"] = existing["created"]
        except (OSError, ValueError):
            pass
        try:
            with open(stamp, "w", encoding="utf-8") as handle:
                json.dump(record, handle)
        except (
            OSError
        ) as error:  # best-effort; the reaper falls back to age/TTL
            logger.debug("could not write owner stamp: %s", error)

    def _touch_heartbeat(self) -> None:
        """Touch a host-side heartbeat file each start (a TTL freshness signal)."""
        try:
            beat = os.path.join(self._host_root, ".hugin", "heartbeat")
            os.makedirs(os.path.dirname(beat), exist_ok=True)
            with open(beat, "w", encoding="utf-8") as handle:
                handle.write(str(time.time()))
        except OSError as error:  # best-effort
            logger.debug("could not touch heartbeat: %s", error)

    def stop(self) -> None:
        """Stop and remove the container. Idempotent; safe if never started.

        Unlike ``local`` (whose ``stop`` is a no-op), this releases a real
        resource, so a clean exit does not leak a container. The reaper is the
        backstop for an abrupt exit that skips this. The bind-mounted host
        directory is intentionally left for the filesystem reaper / resume.
        """
        container = self._container
        if container is None:
            return
        try:
            container.stop(timeout=5)
        except Exception as error:  # already gone / daemon down — nothing to do
            logger.debug("container stop failed: %s", error)
        try:
            container.remove(force=True, v=False)
        except Exception as error:  # remove is best-effort; reaper is the net
            logger.debug("container remove failed: %s", error)
        self._container = None

    # -- workspaces --

    def workspace_for(self, agent_id: str, branch: Optional[str]) -> str:
        """Return the container path for ``(agent, branch)``; create it host-side.

        The returned path is a **container** path under ``/workspace``; the
        matching host directory (visible in the container through the bind
        mount) is created so a command has somewhere to run.
        """
        rel = os.path.join("agents", agent_id, branch or "default")
        os.makedirs(os.path.join(self._host_root, rel), exist_ok=True)
        return f"{CONTAINER_WORKSPACE}/{rel}"

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
        """Run ``command`` in the container; enforce policy fail-closed.

        Policy is a guardrail against accidents, not the boundary — but it is
        still enforced here so no route to ``exec`` runs unchecked. The command
        is wrapped in the container's own ``timeout`` so a hang or a
        SIGTERM-ignoring loop cannot outlive its limit even if the caller stops
        reading its output.
        """
        decision = evaluate(command, policy)
        if not isinstance(decision, Allow):
            raise PolicyDenied(getattr(decision, "reason", "command refused"))
        if self._container is None:
            raise RuntimeError("sandbox not started")

        effective_timeout = min(timeout_s, policy.max_timeout_s)
        wrapped = [
            "timeout",
            "-k",
            str(_KILL_AFTER_S),
            str(effective_timeout),
            "bash",
            "-c",
            command,
        ]
        env = {
            "HOME": cwd,
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "TERM": "dumb",
        }

        started = time.monotonic()
        exit_code, stdout_raw, stderr_raw, capped = self._exec_capture(
            wrapped, cwd, env
        )
        duration = time.monotonic() - started

        # `timeout` reports 124 on a wall-clock timeout; a child SIGKILLed
        # before that (a memory-cap OOM kill is the common cause) surfaces as
        # 137. The 137->OOM mapping is a documented heuristic, not certainty.
        timed_out = exit_code == 124
        oom_killed = exit_code == 137
        if capped:
            stderr_raw += (
                f"\n[hugin: output exceeded {_MAX_CAPTURE_BYTES} bytes; "
                "stopped reading]"
            )

        out, out_trunc = truncate_output(stdout_raw, max_output_bytes)
        err, err_trunc = truncate_output(stderr_raw, max_output_bytes)
        truncated = out_trunc or err_trunc or capped
        if truncated:
            self._spill(cwd, stdout_raw, stderr_raw)

        return ExecResult(
            exit_code=exit_code,
            stdout=out,
            stderr=err,
            duration_s=duration,
            truncated=truncated,
            timed_out=timed_out,
            oom_killed=oom_killed,
        )

    def _exec_capture(
        self, cmd: List[str], cwd: str, env: Dict[str, str]
    ) -> Tuple[int, str, str, bool]:
        """Stream one exec, capping buffered bytes; return code, out, err, capped.

        Uses the low-level exec API so output can be drained incrementally and
        stopped at :data:`_MAX_CAPTURE_BYTES` — past the cap we stop reading and
        let the in-container ``timeout`` end the process, bounding host memory
        the same way ``LocalSandbox`` does.
        """
        assert (
            self._container is not None
        )  # exec() guarantees a started sandbox
        api = self._client.api
        exec_id = api.exec_create(
            self._container.id,
            cmd,
            workdir=cwd,
            environment=env,
            user=self._host_uid_gid(),
        )["Id"]
        stream = api.exec_start(exec_id, stream=True, demux=True)

        out = bytearray()
        err = bytearray()
        total = 0
        capped = False
        for stdout_chunk, stderr_chunk in stream:
            for chunk, buf in (
                (stdout_chunk, out),
                (stderr_chunk, err),
            ):
                if not chunk:
                    continue
                total += len(chunk)
                room = _MAX_CAPTURE_BYTES - len(buf)
                if room > 0:
                    buf.extend(chunk[:room])
            if total > _MAX_CAPTURE_BYTES:
                capped = True
                break

        info = api.exec_inspect(exec_id)
        exit_code = info.get("ExitCode")
        if exit_code is None:  # still running (we stopped draining on the cap)
            exit_code = -1
        return (
            exit_code,
            bytes(out).decode("utf-8", "replace"),
            bytes(err).decode("utf-8", "replace"),
            capped,
        )

    def _spill(self, cwd: str, stdout: str, stderr: str) -> None:
        """Write full output host-side so the agent can read past the cap.

        ``cwd`` is a container path under ``/workspace``; it maps to the host
        bind-mount root, so the file is visible both to the host and, at the
        same relative path, to the agent inside the container.
        """
        try:
            host_cwd = self._host_path(cwd)
            spill_path = os.path.join(host_cwd, _SPILL_RELATIVE)
            os.makedirs(os.path.dirname(spill_path), exist_ok=True)
            with open(spill_path, "w", encoding="utf-8") as handle:
                handle.write(stdout)
                if stderr:
                    handle.write("\n--- stderr ---\n")
                    handle.write(stderr)
        except OSError as error:  # best-effort; never fail the command over it
            logger.debug("could not spill full output: %s", error)

    def _host_path(self, container_path: str) -> str:
        """Map a ``/workspace/...`` container path to its host bind-mount path."""
        rel = os.path.relpath(container_path, CONTAINER_WORKSPACE)
        return os.path.normpath(os.path.join(self._host_root, rel))

    # -- files --

    def put_file(self, path: str, content: bytes) -> None:
        """Write ``content`` into the workspace (host-side, confined)."""
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
        """Resolve ``path`` within the host workspace root or raise PolicyDenied.

        Accepts either a container ``/workspace/...`` path or a host/relative
        one, mapping the former to the host side first, then realpath-checks the
        result so a symlink planted in the workspace cannot point outside it.
        """
        if path == CONTAINER_WORKSPACE or path.startswith(
            CONTAINER_WORKSPACE + "/"
        ):
            path = self._host_path(path)
        root = os.path.realpath(self._host_root)
        candidate = path if os.path.isabs(path) else os.path.join(root, path)
        resolved = os.path.realpath(candidate)
        if resolved != root and not resolved.startswith(root + os.sep):
            raise PolicyDenied(f"path escapes the workspace: {path}")
        return resolved
