"""Run ``bash`` commands off the scheduler thread so they don't freeze siblings.

The framework's session loop is single-threaded round-robin: a tool call runs
synchronously on the one scheduler thread, so a long ``sandbox.exec()`` blocks
*every* sibling agent. This module moves that blocking call onto a worker thread
and hands back a handle the (scheduler-thread) poll can check — the async-ness
lives **above** the ``Sandbox`` ABC, which stays synchronous and unchanged.

Design notes (see ``tasks/open/027-.../design.md`` and its panel review):

- The registry is in-memory and **not serialized** (mirrors ``session.sandboxes``);
  after a session reload a ``job_id`` is simply unknown, which every reader treats
  as *terminal* (never a ``KeyError`` — an exception escaping a tool permanently
  wedges the stack).
- Completion is audited **exactly once**, by whichever of {the inline waiter, an
  explicit collect, the worker done-callback} reaches it first — so a
  fire-and-forget job that is never collected still leaves an audit trail (a
  security requirement), while a collected job records synchronously (so tests
  and counters are deterministic).
- ``collect()`` never raises: a worker exception (a mid-run infra failure, a
  ``PolicyDenied`` backstop) or an unknown job maps to an ``is_error`` content
  dict, because the caller renders it straight into a ``tool_result``.
"""

import concurrent.futures
import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from gimle.hugin.sandbox.sandbox import ExecResult, PolicyDenied, Sandbox

if TYPE_CHECKING:
    from gimle.hugin.sandbox.manager import SandboxManager

logger = logging.getLogger(__name__)

# How long ``bash`` blocks the scheduler waiting for a command before it
# auto-backgrounds it (the automatic-deferral grace). A command that finishes
# within this returns inline like an ordinary synchronous call; a slower one
# defers so siblings run. Small and bounded — the freeze can never exceed it.
DEFAULT_DEFER_AFTER_S = 2.0

_MAX_WORKERS = 8
_MAX_OUTSTANDING_JOBS = 64


class BackgroundLimit(RuntimeError):
    """Raised when too many background jobs are already in flight."""


def result_content(command: str, result: ExecResult) -> Dict[str, Any]:
    """Render an ``ExecResult`` into the model-facing content dict.

    Shared by the foreground tool and the background collect so a backgrounded
    result is byte-identical to a synchronous one (the model learns no second
    format). ``is_error`` is computed by the caller (``timed_out or oom_killed``).
    """
    content: Dict[str, Any] = {
        "command": command,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_s": round(result.duration_s, 3),
        "truncated": result.truncated,
        "timed_out": result.timed_out,
        "oom_killed": result.oom_killed,
    }
    if result.truncated:
        content["full_output"] = ".hugin/last_output.txt"
    return content


@dataclass
class BashJob:
    """A single in-flight (or finished) background command."""

    job_id: str
    session_id: str
    agent_id: str
    command: str
    cwd: str
    future: "Future[ExecResult]"
    manager: "SandboxManager"
    started_at: float
    collected: bool = False
    recorded: bool = field(default=False, repr=False)


