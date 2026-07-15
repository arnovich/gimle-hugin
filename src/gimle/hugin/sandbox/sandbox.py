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

from abc import ABC, abstractmethod
from dataclasses import dataclass, fields
from typing import Any, Callable, Dict, Optional, Tuple, Type, cast

from gimle.hugin.sandbox.policy import Policy

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


def _phase2_loader(name: str) -> Callable[[], Type["Sandbox"]]:
    """Build a loader for a not-yet-implemented backend (clear error on use)."""

    def loader() -> Type["Sandbox"]:
        raise NotImplementedError(f"the {name} backend lands in phase 2")

    return loader


register_backend("local", _load_local)
register_backend("docker", _phase2_loader("docker"))
register_backend("ssh", _phase2_loader("ssh"))


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


@dataclass(frozen=True)
class SandboxSpec:
    """Which backend to run in, and its resource shape.

    ``backend`` has no default — a config must name where its agent's shell
    runs. The three backends are peers with no Docker dependency: ``local``
    (no isolation, honest about it), ``docker`` (container boundary), ``ssh``
    (the remote machine is the boundary). ``image`` applies to ``docker`` only;
    ``host`` to ``ssh`` only; the resource knobs to the container backends only.
    """

    backend: str
    image: Optional[str] = None
    host: Optional[str] = None
    network: bool = False
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
            raise ValueError(f"unknown sandbox keys: {sorted(unknown)}")
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
        return cls(**provided)


def create_sandbox(
    spec: SandboxSpec,
    session_id: str,
    workspace_root: str = "./storage/sandboxes",
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
        """Write ``content`` to ``path`` inside the workspace."""

    @abstractmethod
    def get_file(self, path: str) -> bytes:
        """Read ``path`` from the workspace (realpath-confined, no symlink escape)."""

    @abstractmethod
    def stop(self) -> None:
        """Tear down. Idempotent; safe on an unstarted sandbox."""
