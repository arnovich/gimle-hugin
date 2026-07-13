"""Out-of-band reaping of abandoned local sandbox workspaces.

``Session.close`` cleans up on a clean exit, but it is skipped on an abrupt one
— SIGKILL, an OOM-kill, a closed laptop lid — which is the common case. So the
*primary* cleanup is this reaper: it runs at the start of every ``hugin``
invocation and removes only workspaces whose owning process is gone, never a
live peer's.

A local sandbox stamps its session directory with the owning PID
(``LocalSandbox`` writes ``OWNER_FILE`` on start). The reaper reaps a directory
when that owner is no longer alive; a directory with no stamp is reaped only
once it is older than ``min_age_s`` (so a sandbox mid-startup, before it has
written its stamp, is never swept out from under itself). PID reuse can only
make the reaper *keep* a dead workspace a while longer, never delete a live
one — the safe direction to err.
"""

import json
import logging
import os
import shutil
from dataclasses import dataclass
from typing import Callable, List, Optional

from gimle.hugin.sandbox.local import OWNER_FILE

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


def _owner_pid(session_dir: str) -> "int | None":
    """Read the owning PID from a session directory's stamp, or None."""
    try:
        with open(
            os.path.join(session_dir, OWNER_FILE), encoding="utf-8"
        ) as handle:
            return int(json.load(handle)["pid"])
    except (OSError, ValueError, KeyError):
        return None


def reap_local_workspaces(
    workspace_root: str,
    *,
    now: float,
    min_age_s: float = 30.0,
    pid_alive: Callable[[int], bool] = _pid_alive,
) -> List[str]:
    """Remove abandoned session workspaces under ``workspace_root``.

    Args:
        workspace_root: Directory holding one subdirectory per session.
        now: Current time (passed in for testability).
        min_age_s: An unstamped directory younger than this is left alone.
        pid_alive: Liveness check (injectable for tests).

    Returns:
        The names of the session directories that were removed.
    """
    if not os.path.isdir(workspace_root):
        return []

    reaped: List[str] = []
    for name in os.listdir(workspace_root):
        session_dir = os.path.join(workspace_root, name)
        if not os.path.isdir(session_dir):
            continue

        pid = _owner_pid(session_dir)
        if pid is not None:
            if pid_alive(pid):
                continue  # a live owner — never reap
        else:
            # No stamp: only reap if it's clearly not a sandbox mid-startup.
            age = now - os.path.getmtime(session_dir)
            if age < min_age_s:
                continue

        try:
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
) -> List[WorkspaceInfo]:
    """Describe each session workspace under ``workspace_root`` (for the CLI)."""
    if not os.path.isdir(workspace_root):
        return []
    infos: List[WorkspaceInfo] = []
    for name in sorted(os.listdir(workspace_root)):
        session_dir = os.path.join(workspace_root, name)
        if not os.path.isdir(session_dir):
            continue
        pid = _owner_pid(session_dir)
        infos.append(
            WorkspaceInfo(
                name=name,
                pid=pid,
                alive=pid_alive(pid) if pid is not None else False,
                age_s=now - os.path.getmtime(session_dir),
            )
        )
    return infos