class BackgroundExecutor:
    """A session-scoped worker pool + registry for background bash commands.

    Lazily creates its thread pool on first ``submit`` (a session that never
    backgrounds anything spawns no threads).
    """

    def __init__(
        self,
        max_workers: int = _MAX_WORKERS,
        max_jobs: int = _MAX_OUTSTANDING_JOBS,
    ) -> None:
        """Configure pool size and the outstanding-job cap (no threads yet)."""
        self._max_workers = max_workers
        self._max_jobs = max_jobs
        self._pool: Optional[ThreadPoolExecutor] = None
        self._jobs: Dict[str, BashJob] = {}
        self._lock = threading.Lock()

    def submit(
        self,
        *,
        sandbox: Sandbox,
        manager: "SandboxManager",
        session_id: str,
        agent_id: str,
        command: str,
        cwd: str,
        policy: Any,
        timeout_s: int,
        max_output_bytes: int,
    ) -> BashJob:
        """Start ``command`` on a worker and return its job handle.

        Raises :class:`BackgroundLimit` if too many jobs are already running.
        """
        with self._lock:
            running = sum(1 for j in self._jobs.values() if not j.future.done())
            if running >= self._max_jobs:
                raise BackgroundLimit(
                    f"too many background commands in flight ({running}); "
                    "collect one with bash_output before starting another"
                )
            self._gc_locked()
            if self._pool is None:
                self._pool = ThreadPoolExecutor(
                    max_workers=self._max_workers,
                    thread_name_prefix="hugin-bash",
                )
            pool = self._pool

        def _work() -> ExecResult:
            return sandbox.exec(
                command,
                policy=policy,
                cwd=cwd,
                timeout_s=timeout_s,
                max_output_bytes=max_output_bytes,
            )

        future: "Future[ExecResult]" = pool.submit(_work)
        job = BashJob(
            job_id=uuid.uuid4().hex[:12],
            session_id=session_id,
            agent_id=agent_id,
            command=command,
            cwd=cwd,
            future=future,
            manager=manager,
            started_at=time.time(),
        )

        # Last-resort audit for a job that is never explicitly collected.
        def _done(_f: "Future[ExecResult]", j: BashJob = job) -> None:
            self._record_completion(j)

        future.add_done_callback(_done)
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def wait(self, job_id: str, timeout: float) -> bool:
        """Block up to ``timeout`` for the job; return whether it has finished."""
        job = self._get(job_id)
        if job is None:
            return True  # unknown -> terminal
        try:
            job.future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return False
        except Exception:  # finished (with an exception); collect surfaces it
            return True
        return True

    def is_done(self, job_id: str) -> bool:
        """Whether the job has finished (an unknown/lost job counts as done)."""
        job = self._get(job_id)
        return job is None or job.future.done()

    def collect(
        self, job_id: str, *, agent_id: Optional[str] = None
    ) -> Tuple[Dict[str, Any], bool]:
        """Return ``(content, is_error)`` for a finished job. Never raises.

        Records the outcome (once) before returning. An unknown/foreign job, or
        a worker exception, comes back as an ``is_error`` content dict so the
        caller can render it straight into a ``tool_result``.
        """
        job = self._get(job_id)
        if job is None:
            return (
                {
                    "error": f"unknown or already-collected job_id: {job_id}",
                    "note": "it was already collected, or lost to a session "
                    "restart; start a new command, do not retry this id",
                },
                True,
            )
        if agent_id is not None and job.agent_id != agent_id:
            return (
                {
                    "error": f"unknown or already-collected job_id: {job_id}",
                    "note": "start a new command; do not retry this id",
                },
                True,
            )
        self._record_completion(job)
        try:
            result = job.future.result(timeout=0)
        except concurrent.futures.TimeoutError:  # not finished yet
            return (
                {"job_id": job_id, "status": "running"},
                False,
            )
        except PolicyDenied as denied:
            content, is_error = (
                {"denied": denied.reason, "command": job.command},
                True,
            )
        except Exception as error:
            content, is_error = (
                {"infra_error": str(error), "command": job.command},
                True,
            )
        else:
            content = result_content(job.command, result)
            is_error = result.timed_out or result.oom_killed
        job.collected = True
        # Evict a collected job so a long session doesn't accumulate one entry
        # per command (every bash call routes through the registry, including
        # fast inline ones). A later collect of the same id falls through to the
        # "already-collected" error above.
        with self._lock:
            self._jobs.pop(job_id, None)
        return content, is_error

    def shutdown(self) -> None:
        """Drop queued jobs and join running workers.

        Call after stopping the sandboxes (which is what interrupts an in-flight
        ``exec``), so the join does not block on a still-running command.
        """
        with self._lock:
            pool, self._pool = self._pool, None
            self._jobs.clear()
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)

    # -- internals --

    def _gc_locked(self) -> None:
        """Evict old finished jobs so the registry stays bounded (lock held).

        Collected jobs are already evicted in ``collect``; this bounds
        fire-and-forget jobs that finished but the model never collected —
        keeping at most ``max_jobs`` finished entries, dropping the oldest.
        """
        finished = sorted(
            (j for j in self._jobs.values() if j.future.done()),
            key=lambda j: j.started_at,
        )
        for job in finished[: max(0, len(finished) - self._max_jobs)]:
            self._jobs.pop(job.job_id, None)

    def _get(self, job_id: str) -> Optional[BashJob]:
        """Look a job up under the lock."""
        with self._lock:
            return self._jobs.get(job_id)

    def _record_completion(self, job: BashJob) -> None:
        """Audit a finished job's outcome, at most once across all callers."""
        with self._lock:
            if job.recorded:
                return
            if not job.future.done():
                return  # not finished; a later caller will record it
            job.recorded = True
        try:
            result = job.future.result(timeout=0)
            outcome = "timed_out" if result.timed_out else "run"
            job.manager.audit.record(
                session_id=job.session_id,
                agent_id=job.agent_id,
                command=job.command,
                outcome=outcome,
                exit_code=result.exit_code,
                duration_s=round(result.duration_s, 3),
                truncated=result.truncated,
                timed_out=result.timed_out,
                oom_killed=result.oom_killed,
            )
        except concurrent.futures.CancelledError:
            # A queued job cancelled at shutdown never ran — nothing to audit.
            return
        except PolicyDenied as denied:
            job.manager.audit.record(
                session_id=job.session_id,
                agent_id=job.agent_id,
                command=job.command,
                outcome="denied",
                reason=denied.reason,
            )
        except Exception as error:
            job.manager.audit.record(
                session_id=job.session_id,
                agent_id=job.agent_id,
                command=job.command,
                outcome="infra_error",
                reason=str(error),
            )
