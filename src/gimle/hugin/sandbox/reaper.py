"""Out-of-band reaping of abandoned local sandbox workspaces.

``Session.close`` cleans up on a clean exit, but it is skipped on an abrupt one
— SIGKILL, an OOM-kill, a closed laptop lid — which is the common case. So the
*primary* cleanup is this reaper: it runs at the start of every ``hugin``
invocation and removes only workspaces whose owning process is gone, never a
live peer's.

A local sandbox stamps its session directory with the owning PID and that
process's start time (``LocalSandbox`` writes ``OWNER_FILE`` on every start).
The reaper reaps a directory when that owner is no longer alive; a directory
with no stamp is reaped only once it is older than ``min_age_s`` (so a sandbox
mid-startup, before it has written its stamp, is never swept out from under
itself).

The start-time token guards against PID reuse: a live process that merely
recycled the dead owner's PID has a different start time, so it is not mistaken
for the owner (which would leak the dead workspace forever). Whenever the reaper
cannot positively confirm a PID belongs to a *different* incarnation, it errs
toward keeping the workspace — never deleting a possibly-live one.
"""

import json
import logging
import os
import shutil
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from gimle.hugin.sandbox.local import OWNER_FILE, process_start_time

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkspaceInfo:
    """A local sandbox workspace as seen by the reaper/CLI."""

    name: str
    pid: Optional[int]
    alive: bool
    age_s: float


def _pid_alive(pid: int) -> bool:
    """Return whether a process with ``pid`` currently exists."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but owned by another user
    return True


def _read_owner(session_dir: str) -> Optional[Tuple[int, Optional[str]]]:
    """Read ``(pid, start_time)`` from a session directory's stamp, or None.

    Tolerates a corrupt/partial stamp (truncated JSON, a null or non-integer
    ``pid``) by returning None rather than raising — one bad stamp must never
    abort the whole sweep.
    """
    try:
        with open(
            os.path.join(session_dir, OWNER_FILE), encoding="utf-8"
        ) as handle:
            data = json.load(handle)
        pid = int(data["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    start_time = data.get("start_time")
    if not isinstance(start_time, str):
        start_time = None
    return pid, start_time


def _owner_is_alive(
    pid: int,
    start_time: Optional[str],
    pid_alive: Callable[[int], bool],
    start_time_of: Callable[[int], Optional[str]],
) -> bool:
    """Report whether the stamped owner is still the live process it names.

    Reaps only when we can *positively* tell the PID now belongs to a different
    incarnation (start time differs); an unknowable start time keeps the
    workspace, so the reaper never deletes a possibly-live one.
    """
    if not pid_alive(pid):
        return False
    if start_time is None:
        return True  # nothing to disambiguate with — trust liveness
    current = start_time_of(pid)
    if current is None:
        return True  # can't read it now — err toward keeping
    return current == start_time


def reap_local_workspaces(
    workspace_root: str,
    *,
    now: float,
    min_age_s: float = 30.0,
    pid_alive: Callable[[int], bool] = _pid_alive,
    start_time_of: Callable[[int], Optional[str]] = process_start_time,
) -> List[str]:
    """Remove abandoned session workspaces under ``workspace_root``.

    Args:
        workspace_root: Directory holding one subdirectory per session.
        now: Current time (passed in for testability).
        min_age_s: An unstamped directory younger than this is left alone.
        pid_alive: Liveness check (injectable for tests).
        start_time_of: Process-incarnation token lookup (injectable for tests).

    Returns:
        The names of the session directories that were removed.
    """
    if not os.path.isdir(workspace_root):
        return []

    reaped: List[str] = []
    for name in os.listdir(workspace_root):
        session_dir = os.path.join(workspace_root, name)
        # A concurrent reaper (parallel `hugin` processes) can remove an entry
        # between listing and acting on it; guard the whole per-entry body so
        # one vanished/unreadable dir never aborts the sweep.
        try:
            if not os.path.isdir(session_dir):
                continue
            owner = _read_owner(session_dir)
            if owner is not None:
                if _owner_is_alive(*owner, pid_alive, start_time_of):
                    continue  # a live owner — never reap
            else:
                # Unstamped: reap only if clearly not a sandbox mid-startup.
                if now - os.path.getmtime(session_dir) < min_age_s:
                    continue
            shutil.rmtree(session_dir)
            reaped.append(name)
        except OSError as error:  # best-effort; a busy dir is tried next time
            logger.debug("could not reap %s: %s", session_dir, error)

    if reaped:
        logger.info("reaped %d abandoned sandbox workspace(s)", len(reaped))
    return reaped


def list_local_workspaces(
    workspace_root: str,
    *,
    now: float,
    pid_alive: Callable[[int], bool] = _pid_alive,
    start_time_of: Callable[[int], Optional[str]] = process_start_time,
) -> List[WorkspaceInfo]:
    """Describe each session workspace under ``workspace_root`` (for the CLI)."""
    if not os.path.isdir(workspace_root):
        return []
    infos: List[WorkspaceInfo] = []
    for name in sorted(os.listdir(workspace_root)):
        session_dir = os.path.join(workspace_root, name)
        try:
            if not os.path.isdir(session_dir):
                continue
            owner = _read_owner(session_dir)
            if owner is not None:
                pid: Optional[int] = owner[0]
                alive = _owner_is_alive(*owner, pid_alive, start_time_of)
            else:
                pid, alive = None, False
            age_s = now - os.path.getmtime(session_dir)
        except OSError:  # vanished mid-scan — skip it, don't crash the listing
            continue
        infos.append(
            WorkspaceInfo(name=name, pid=pid, alive=alive, age_s=age_s)
        )
    return infos
