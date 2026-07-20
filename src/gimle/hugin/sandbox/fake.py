"""``FakeSandbox`` — an in-memory backend for testing everything above exec.

It records the calls it receives and returns a canned :class:`ExecResult`, so
the tool, the manager, and the policy-to-response mapping can all be tested
with no subprocess, no container, and no daemon.
"""

import os
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from gimle.hugin.sandbox.policy import Policy
from gimle.hugin.sandbox.sandbox import ExecResult, Sandbox


@dataclass
class _ExecCall:
    command: str
    policy: Policy
    cwd: str
    timeout_s: int
    max_output_bytes: int


class FakeSandbox(Sandbox):
    """A Sandbox that records calls and returns a pre-set result."""

    def __init__(
        self,
        result: Optional[ExecResult] = None,
        raises: Optional[Exception] = None,
        raises_on_start: Optional[Exception] = None,
        gate: Optional[threading.Event] = None,
    ) -> None:
        """Return ``result`` (or a benign default) from every exec, or raise.

        ``raises`` is raised from ``exec``; ``raises_on_start`` from ``start``
        (modelling a backend that fails to come up — daemon down, image
        missing, extra not installed). ``gate`` makes ``exec`` block until the
        event is set, so a test can hold a command "running" to exercise the
        background deferral path; ``stop`` sets the gate, modelling how stopping
        a real sandbox interrupts an in-flight ``exec``.
        """
        self._result = result or ExecResult(
            exit_code=0,
            stdout="ok",
            stderr="",
            duration_s=0.0,
        )
        self._raises = raises
        self._raises_on_start = raises_on_start
        self._gate = gate
        self.started = False
        self.stopped = False
        self.calls: List[_ExecCall] = []
        self.files: Dict[Tuple[str, Optional[str], str], bytes] = {}

    def start(self) -> None:
        """Record that the sandbox was started, or raise if configured to fail."""
        if self._raises_on_start is not None:
            raise self._raises_on_start
        self.started = True

    def stop(self) -> None:
        """Record that the sandbox was stopped; release any gated exec."""
        self.stopped = True
        if self._gate is not None:
            self._gate.set()

    def workspace_for(self, agent_id: str, branch: Optional[str]) -> str:
        """Return a deterministic fake workspace path for the pair."""
        return os.path.join(
            "/workspace", "agents", agent_id, branch or "default"
        )

    def exec(
        self,
        command: str,
        *,
        policy: Policy,
        cwd: str,
        timeout_s: int,
        max_output_bytes: int = 16_000,
    ) -> ExecResult:
        """Record the call and return the canned result (or raise).

        If a ``gate`` was set, block until it is released — so a test can hold
        the command "running" and observe the parked→resume deferral path.
        """
        self.calls.append(
            _ExecCall(command, policy, cwd, timeout_s, max_output_bytes)
        )
        if self._gate is not None:
            self._gate.wait()
        if self._raises is not None:
            raise self._raises
        return self._result

    def put_file(
        self, agent_id: str, branch: Optional[str], path: str, content: bytes
    ) -> None:
        """Store ``content`` in the in-memory file map, keyed per agent."""
        self.files[(agent_id, branch, path)] = content

    def get_file(
        self, agent_id: str, branch: Optional[str], path: str
    ) -> bytes:
        """Return previously stored content for this agent's ``path``."""
        return self.files[(agent_id, branch, path)]

    @property
    def last_call(self) -> Optional[_ExecCall]:
        """The most recent exec call, or None if exec was never called."""
        return self.calls[-1] if self.calls else None
