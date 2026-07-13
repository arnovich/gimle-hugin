"""``FakeSandbox`` — an in-memory backend for testing everything above exec.

It records the calls it receives and returns a canned :class:`ExecResult`, so
the tool, the manager, and the policy-to-response mapping can all be tested
with no subprocess, no container, and no daemon.
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

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
    ) -> None:
        """Return ``result`` (or a benign default) from every exec, or raise."""
        self._result = result or ExecResult(
            exit_code=0,
            stdout="ok",
            stderr="",
            duration_s=0.0,
        )
        self._raises = raises
        self.started = False
        self.stopped = False
        self.calls: List[_ExecCall] = []
        self.files: Dict[str, bytes] = {}

    def start(self) -> None:
        """Record that the sandbox was started."""
        self.started = True

    def stop(self) -> None:
        """Record that the sandbox was stopped."""
        self.stopped = True

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
        """Record the call and return the canned result (or raise)."""
        self.calls.append(
            _ExecCall(command, policy, cwd, timeout_s, max_output_bytes)
        )
        if self._raises is not None:
            raise self._raises
        return self._result

    def put_file(self, path: str, content: bytes) -> None:
        """Store ``content`` in the in-memory file map."""
        self.files[path] = content

    def get_file(self, path: str) -> bytes:
        """Return previously stored content for ``path``."""
        return self.files[path]

    @property
    def last_call(self) -> Optional[_ExecCall]:
        """The most recent exec call, or None if exec was never called."""
        return self.calls[-1] if self.calls else None
