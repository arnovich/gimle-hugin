"""``SandboxManager`` — one sandbox per session, lazily started, torn down once.

The manager owns the lifecycle so the tool doesn't have to: it lazily creates
and starts the backend on first use (a session that never runs a command never
pays for one) and closes it exactly once. The session-level teardown seam
(``Session.close``) and out-of-band reaping wire into ``close`` in a later unit;
here the manager is the single object that holds the live backend handle.
"""

import logging
import os
import threading
from typing import Optional

from gimle.hugin.sandbox.audit import CommandAudit
from gimle.hugin.sandbox.sandbox import (
    DEFAULT_SANDBOX_ROOT,
    Sandbox,
    SandboxSpec,
    create_sandbox,
)

logger = logging.getLogger(__name__)

# Outcomes that make a session's bash usage "hot" — worth a WARN at teardown so
# a misbehaving agent (a loop of timeouts, repeated denials, a flaky backend)
# surfaces without a metrics pipeline.
_HOT_OUTCOMES = (
    "denied",
    "timed_out",
    "infra_error",
    "sandbox_start_failures",
)


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
        # Serializes first-creation in ``get`` so two threads can't each build a
        # backend (check-then-act). The step loop is single-threaded today, so
        # this is defensive — but background exec already runs off-thread, so
        # keep the invariant explicit rather than load-bearing on call order.
        self._lock = threading.Lock()
        audit_path = None
        if record_audit_to_file:
            audit_path = os.path.join(
                workspace_root, session_id, ".hugin", "audit.jsonl"
            )
        self.audit = CommandAudit(audit_path)

    def get(self) -> Sandbox:
        """Return the session's sandbox, creating and starting it on first use.

        First-creation is serialized (double-checked under ``self._lock`` in
        ``_create_locked``) so concurrent callers build one backend, not one
        each. The common case — an already-created backend — takes no lock and
        just re-``start``s it (idempotent).
        """
        sandbox = self._sandbox
        if sandbox is not None:
            # A re-start() raising here is a *different* failure class than
            # first-bring-up: it's not counted as sandbox_start_failures (the
            # caller records it as infra_error), by design.
            sandbox.start()  # idempotent, no lock on the hot path
            return sandbox
        return self._create_locked()

    def _create_locked(self) -> Sandbox:
        """Create + start the backend under the lock (double-checked)."""
        with self._lock:
            existing = self._sandbox
            if existing is not None:  # another thread won the creation race
                existing.start()
                return existing
            try:
                sandbox = create_sandbox(
                    self._spec, self._session_id, self._workspace_root
                )
                sandbox.start()
            except Exception:
                # Bringing a backend up is the classic ops failure (daemon
                # down, host unreachable); count it so the rate is visible.
                self.audit.bump("sandbox_start_failures")
                raise
            self._sandbox = sandbox
            self.audit.bump("sandbox_starts")
            return sandbox

    def log_summary(self) -> None:
        """Emit the audit outcome counters as a structured log line.

        The counters otherwise live only in memory and are discarded at exit,
        leaving no trace of a misbehaving agent. Logged at ``Session.close``: an
        INFO line always, plus a WARNING naming the failing outcomes when any are
        present. A never-used sandbox (no outcomes) logs nothing.
        """
        summary = self.audit.summary()
        if not summary:
            return
        logger.info(
            "bash sandbox audit: session=%s backend=%s outcomes=%s",
            self._session_id,
            self._spec.backend,
            summary,  # already a plain dict snapshot
        )
        hot = {k: summary[k] for k in _HOT_OUTCOMES if summary.get(k)}
        if hot:
            logger.warning(
                "bash sandbox had failing outcomes: session=%s backend=%s %s",
                self._session_id,
                self._spec.backend,
                hot,
            )

    def close(self) -> None:
        """Tear the sandbox down. Idempotent; safe if never started."""
        if self._sandbox is not None:
            try:
                self._sandbox.stop()
            except Exception as error:  # teardown must never raise upward
                logger.warning("sandbox stop failed: %s", error)
