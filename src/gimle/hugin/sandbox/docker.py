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

Two honest limits of this backend's isolation, both dependent on host/daemon
configuration this code cannot set per-container:

- **No userns-remap here.** The container process runs as the host uid, which
  makes it non-root *inside* the container but does not remap container-root to
  a subuid. True userns-remap is a daemon-level setting; enable it on the docker
  daemon for defence in depth. As a fail-closed guard, ``start()`` refuses to
  run as uid 0 unless the daemon has userns-remap on (else container-root would
  equal host-root).
- **``network: true`` requires an egress policy (three postures).** The default
  (``network: false``) is the safe path — no network at all. Opting in needs one
  of: **filtered** egress (a non-empty ``egress_allowlist``) — the sandbox joins
  a per-session *internal* network with no direct route out, and its only exit
  is a dual-homed proxy sidecar that permits only the allowlisted hosts and
  blocks link-local/metadata (169.254.169.254) + private ranges (the
  recommended path, task 033); or **unrestricted** egress
  (``allow_unrestricted_egress: true``) — the default bridge, unfiltered, which
  warns. Anything else is **refused** (fail-closed): an unfiltered bridge would
  reach the metadata endpoint and exfiltrate IAM credentials. The proxy sidecar
  + internal network are per-session resources cleaned up by ``stop()`` and the
  reaper, exactly like the sandbox container. See ``egress_proxy.py``.
