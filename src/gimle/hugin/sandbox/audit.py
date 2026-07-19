"""Command audit log: what the agent ran, and how it turned out.

A security-sensitive tool needs an answer to "which commands did agent X run,
and how many were denied?" at 2am. ``CommandAudit`` keeps outcome counters in
memory always, and — when given a file path — also appends each command as a
JSON line for post-mortem. Writing is best-effort: a failed append is logged
and swallowed, never allowed to fail the command it was recording.

Outcomes partition every attempt: ``run`` (executed to completion, any exit
code), ``timed_out``, ``infra_error``, ``denied``, ``escalated``.
"""

import json
import logging
import os
import threading
import time
from collections import Counter
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# The JSONL audit is append-only; without a bound a long-lived / chatty session
# grows it without limit. Rotate to a single ``.jsonl.1`` backup past this size,
# so on-disk audit is bounded to ~2x this (the live file plus one backup).
DEFAULT_MAX_AUDIT_BYTES = 5_000_000


class CommandAudit:
    """Append-only audit of bash commands plus outcome counters."""

    def __init__(
        self,
        path: Optional[str] = None,
        max_bytes: int = DEFAULT_MAX_AUDIT_BYTES,
    ) -> None:
        """Record to ``path`` (JSONL) if given; always keep in-memory counters.

        ``max_bytes`` bounds the JSONL file: past it, the file rotates to one
        ``.1`` backup before the next append, so audit-on-disk never grows
        without limit.
        """
        self.path = path
        self.max_bytes = max_bytes
        self.counters: Counter = Counter()
        # A background command records its outcome from a worker thread while a
        # foreground command records from the scheduler thread, so the counter
        # bump + file append must be serialized (a ``Counter[k] += 1`` is not
        # atomic across threads). Out-of-record bumps (``bump``) and snapshots
        # (``summary``) take the same lock.
        self._lock = threading.Lock()

    def bump(self, key: str, amount: int = 1) -> None:
        """Increment a counter under the lock (for outcomes outside ``record``).

        Lifecycle events like ``sandbox_starts`` / ``sandbox_start_failures`` are
        tallied here rather than via ``record`` (no command line to log), and may
        come from any thread — so they take the same lock as the record path.
        """
        with self._lock:
            self.counters[key] += amount

    def summary(self) -> Dict[str, int]:
        """Return a thread-safe snapshot copy of the outcome counters."""
        with self._lock:
            return dict(self.counters)

    def record(
        self,
        *,
        session_id: str,
        agent_id: str,
        command: str,
        outcome: str,
        exit_code: Optional[int] = None,
        duration_s: Optional[float] = None,
        truncated: bool = False,
        timed_out: bool = False,
        oom_killed: bool = False,
        reason: Optional[str] = None,
    ) -> None:
        """Count the outcome and, if a path is set, append a JSON line."""
        with self._lock:
            self.counters[outcome] += 1
            if not self.path:
                return
            entry = {
                "ts": time.time(),
                "session_id": session_id,
                "agent_id": agent_id,
                "command": command,
                "outcome": outcome,
                "exit_code": exit_code,
                "duration_s": duration_s,
                "truncated": truncated,
                "timed_out": timed_out,
                "oom_killed": oom_killed,
                "reason": reason,
            }
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                self._rotate_if_large()
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry) + "\n")
            except OSError as error:  # best-effort; never fail over it
                logger.debug("could not write audit entry: %s", error)

    def _rotate_if_large(self) -> None:
        """Rotate the JSONL file to a single ``.1`` backup once it exceeds the cap.

        Called under ``self._lock`` from ``record``. Keeps exactly one backup
        (``os.replace`` overwrites any prior one), so on-disk audit is bounded.
        Best-effort: a failed rotation just lets the file keep growing this turn.
        """
        assert self.path is not None
        try:
            if os.path.getsize(self.path) < self.max_bytes:
                return
        except OSError:
            return  # not there yet / unstatable — nothing to rotate
        try:
            os.replace(self.path, self.path + ".1")
        except OSError as error:  # keep appending rather than fail the command
            logger.debug("could not rotate audit file: %s", error)
