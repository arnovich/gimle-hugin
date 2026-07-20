"""The ``Sandbox`` execution-backend protocol.

A :class:`Sandbox` is *somewhere a command can run* — the host, a local
container, or a remote machine. The protocol is deliberately narrow and mirrors
the ``Storage`` ABC: a small surface, concrete backends beside it, no knowledge
of agents or tools. Everything above this layer is backend-agnostic.

Concrete backends (``LocalSandbox``, ``DockerSandbox``, ``SSHSandbox``) and the
``create_sandbox`` factory land in later phases. This module defines only the
shared types so the tool and the policy engine can be built and tested against
a fake backend first.
"""

import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, fields
from typing import Any, Callable, Dict, Optional, Tuple, Type, cast

from gimle.hugin.sandbox.policy import Policy

# Default storage base when a session has no explicit path (in-memory storage).
DEFAULT_STORAGE_BASE = "./storage"

# Directory (relative to a workspace) that per-command output spills land in, and
# a factory for a unique spill filename. Forward slashes so the one relative path
# is valid on the host, in a Linux container, and on a remote box alike; each
# backend joins it onto its own base and returns the absolute result.
SPILL_DIR = ".hugin"


def new_spill_relpath() -> str:
    """Return a unique, workspace-relative spill filename for one command.

    Unique per call so a later truncated command never clobbers an earlier
    command's spilled output (a fixed ``last_output.txt`` did).
    """
    return f"{SPILL_DIR}/output-{uuid.uuid4().hex[:12]}.txt"


def sandbox_root_for(storage_base: Optional[str]) -> str:
    """Return the sandbox workspace root for a session's storage base path.

    Sandboxes live beside the rest of a session's storage
    (``<storage_base>/sandboxes``) — one place, derived from one source — so a
    custom ``--storage-path`` keeps its sandboxes with its sessions and the
    startup reaper looks where the tool actually wrote. Falls back to the
    default base when storage is in-memory / has no path.
    """
    return os.path.join(storage_base or DEFAULT_STORAGE_BASE, "sandboxes")


# The single canonical default root (was duplicated as a literal in four files).
DEFAULT_SANDBOX_ROOT = sandbox_root_for(None)

# --- backend registry ---
# Backend name -> a lazy loader returning its ``Sandbox`` subclass. Lazy so
# selecting one backend never imports another's dependency (the ``docker`` SDK,
# a remote client) — the three backends stay true peers. Adding a backend is a
# ``register_backend`` call, not an edit to a hardcoded enum + factory.
_BACKENDS: Dict[str, Callable[[], Type["Sandbox"]]] = {}


def register_backend(name: str, loader: Callable[[], Type["Sandbox"]]) -> None:
    """Register ``name`` -> a thunk that imports and returns its Sandbox class."""
    _BACKENDS[name] = loader


def registered_backends() -> Tuple[str, ...]:
    """Return the registered backend names, sorted."""
    return tuple(sorted(_BACKENDS))


def _load_local() -> Type["Sandbox"]:
    """Import the local backend on demand."""
    from gimle.hugin.sandbox.local import LocalSandbox

    return LocalSandbox


def _load_docker() -> Type["Sandbox"]:
    """Import the docker backend on demand.

    Importing the module is cheap and dependency-free — ``DockerSandbox`` pulls
    in the ``docker`` SDK lazily inside its methods — so a missing extra
    surfaces as a clear remediation error at ``start()``, not an import crash.
    """
    from gimle.hugin.sandbox.docker import DockerSandbox

    return DockerSandbox


def _load_ssh() -> Type["Sandbox"]:
    """Import the ssh backend on demand (it shells out to ``ssh``/``scp``)."""
    from gimle.hugin.sandbox.ssh import SSHSandbox

    return SSHSandbox


register_backend("local", _load_local)
register_backend("docker", _load_docker)
register_backend("ssh", _load_ssh)


