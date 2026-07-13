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
from dataclasses import dataclass
from typing import Literal, Optional

from gimle.hugin.sandbox.policy import Policy


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

    backend: Literal["local", "docker", "ssh"]
    image: Optional[str] = None
    host: Optional[str] = None
    network: bool = False
    cpu: float = 2.0
    memory: str = "2g"
    pids: int = 512


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
