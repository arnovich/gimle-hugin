"""``SandboxManager`` — one sandbox per session, lazily started, torn down once.

The manager owns the lifecycle so the tool doesn't have to: it lazily creates
and starts the backend on first use (a session that never runs a command never
pays for one) and closes it exactly once. The session-level teardown seam
(``Session.close``) and out-of-band reaping wire into ``close`` in a later unit;
here the manager is the single object that holds the live backend handle.
"""

import logging
from typing import Optional

from gimle.hugin.sandbox.sandbox import Sandbox, SandboxSpec, create_sandbox

logger = logging.getLogger(__name__)


class SandboxManager:
    """Lazily own one :class:`Sandbox` for a session."""

    def __init__(
        self,
        spec: SandboxSpec,
        session_id: str,
        workspace_root: str = "./storage/sandboxes",
        sandbox: Optional[Sandbox] = None,
    ) -> None:
        """Bind to ``session_id``; ``sandbox`` pre-injects a backend (tests)."""
        self._spec = spec
        self._session_id = session_id
        self._workspace_root = workspace_root
        self._sandbox = sandbox

    def get(self) -> Sandbox:
        """Return the session's sandbox, creating and starting it on first use."""
        if self._sandbox is None:
            self._sandbox = create_sandbox(
                self._spec, self._session_id, self._workspace_root
            )
        self._sandbox.start()  # idempotent
        return self._sandbox

    def close(self) -> None:
        """Tear the sandbox down. Idempotent; safe if never started."""
        if self._sandbox is not None:
            try:
                self._sandbox.stop()
            except Exception as error:  # teardown must never raise upward
                logger.warning("sandbox stop failed: %s", error)