"""

import hashlib
import logging
import os
import posixpath
import threading
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from gimle.hugin.sandbox import egress_proxy
from gimle.hugin.sandbox.local import (
    OWNER_FILE,
    boot_id,
    current_hostname,
    process_start_time,
)
from gimle.hugin.sandbox.policy import Allow, Policy, evaluate
from gimle.hugin.sandbox.sandbox import (
    DEFAULT_SANDBOX_ROOT,
    ExecResult,
    PolicyDenied,
    Sandbox,
    SandboxSpec,
    classify_timeout_exit,
    new_spill_relpath,
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
_PROXY_PREFIX = "hugin-proxy-"
_EGRESS_NET_PREFIX = "hugin-egress-"

# The egress proxy listens here inside its sidecar; the sandbox's HTTP_PROXY
# points at ``http://<proxy-name>:<port>`` (resolved by the internal network's
# embedded DNS). The proxy script is bind-mounted here in the sidecar.
_PROXY_PORT = 8080
_PROXY_SCRIPT_HOST = os.path.abspath(egress_proxy.__file__)
_PROXY_SCRIPT_MOUNT = "/opt/egress_proxy.py"

# Warn once per process that network:true has unrestricted egress (see start()).
_network_warned = False

# Container labels the reaper reads to decide abandonment (mirrors the local
# backend's owner stamp: PID + process-incarnation token, never session alone).
LABEL_SESSION = "hugin.session"
LABEL_OWNER_PID = "hugin.owner_pid"
LABEL_OWNER_START = "hugin.owner_start"
LABEL_CREATED = "hugin.created"
LABEL_TTL = "hugin.ttl"
# Which host + boot created the container, so the reaper only judges an owner
# PID against the process table it actually belongs to: never another host's
# container (a shared daemon), and a prior boot's owner PID (recycled) is dead.
LABEL_HOST = "hugin.host"
LABEL_BOOT = "hugin.boot"

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

# Extra host-side slack on top of the in-container timeout before ``exec`` gives
# up waiting for output — covers SDK/daemon latency. The in-container ``timeout``
# should always fire first; this only backstops a wedged daemon or a command
# that backgrounded a child holding the output pipe (which ``timeout`` can't
# reach), so a bash call can never hang the agent's turn indefinitely.
_HOST_GRACE_S = 10

# How long to keep draining after the foreground process exits, for a lingering
# background child that still holds the pipe (mirrors LocalSandbox).
_DRAIN_GRACE_S = 0.5

# Short client timeout for the reaper's daemon calls so a wedged daemon can't
# stall every ``hugin`` startup (the reaper runs on each invocation).
REAPER_CLIENT_TIMEOUT_S = 5


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
    """Return a docker-legal name fragment for ``session_id``."""
    return "".join(
        c if (c.isalnum() or c in "_.-") else "-" for c in session_id
    )


def _identity_hash(session_id: str, spec: SandboxSpec) -> str:
    """Return a short stable hash of the raw session id and the spec.

    Folded into the container name for two reasons: two agents in one session
    with *different* specs (image / network / cpu / memory / pids / egress
    posture) must get *different* containers — an agent's hardening profile
    follows its own config, not whichever agent started a container first — and
    the *raw* session id is hashed (not just its sanitized fragment) so two ids
    that sanitize alike (``weird/id`` and ``weird-id`` both -> ``weird-id``)
    never collide onto one container.

    The egress posture (``egress_allowlist`` + ``allow_unrestricted_egress``) is
    part of the identity because it also names the *proxy* + *internal network*:
    two agents that differ only in their allowlist must not share one proxy (the
    allowlist is baked into the proxy at creation, so sharing would silently give
    the second agent the first's egress policy).
    """
    identity = "|".join(
        str(part)
        for part in (
            session_id,
            spec.image,
            spec.network,
            spec.egress_allowlist,
            spec.allow_unrestricted_egress,
            spec.cpu,
            spec.memory,
            spec.pids,
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]


def container_name(session_id: str, spec: SandboxSpec) -> str:
    """Return the docker container name for a ``(session, spec)`` pair."""
    fragment = _sanitize_name(session_id)[:40]
    return f"{_NAME_PREFIX}{fragment}-{_identity_hash(session_id, spec)}"


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
        self._name = container_name(session_id, spec)
        ident = _identity_hash(session_id, spec)
        self._proxy_name = f"{_PROXY_PREFIX}{ident}"
        self._egress_net_name = f"{_EGRESS_NET_PREFIX}{ident}"
        self._image = spec.image or DEFAULT_IMAGE
        self._client: Any = None
        self._container: Optional["Container"] = None
        self._proxy: Optional["Container"] = None
        self._started = False

    def _egress_filtered(self) -> bool:
        """Whether egress is filtered through the per-session allowlist proxy."""
        return bool(self._spec.network and self._spec.egress_allowlist)

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

        Idempotent. A container this same process owns is reused; a container
        left by a *dead* prior owner (a resume after an abrupt exit) is recreated
        so its immutable owner labels — which the reaper judges liveness by —
        refresh to this live process, and any changed hardening spec takes
        effect. Only a missing container is created fresh. Also writes the
        host-side owner stamp so the filesystem reaper treats this like a local
        workspace, and fails closed on an unsafe (root, no userns) configuration.
        """
        if self._started and self._container is not None:
            # A re-``get()`` on every command must not re-run ``images.get`` or
            # reassign ``self._container`` — a background worker may be reading it
            # mid-``exec`` (a data race). Only refresh the liveness heartbeat,
            # which is a host-side file write touching no shared handle.
            self._write_owner_stamp()
            return

        docker = self._docker()
        if self._client is None:
            self._client = docker.from_env()
        self._assert_not_unsafe_root()
        self._assert_egress_acknowledged()
        os.makedirs(self._host_root, exist_ok=True)
        self._write_owner_stamp()
        self._ensure_image()

        # Filtered egress: bring up the internal network + proxy sidecar *before*
        # the sandbox, so the sandbox joins the internal network (its only exit)
        # with the proxy already reachable. If anything from here on fails, tear
        # down the infra we just created — otherwise a per-session network +
        # proxy leak (and the network subnet pool is small).
        try:
            if self._egress_filtered():
                self._ensure_egress_infra(docker)

            container = self._existing_container()
            if container is not None and not self._owner_is_current(container):
                # A dead prior owner's container: its frozen labels name a dead
                # PID, so the reaper would treat this resumed (live) session as
                # abandoned. Recreate — the bind-mounted files persist, cheaply.
                self._remove_container(container)
                container = None
            if container is None:
                container = self._create_container(docker)
            elif container.status != "running":
                container.start()
        except Exception:
            # _remove_proxy_and_network never raises (guarded), so it can't mask
            # the original failure we re-raise.
            self._remove_proxy_and_network()
            raise
        self._container = container
        self._started = True

    def _assert_not_unsafe_root(self) -> None:
        """Fail closed if running as root without daemon userns-remap.

        Running as the host uid makes the container process non-root only when
        the orchestrator itself is non-root. If Hugin runs as root (CI, some
        servers), the sandbox would run as container-root — and without
        userns-remap container-root *is* host-root, so a single escape primitive
        is host root. Allowed only when the daemon has userns-remap on (which
        decouples them); otherwise refused with remediation.
        """
        if self._host_uid_gid() != "0:0":
            return
        try:
            security = self._client.info().get("SecurityOptions", []) or []
        except Exception:  # can't tell — fail closed
            security = []
        if any("userns" in str(opt) for opt in security):
            return
        raise RuntimeError(
            "refusing to run the docker sandbox as root without userns-remap: "
            "container-root would equal host-root. Run Hugin as a non-root "
            "user, or enable docker userns-remap on the daemon."
        )

    def _assert_egress_acknowledged(self) -> None:
        """Require an explicit egress policy for ``network: true``.

        The container has ``cap_drop=ALL`` (no in-container iptables), so egress
        is controlled at the network layer. ``network: true`` needs one of:

        - **filtered** — a non-empty ``egress_allowlist`` routes egress through a
          per-session proxy that permits only those hosts and blocks link-local/
          metadata + private ranges (the safe, recommended path); or
        - **unrestricted** — ``allow_unrestricted_egress: true`` explicitly
          accepts an unfiltered bridge (an injected command could read the
          metadata endpoint 169.254.169.254 and exfiltrate IAM credentials); it
          warns.

        Otherwise ``network: true`` is **refused** (fail-closed). The default
        ``network: false`` (no network) is untouched.
        """
        if not self._spec.network:
            return
        if self._egress_filtered():
            return  # filtered through the allowlist proxy
        if self._spec.allow_unrestricted_egress:
            global _network_warned
            if not _network_warned:
                logger.warning(
                    "DockerSandbox network:true attaches UNRESTRICTED egress "
                    "(including the metadata endpoint 169.254.169.254); an "
                    "injected command can exfiltrate cloud IAM credentials. You "
                    "accepted this with allow_unrestricted_egress:true. Prefer "
                    "egress_allowlist for filtered egress."
                )
                _network_warned = True
            return
        raise RuntimeError(
            "backend: docker network:true needs an egress policy — an injected "
            "command could otherwise read the cloud metadata endpoint "
            "169.254.169.254 and exfiltrate IAM credentials. Set "
            "options.bash.egress_allowlist:[hosts] for filtered egress "
            "(recommended — only those hosts, metadata/private ranges blocked), "
            "or allow_unrestricted_egress:true to accept UNFILTERED egress. "
            "Refused by default; network:false (no network) is the safe default."
        )

    def _ensure_image(self) -> None:
        """Verify the image is present locally, or raise a clear build/pull hint.

        Fails fast with remediation instead of the SDK's cryptic registry-pull
        404 thirty steps into a run — the default image is built locally, not
        published, so a first run would otherwise 404 opaquely.
        """
        docker = self._docker()
        try:
            self._client.images.get(self._image)
        except docker.errors.ImageNotFound as error:
            raise RuntimeError(
                f"sandbox image {self._image!r} is not available locally. "
                "Build the default image with: "
                f"docker build -f docker/sandbox.Dockerfile -t {self._image} ."
                " — or `docker pull` it, or set options.bash.image to an image "
                "you already have."
            ) from error

    def _owner_is_current(self, container: "Container") -> bool:
        """Return whether ``container``'s owner label is this live process."""
        labels = container.labels or {}
        try:
            return int(labels.get(LABEL_OWNER_PID, "")) == os.getpid()
        except (ValueError, TypeError):
            return False

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

    @staticmethod
    def _remove_container(container: "Container") -> None:
        """Force-remove a container (SIGKILL + remove) idempotently.

        ``force=True`` kills and removes in one step, so there is no wasted
        graceful-stop wait; ``v=False`` keeps any volumes (we use a bind mount,
        which is untouched regardless).
        """
        try:
            container.remove(force=True, v=False)
        except Exception as error:  # already gone / daemon down — nothing to do
            logger.debug("container remove failed: %s", error)

    # -- egress-filter proxy + internal network (task 033) --

    def _existing_proxy(self) -> Optional["Container"]:
        """Return the session's proxy sidecar container if it exists, else None."""
        docker = self._docker()
        try:
            return self._client.containers.get(self._proxy_name)
        except docker.errors.NotFound:
            return None

    def _ensure_egress_infra(self, docker: Any) -> None:
        """Create/reattach the internal network + the allowlist proxy sidecar.

        The sandbox joins the internal network (no direct route out); the proxy
        is dual-homed (internal + bridge) so it is the sandbox's *only* exit and
        can reach the allowed hosts. Recreated on a dead prior owner, like the
        sandbox container.
        """
        try:
            self._client.networks.get(self._egress_net_name)
        except docker.errors.NotFound:
            self._create_egress_network(docker)
        proxy = self._existing_proxy()
        if proxy is not None and not self._owner_is_current(proxy):
            self._remove_container(proxy)
            proxy = None
        if proxy is None:
            proxy = self._create_proxy()
        elif proxy.status != "running":
            proxy.start()
        self._proxy = proxy
        self._wait_for_proxy(proxy)

    def _create_egress_network(self, docker: Any) -> None:
        """Create the per-session ``internal`` network, with a remediation hint.

        Docker's default address pool is small (~31 ``/24`` subnets), and this
        feature's workload is many concurrent filtered-egress sessions, so pool
        exhaustion is a realistic failure — surface it actionably instead of the
        SDK's raw 500.
        """
        try:
            self._client.networks.create(
                self._egress_net_name,
                driver="bridge",
                internal=True,  # members have no route out on this network
                labels=self._labels(),
            )
        except docker.errors.APIError as error:
            raise RuntimeError(
                f"could not create egress network {self._egress_net_name!r}: "
                f"{error}. Docker's default address pool may be exhausted by "
                "leaked per-session networks — run `hugin sandbox prune` to "
                "reclaim abandoned ones, widen the daemon's "
                "default-address-pools, or lower concurrent filtered-egress "
                "sandboxes."
            ) from error

    def _proxy_kwargs(self) -> Dict[str, Any]:
        """Pure ``containers.run`` kwargs for the proxy sidecar — its boundary.

        Extracted like ``_container_kwargs`` so the proxy's own hardening (it *is*
        the egress boundary) is pinned by a daemon-free contract test, not only by
        the slow end-to-end suite. ``image`` is popped by ``_create_proxy`` for
        the positional arg.
        """
        return {
            "image": self._image,  # has python3; the proxy script is bind-mounted
            "command": ["python3", _PROXY_SCRIPT_MOUNT],
            "name": self._proxy_name,
            "detach": True,
            "init": True,  # reap the exec-probe children
            "network": self._egress_net_name,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "read_only": True,
            "tmpfs": {"/tmp": "rw,noexec,nosuid,size=16m"},
            "user": self._host_uid_gid(),
            "environment": {
                "EGRESS_ALLOWLIST": ",".join(self._spec.egress_allowlist),
                "EGRESS_PORT": str(_PROXY_PORT),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            "volumes": {
                _PROXY_SCRIPT_HOST: {"bind": _PROXY_SCRIPT_MOUNT, "mode": "ro"}
            },
            "labels": self._labels(),
            "mem_limit": "128m",
            "memswap_limit": "128m",
            "nano_cpus": 500_000_000,  # 0.5 CPU — a forward proxy needs little
            "pids_limit": 128,  # one thread per tunnel; headroom for parallelism
            # Survive a transient crash (OOM, a blip) mid-session instead of
            # silently killing the session's egress.
            "restart_policy": {"Name": "on-failure", "MaximumRetryCount": 3},
        }

    def _create_proxy(self) -> "Container":
        """Run the allowlist proxy sidecar — hardened, dual-homed, bind-mounted.

        Runs on the internal network, then connects the bridge so it (alone) can
        reach the internet. If the bridge attach fails, the proxy would be
        internal-only (no egress) yet look reusable next start — so remove it and
        re-raise rather than leave a silently broken proxy behind.
        """
        kwargs = self._proxy_kwargs()
        image = kwargs.pop("image")
        proxy = self._client.containers.run(image, **kwargs)
        try:
            self._client.networks.get("bridge").connect(proxy)
        except Exception:
            self._remove_container(proxy)
            raise
        return proxy

    def _wait_for_proxy(
        self, proxy: "Container", timeout_s: float = 15.0
    ) -> None:
        """Block until the proxy is *accepting connections*, or raise.

        Container ``running`` means init is up — not that the Python server has
        ``bind()``-ed its port. So readiness is verified by connecting to the
        proxy's own listener *from inside the container* (immune to host<->
        container routing differences across platforms). Raises on a crash or on
        the deadline, so a broken proxy surfaces as a clear error here rather than
        as a cryptic connection-refused on the sandbox's first command.
        """
        probe = (
            "import socket; "
            f"socket.create_connection(('127.0.0.1', {_PROXY_PORT}), 1).close()"
        )
        deadline = time.time() + timeout_s
        detail = "not running"
        while time.time() < deadline:
            proxy.reload()
            if proxy.status in ("exited", "dead"):
                raise RuntimeError(
                    f"egress proxy {self._proxy_name!r} exited during startup "
                    f"(status={proxy.status})"
                )
            if proxy.status == "running":
                try:
                    result = proxy.exec_run(["python3", "-c", probe])
                    if result.exit_code == 0:
                        return
                    detail = (result.output or b"").decode("utf-8", "replace")[
                        -200:
                    ]
                except Exception as error:  # daemon blip mid-probe — retry
                    detail = str(error)
            time.sleep(0.2)
        raise RuntimeError(
            f"egress proxy {self._proxy_name!r} did not become ready within "
            f"{timeout_s:.0f}s (last probe: {detail})"
        )

    def _remove_proxy_and_network(self) -> None:
        """Remove the proxy sidecar then the internal network (best-effort).

        Reached unconditionally from ``stop()`` (a resume path), so it must
        **never raise** — a raising teardown wedges the agent's stack. Every step
        is guarded, and it is a no-op for a non-egress-filtered sandbox (which has
        no proxy or network) so a flaky daemon can't turn a plain sandbox's
        ``stop()`` into an exception.
        """
        if self._client is None or not self._egress_filtered():
            return
        try:
            proxy = self._proxy or self._existing_proxy()
            if proxy is not None:
                self._remove_container(proxy)
        except Exception as error:  # daemon unreachable etc. — never propagate
            logger.debug("egress proxy remove failed: %s", error)
        self._proxy = None
        try:
            self._client.networks.get(self._egress_net_name).remove()
        except Exception as error:  # not found / still attached — leave it
            logger.debug("egress network remove failed: %s", error)

    def _container_kwargs(self) -> Dict[str, Any]:
        """Build the container-creation kwargs — the whole hardening contract.

        Pure and SDK-free (``ulimits`` are plain ``(name, soft, hard)`` tuples,
        finalized into ``docker.types.Ulimit`` in :meth:`_create_container`) so
        the flags can be asserted in a unit test without a daemon. Every value
        here is load-bearing for containment; changing one weakens the boundary.
        """
        uid_gid = self._host_uid_gid()
        # No network unless opted in. Filtered egress puts the container on a
        # per-session *internal* network (no direct route out — its only exit is
        # the dual-homed proxy, reached via HTTP_PROXY below); unrestricted uses
        # the bridge; the default is no network at all.
        if self._egress_filtered():
            network_mode = self._egress_net_name
        elif self._spec.network:
            network_mode = "bridge"
        else:
            network_mode = "none"
        environment = {
            "HOME": CONTAINER_WORKSPACE,
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "TERM": "dumb",
        }
        if self._egress_filtered():
            # The internal network has no route out; the sandbox's only exit is
            # the proxy (resolved by name via the network's embedded DNS).
            proxy_url = f"http://{self._proxy_name}:{_PROXY_PORT}"
            environment.update(
                {
                    "HTTP_PROXY": proxy_url,
                    "HTTPS_PROXY": proxy_url,
                    "http_proxy": proxy_url,
                    "https_proxy": proxy_url,
                }
            )
        return {
            "name": self._name,
            "command": ["sleep", "infinity"],  # idle PID; we exec per command
            "detach": True,
            "init": True,  # PID 1 reaps double-forked children (local can't)
            "network_mode": network_mode,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "read_only": True,  # rootfs is immutable; only the mounts below write
            # Both writable scratch mounts are noexec,nosuid,size-capped —
            # /dev/shm too, which docker otherwise mounts rw+exec even under a
            # read-only rootfs (a would-be drop-and-exec path).
            "tmpfs": {
                "/tmp": "rw,noexec,nosuid,size=256m",
                "/dev/shm": "rw,noexec,nosuid,size=64m",
            },
            "mem_limit": self._spec.memory,
            # Pin swap to the memory limit so the cap can't be doubled via swap.
            "memswap_limit": self._spec.memory,
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
            # own workspace in exec(). HTTP_PROXY is added above when egress is
            # filtered so the container's only route out is the allowlist proxy.
            "environment": environment,
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
            LABEL_HOST: current_hostname(),
            LABEL_BOOT: boot_id(),
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

    def stop(self) -> None:
        """Remove the container. Idempotent; safe if never started.

        Unlike ``local`` (whose ``stop`` is a no-op), this releases a real
        resource, so a clean exit does not leak a container. The reaper is the
        backstop for an abrupt exit that skips this. The bind-mounted host
        directory is intentionally left for the filesystem reaper / resume.
        """
        self._started = False
        container = self._container
        if container is not None:
            self._remove_container(container)
            self._container = None
        # Then the egress proxy + its internal network (order matters — a network
        # can't be removed while a container is attached). Best-effort no-op when
        # egress wasn't filtered.
        self._remove_proxy_and_network()

    # -- workspaces --

    def _agent_root(self, agent_id: str, branch: Optional[str]) -> str:
        """Container path for ``(agent, branch)`` (pure, no host dir created)."""
        rel = posixpath.join("agents", agent_id, branch or "default")
        return f"{CONTAINER_WORKSPACE}/{rel}"

    def workspace_for(self, agent_id: str, branch: Optional[str]) -> str:
        """Return the container path for ``(agent, branch)``; create it host-side.

        The returned path is a **container** path under ``/workspace``; the
        matching host directory (visible in the container through the bind
        mount) is created so a command has somewhere to run.
        """
        container = self._agent_root(agent_id, branch)
        os.makedirs(self._host_path(container), exist_ok=True)
        return container

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
        if self._egress_filtered():
            # The internal network has no direct route out; a command reaches the
            # internet only via the allowlist proxy. Set it explicitly per exec
            # rather than rely on inheriting the container's creation env.
            proxy_url = f"http://{self._proxy_name}:{_PROXY_PORT}"
            env.update(
                {
                    "HTTP_PROXY": proxy_url,
                    "HTTPS_PROXY": proxy_url,
                    "http_proxy": proxy_url,
                    "https_proxy": proxy_url,
                }
            )

        host_deadline = effective_timeout + _KILL_AFTER_S + _HOST_GRACE_S
        started = time.monotonic()
        exit_code, stdout_raw, stderr_raw, capped, hung = self._exec_capture(
            wrapped, cwd, env, host_deadline
        )
        duration = time.monotonic() - started

        timed_out, oom_killed = self._classify_exit(
            exit_code, hung, duration, effective_timeout
        )
        if capped:
            stderr_raw += (
                f"\n[hugin: output exceeded {_MAX_CAPTURE_BYTES} bytes; "
                "stopped reading]"
            )
        if hung:
            stderr_raw += (
                "\n[hugin: command exceeded its time budget and was abandoned "
                "(it may have left a background process)]"
            )

        out, out_trunc = truncate_output(stdout_raw, max_output_bytes)
        err, err_trunc = truncate_output(stderr_raw, max_output_bytes)
        truncated = out_trunc or err_trunc or capped
        spill_path = (
            self._spill(cwd, stdout_raw, stderr_raw) if truncated else None
        )

        return ExecResult(
            exit_code=exit_code,
            stdout=out,
            stderr=err,
            duration_s=duration,
            truncated=truncated,
            timed_out=timed_out,
            oom_killed=oom_killed,
            spill_path=spill_path,
        )

    @staticmethod
    def _classify_exit(
        exit_code: int, hung: bool, duration: float, timeout_s: int
    ) -> Tuple[bool, bool]:
        """Map an exit code to ``(timed_out, oom_killed)`` (see the shared rule)."""
        return classify_timeout_exit(exit_code, hung, duration, timeout_s)

    def _exec_capture(
        self,
        cmd: List[str],
        cwd: str,
        env: Dict[str, str],
        deadline_s: float,
    ) -> Tuple[int, str, str, bool, bool]:
        """Stream one exec under a byte cap and a host-side deadline.

        Returns ``(exit_code, stdout, stderr, capped, hung)``. Output is drained
        in a worker thread so a command that backgrounds a child holding the
        output pipe — which the in-container ``timeout`` cannot reach — can never
        block the agent's turn: the reader is joined against ``deadline_s``, and
        once the foreground exec exits, only a short grace. Buffered bytes are
        hard-capped at :data:`_MAX_CAPTURE_BYTES` so a runaway ``yes`` can't OOM
        the orchestrator. ``hung`` means the deadline was hit with the reader
        still blocked; ``exit_code`` is -1 when the process had not exited.
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
        total = [0]  # boxed so the reader thread can mutate it
        capped = threading.Event()
        done = threading.Event()

        def drain() -> None:
            try:
                for stdout_chunk, stderr_chunk in stream:
                    for chunk, buf in (
                        (stdout_chunk, out),
                        (stderr_chunk, err),
                    ):
                        if not chunk:
                            continue
                        total[0] += len(chunk)
                        room = _MAX_CAPTURE_BYTES - len(buf)
                        if room > 0:
                            buf.extend(chunk[:room])
                    if total[0] > _MAX_CAPTURE_BYTES:
                        capped.set()
                        break
            except Exception:  # pipe closed under us / stream error
                pass
            finally:
                done.set()

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()

        deadline = time.monotonic() + deadline_s
        while not done.is_set():
            if not self._exec_running(api, exec_id):
                # Foreground exec finished; a lingering background child may
                # still hold the pipe. Give the drain a short grace, then stop.
                done.wait(timeout=_DRAIN_GRACE_S)
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)

        hung = not done.is_set()
        try:
            stream.close()  # release our socket even if the drain is abandoned
        except Exception:  # pragma: no cover - best-effort
            pass

        info = api.exec_inspect(exec_id)
        exit_code = info.get("ExitCode")
        if exit_code is None:  # still running (cap break or host-side timeout)
            exit_code = -1
        return (
            int(exit_code),
            bytes(out).decode("utf-8", "replace"),
            bytes(err).decode("utf-8", "replace"),
            capped.is_set(),
            hung,
        )

    @staticmethod
    def _exec_running(api: Any, exec_id: str) -> bool:
        """Return whether the exec'd process is still running (True if unknown)."""
        try:
            return bool(api.exec_inspect(exec_id).get("Running", False))
        except Exception:  # pragma: no cover - if we can't tell, assume running
            return True

    def _spill(self, cwd: str, stdout: str, stderr: str) -> Optional[str]:
        """Write full output host-side so the agent can read past the cap.

        ``cwd`` is a container path under ``/workspace``; it maps to the host
        bind-mount root, so the file is visible both to the host and, at the
        same relative path, to the agent inside the container. Returns the
        *container* absolute path (what the agent reads, from any cwd), or None
        if the best-effort write failed.
        """
        relpath = new_spill_relpath()
        try:
            host_spill = os.path.join(self._host_path(cwd), relpath)
            os.makedirs(os.path.dirname(host_spill), exist_ok=True)
            with open(host_spill, "w", encoding="utf-8") as handle:
                handle.write(stdout)
                if stderr:
                    handle.write("\n--- stderr ---\n")
                    handle.write(stderr)
            # The agent reads it inside the container: the same relative path
            # under the container-side cwd (posix, absolute).
            return posixpath.join(cwd, relpath)
        except OSError as error:  # best-effort; never fail the command over it
            logger.debug("could not spill full output: %s", error)
            return None

    def _host_path(self, container_path: str) -> str:
        """Map a ``/workspace/...`` container path to its host bind-mount path."""
        rel = os.path.relpath(container_path, CONTAINER_WORKSPACE)
        return os.path.normpath(os.path.join(self._host_root, rel))

    # -- files --

    def put_file(
        self, agent_id: str, branch: Optional[str], path: str, content: bytes
    ) -> None:
        """Write ``content`` into the agent's workspace (host-side, confined)."""
        target = self._confine(agent_id, branch, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(content)

    def get_file(
        self, agent_id: str, branch: Optional[str], path: str
    ) -> bytes:
        """Read ``path`` from the agent's workspace, refusing a symlink escape."""
        target = self._confine(agent_id, branch, path)
        with open(target, "rb") as handle:
            return handle.read()

    def _confine(self, agent_id: str, branch: Optional[str], path: str) -> str:
        """Resolve ``path`` within the ``(agent, branch)`` host workspace, or raise.

        Confined to the *agent's own* workspace (not the whole session), so a
        traversal into a sibling agent's tree is refused. Accepts either a
        container ``/workspace/...`` path or a host/relative one, mapping the
        former to the host side first, then realpath-checks the result so a
        symlink planted in the workspace cannot point outside it.
        """
        root = os.path.realpath(
            self._host_path(self._agent_root(agent_id, branch))
        )
        if path == CONTAINER_WORKSPACE or path.startswith(
            CONTAINER_WORKSPACE + "/"
        ):
            path = self._host_path(path)
        candidate = path if os.path.isabs(path) else os.path.join(root, path)
        resolved = os.path.realpath(candidate)
        if resolved != root and not resolved.startswith(root + os.sep):
            raise PolicyDenied(f"path escapes the workspace: {path}")
        return resolved