def classify_timeout_exit(
    exit_code: int, hung: bool, duration: float, timeout_s: float
) -> Tuple[bool, bool]:
    """Map a ``timeout``-wrapped exit code to ``(timed_out, oom_killed)``.

    Shared by every backend that runs commands under coreutils ``timeout -k``:
    124 is a wall-clock timeout; 137 is a SIGKILL, ambiguous between a memory-cap
    OOM kill and ``timeout``'s kill-after finishing off a SIGTERM-ignoring
    process — so 137 at/after the deadline is classed as a timeout (the more
    actionable signal), otherwise as OOM. A host-side abandonment (``hung``) is
    always a timeout.
    """
    if hung or exit_code == 124:
        return True, False
    if exit_code == 137 and duration >= timeout_s:
        return True, False  # kill-after finished off a TERM-ignoring hang
    if exit_code == 137:
        return False, True  # SIGKILL well before the deadline — likely OOM
    return False, False


def truncate_output(text: str, max_bytes: int) -> Tuple[str, bool]:
    """Cap ``text`` at ``max_bytes``, tail-biased, with an elision marker.

    Returns ``(text, truncated)``. The truncation keeps a small head (so the
    reader sees where output began) and a larger tail — the actionable error
    (a test failure, a traceback summary) is usually last. Shared by every
    backend so the cap behaves identically regardless of where the command ran.
    """
    raw = text.encode("utf-8", "replace")
    if len(raw) <= max_bytes:
        return text, False
    head_n = max_bytes // 5
    tail_n = max_bytes - head_n
    elided = len(raw) - head_n - tail_n
    marker = f"\n[... {elided} bytes elided ...]\n"
    head = raw[:head_n].decode("utf-8", "ignore")
    tail = raw[len(raw) - tail_n :].decode("utf-8", "ignore")
    return head + marker + tail, True


class PolicyDenied(Exception):
    """Raised inside ``Sandbox.exec`` when policy refuses a command.

    Enforcement lives in the backend (not only in the tool) so that *every*
    route to ``exec`` is checked by construction — a future tool or the harvest
    layer cannot reach execution unchecked. The tool additionally calls
    ``evaluate`` itself only to render a friendly result.
    """

    def __init__(self, reason: str) -> None:
        """Record the human-readable ``reason`` the command was refused."""
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ExecResult:
    """The outcome of running one command.

    ``exit_code`` is the process's own status; a non-zero exit is data about
    the process (``grep`` finding nothing exits 1), not necessarily an error.
    The distinct failure surfaces the tool must tell apart are carried
    explicitly: ``timed_out`` and ``oom_killed`` (policy denial and infra
    failure are represented by ``PolicyDenied`` / raised exceptions, not here).
    """

    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    truncated: bool = False
    timed_out: bool = False
    oom_killed: bool = False
    # When ``truncated``, the absolute path (in the command's own namespace —
    # host / container / remote) of the file the full output was spilled to, so
    # a follow-up can read past the cap. Unique per command (so a later
    # truncation doesn't clobber an earlier one) and absolute (so it reads from
    # any cwd). None if nothing was spilled or the spill write failed.
    spill_path: Optional[str] = None


@dataclass(frozen=True)
class SandboxSpec:
    """Which backend to run in, and its resource shape.

    ``backend`` has no default — a config must name where its agent's shell
    runs. The three backends are peers with no Docker dependency: ``local``
    (no isolation, honest about it), ``docker`` (container boundary), ``ssh``
    (the remote machine is the boundary). ``image`` applies to ``docker`` only;
    ``host`` / ``ssh_key`` / ``port`` to ``ssh`` only; the resource knobs to the
    container backends only.
    """

    backend: str
    image: Optional[str] = None
    host: Optional[str] = None
    ssh_key: Optional[str] = None
    port: Optional[int] = None
    network: bool = False
    # Explicit, informed opt-in to UNFILTERED egress on ``docker`` when
    # ``network: true``. Off by default: unfiltered egress lets an injected
    # command read the cloud metadata endpoint (169.254.169.254) and exfiltrate
    # IAM credentials, so ``network: true`` is refused unless this acknowledges
    # the risk. Real egress filtering (an allowlist proxy) is task 030.
    allow_unrestricted_egress: bool = False
    # Docker only: host/domain allowlist for **filtered** egress. When
    # ``network: true`` and this is non-empty, egress is routed through a
    # per-session proxy that permits only these hosts (and their subdomains) and
    # blocks link-local/metadata + private ranges. A tuple so the spec stays
    # hashable (it keys ``session.sandboxes``). See task 033.
    egress_allowlist: Tuple[str, ...] = ()
    cpu: float = 2.0
    memory: str = "2g"
    pids: int = 512

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SandboxSpec":
        """Build a SandboxSpec from the ``options.bash`` block, failing loud.

        The ``policy`` sub-block belongs to :class:`Policy`, so it is ignored
        here; every other unknown key raises. ``backend`` is required — a config
        must name where its agent's shell runs; there is no silent default.
        """
        if not isinstance(data, dict):
            raise ValueError("options.bash must be a mapping")
        known = {f.name for f in fields(cls)}
        provided = {k: v for k, v in data.items() if k != "policy"}
        unknown = set(provided) - known
        if unknown:
            raise ValueError(
                f"unknown sandbox keys: {sorted(unknown)}"
                f"{_misplaced_policy_hint(unknown)}"
            )
        if "backend" not in provided:
            raise ValueError(
                "options.bash.backend is required "
                f"({' | '.join(registered_backends())})"
            )
        if provided["backend"] not in registered_backends():
            raise ValueError(
                f"invalid backend: {provided['backend']!r} "
                f"(known: {', '.join(registered_backends())})"
            )
        if "egress_allowlist" in provided:
            # YAML gives a list; the spec field is a tuple so the spec stays
            # hashable (it keys ``session.sandboxes``).
            provided["egress_allowlist"] = tuple(provided["egress_allowlist"])
        return cls(**provided)


