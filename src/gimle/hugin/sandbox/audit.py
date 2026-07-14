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
import time
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)


class CommandAudit:
    """Append-only audit of bash commands plus outcome counters."""

    def __init__(self, path: Optional[str] = None) -> None:
        """Record to ``path`` (JSONL) if given; always keep in-memory counters."""
        self.path = path
        self.counters: Counter = Counter()

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
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")
        except OSError as error:  # best-effort; never fail the command over it
            logger.debug("could not write audit entry: %s", error)
