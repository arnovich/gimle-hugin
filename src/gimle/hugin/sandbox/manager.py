"""``SandboxManager`` — one sandbox per session, lazily started, torn down once.

The manager owns the lifecycle so the tool doesn't have to: it lazily creates
and starts the backend on first use (a session that never runs a command never
pays for one) and closes it exactly once. The session-level teardown seam
(``Session.close``) and out-of-band reaping wire into ``close`` in a later unit;
here the manager is the single object that holds the live backend handle.
"""

import logging
import os
from typing import Optional

from gimle.hugin.sandbox.audit import CommandAudit
from gimle.hugin.sandbox.sandbox import (
    DEFAULT_SANDBOX_ROOT,
    Sandbox,
    SandboxSpec,
    create_sandbox,
)

logger = logging.getLogger(__name__)


class SandboxManager:
    """Lazily own one :class:`Sandbox` for a session."""

    def __init__(
        self,
        spec: SandboxSpec,
        session_id: str,
        workspace_root: str = DEFAULT_SANDBOX_ROOT,
        sandbox: Optional[Sandbox] = None,
        record_audit_to_file: bool = False,
    ) -> None:
        """Bind to ``session_id``; ``sandbox`` pre-injects a backend (tests).

        ``record_audit_to_file`` additionally persists the command audit as a
        JSONL file under the session workspace; off by default so pre-injected
        managers (tests, in-process apps) keep counters without touching disk.
        """
        self._spec = spec
        self._session_id = session_id
        self._workspace_root = workspace_root
        self._sandbox = sandbox
        audit_path = None
        if record_audit_to_file:
            audit_path = os.path.join(
                workspace_root, session_id, ".hugin", "audit.jsonl"
            )
        self.audit = CommandAudit(audit_path)

    def get(self) -> Sandbox:
        """Return the session's sandbox, creating and starting it on first use."""
        if self._sandbox is None:
            try:
                sandbox = create_sandbox(
                    self._spec, self._session_id, self._workspace_root
                )
                sandbox.start()
            except Exception:
                # Bringing a backend up is the classic ops failure (daemon
                # down, host unreachable); count it so the rate is visible.
                self.audit.counters["sandbox_start_failures"] += 1
                raise
            self._sandbox = sandbox
            self.audit.counters["sandbox_starts"] += 1
            return self._sandbox
        self._sandbox.start()  # idempotent
        return self._sandbox

    def close(self) -> None:
        """Tear the sandbox down. Idempotent; safe if never started."""
        if self._sandbox is not None:
            try:
                self._sandbox.stop()
            except Exception as error:  # teardown must never raise upward
                logger.warning("sandbox stop failed: %s", error)