def _misplaced_policy_hint(unknown: set) -> str:
    """Suggest nesting under ``policy:`` for keys that are Policy fields.

    A common config mistake is putting a policy knob (``deny``, ``timeout_s``, …)
    at the top level of ``options.bash`` instead of under
    ``options.bash.policy``. Turn the bare "unknown sandbox keys" error into an
    actionable hint when that's what happened; empty otherwise.
    """
    misplaced = sorted(unknown & {f.name for f in fields(Policy)})
    if not misplaced:
        return ""
    return (
        f" — {misplaced} look like policy settings; "
        "nest them under options.bash.policy"
    )


def create_sandbox(
    spec: SandboxSpec,
    session_id: str,
    workspace_root: str = DEFAULT_SANDBOX_ROOT,
) -> "Sandbox":
    """Construct the backend named by ``spec`` via the registry.

    The backend's class is imported lazily (through its registered loader) so
    selecting ``local`` never pulls in the ``docker`` SDK, and vice versa — the
    backends are peers with no shared dependency.
    """
    loader = _BACKENDS.get(spec.backend)
    if loader is None:
        raise ValueError(
            f"unknown backend: {spec.backend!r} "
            f"(known: {', '.join(registered_backends())})"
        )
    # Every backend is constructed uniformly as (spec, session_id, root); the
    # Sandbox ABC declares no constructor, so tell the type checker the shape.
    factory = cast(Callable[[SandboxSpec, str, str], "Sandbox"], loader())
    return factory(spec, session_id, workspace_root)


class Sandbox(ABC):
    """Somewhere a command can run. Backends implement this."""

    @abstractmethod
    def start(self) -> None:
        """Create/pull/connect. Idempotent; called lazily on first ``exec``."""

    @abstractmethod
    def exec(
        self,
        command: str,
        *,
        policy: Policy,
        cwd: str,
        timeout_s: int,
        max_output_bytes: int = 16_000,
    ) -> ExecResult:
        """Run ``command``.

        The backend enforces ``policy`` before running and raises
        :class:`PolicyDenied` on a violation (fail closed). It executes through
        the same dialect the policy parsed (``bash -c``). It never raises for a
        non-zero exit — that is reported in :class:`ExecResult`.
        """

    @abstractmethod
    def workspace_for(self, agent_id: str, branch: Optional[str]) -> str:
        """Absolute working directory for this ``(agent, branch)``; created."""

    @abstractmethod
    def put_file(self, path: str, content: bytes) -> None:
        """Write ``content`` to ``path`` inside the workspace (confined)."""

    @abstractmethod
    def get_file(self, path: str) -> bytes:
        """Read ``path`` from the workspace.

        Confined to the workspace. The *strength* of that confinement is
        backend-dependent: the local backend resolves the real path (symlink
        escapes blocked), while the ssh backend confines lexically (a remote
        symlink escape is out of scope on a disposable box — see its docstring).
        """

    @abstractmethod
    def stop(self) -> None:
        """Tear down. Idempotent; safe on an unstarted sandbox."""
