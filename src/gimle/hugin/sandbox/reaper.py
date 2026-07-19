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


def reap_abandoned_containers(
    *,
    now: float,
    pid_alive: Callable[[int], bool] = _pid_alive,
    start_time_of: Callable[[int], Optional[str]] = process_start_time,
) -> List[str]:
    """Stop and remove docker sandbox containers whose owner process is gone.

    The container counterpart of :func:`reap_local_workspaces`: a
    ``DockerSandbox`` labels its container with the owning PID and that
    process's start-time token, so the same dead-owner test (never session
    label alone — that would race a live peer) decides abandonment here. A
    container we cannot positively judge is kept until its TTL elapses.

    Best-effort and **daemon-optional**: if the ``docker`` SDK is absent or the
    daemon is unreachable, this is a no-op returning ``[]`` — reaping must never
    require docker, so ``local``/``ssh``-only users are unaffected.

    Returns:
        The names of the containers that were removed.
    """
    from gimle.hugin.sandbox.docker import (
        LABEL_CREATED,
        LABEL_OWNER_PID,
        LABEL_OWNER_START,
        LABEL_SESSION,
        LABEL_TTL,
        REAPER_CLIENT_TIMEOUT_S,
        import_docker,
    )

    try:
        # Short client timeout so a wedged daemon can't stall the startup reap
        # (this runs on every `hugin` invocation, before the real command).
        client = import_docker().from_env(timeout=REAPER_CLIENT_TIMEOUT_S)
        containers = client.containers.list(
            all=True, filters={"label": LABEL_SESSION}
        )
    except Exception as error:  # no SDK / daemon down — cleanup stays optional
        logger.debug("container reap skipped (docker unavailable): %s", error)
        return []

    reaped: List[str] = []
    for container in containers:
        try:
            labels = container.labels or {}
            if _container_is_abandoned(
                labels,
                now=now,
                pid_alive=pid_alive,
                start_time_of=start_time_of,
                created_key=LABEL_CREATED,
                pid_key=LABEL_OWNER_PID,
                start_key=LABEL_OWNER_START,
                ttl_key=LABEL_TTL,
            ):
                # force=True SIGKILLs and removes in one step (the owner is
                # already dead — no graceful stop to wait on).
                container.remove(force=True, v=False)
                reaped.append(container.name)
        except Exception as error:  # one bad container never aborts the sweep
            logger.debug("could not reap container %s: %s", container, error)

    if reaped:
        logger.info("reaped %d abandoned sandbox container(s)", len(reaped))
    return reaped


def reap_abandoned_networks(
    *,
    now: float,
    pid_alive: Callable[[int], bool] = _pid_alive,
    start_time_of: Callable[[int], Optional[str]] = process_start_time,
) -> List[str]:
    """Remove egress ``internal`` networks whose owner process is gone.

    The network counterpart of :func:`reap_abandoned_containers`: filtered
    egress creates a per-session internal network labelled with the same owner
    scheme, and a crashed session (no ``stop()``) leaks it. Docker's
    bridge-network subnet pool is small, so orphans accumulate into allocation
    failures — hence a dedicated sweep. The same dead-owner test decides
    abandonment; a network still attached to a *live* peer's container refuses
    removal and is simply kept. Call this **after** the container sweep so the
    proxy container is already gone and the network is detachable.

    Best-effort and daemon-optional (no SDK / daemon down -> ``[]``).

    Returns:
        The names of the networks that were removed.
    """
    from gimle.hugin.sandbox.docker import (
        LABEL_CREATED,
        LABEL_OWNER_PID,
        LABEL_OWNER_START,
        LABEL_SESSION,
        LABEL_TTL,
        REAPER_CLIENT_TIMEOUT_S,
        import_docker,
    )

    try:
        client = import_docker().from_env(timeout=REAPER_CLIENT_TIMEOUT_S)
        networks = client.networks.list(filters={"label": LABEL_SESSION})
    except Exception as error:  # no SDK / daemon down — cleanup stays optional
        logger.debug("network reap skipped (docker unavailable): %s", error)
        return []

    reaped: List[str] = []
    for network in networks:
        try:
            labels = (network.attrs or {}).get("Labels") or {}
            if _container_is_abandoned(
                labels,
                now=now,
                pid_alive=pid_alive,
                start_time_of=start_time_of,
                created_key=LABEL_CREATED,
                pid_key=LABEL_OWNER_PID,
                start_key=LABEL_OWNER_START,
                ttl_key=LABEL_TTL,
            ):
                # Refuses (raises) if a live peer container is still attached —
                # caught below, so a live session's network is never pulled.
                network.remove()
                reaped.append(network.name)
        except (
            Exception
        ) as error:  # one bad/attached network never aborts the sweep
            logger.debug("could not reap network %s: %s", network, error)

    if reaped:
        logger.info("reaped %d abandoned egress network(s)", len(reaped))
    return reaped


def _container_is_abandoned(
    labels: dict,
    *,
    now: float,
    pid_alive: Callable[[int], bool],
    start_time_of: Callable[[int], Optional[str]],
    created_key: str,
    pid_key: str,
    start_key: str,
    ttl_key: str,
) -> bool:
    """Decide whether a labelled container is abandoned (dead owner, or past TTL).

    Dead owner is the primary signal, using the same start-time disambiguation
    as the local reaper: a PID that is gone — or now belongs to a different
    incarnation — means the owner is dead and the container is abandoned. A
    container whose owner cannot be identified at all (missing/garbled PID
    label) is kept until its TTL elapses, never removed while its owner is
    provably alive.
    """
    try:
        pid = int(labels[pid_key])
    except (KeyError, ValueError, TypeError):
        pid = 0
    if pid <= 0:  # unidentifiable owner — lean on the TTL backstop only
        return _past_ttl(
            labels, now=now, created_key=created_key, ttl_key=ttl_key
        )
    start_time = labels.get(start_key) or None
    return not _owner_is_alive(pid, start_time, pid_alive, start_time_of)


def _past_ttl(
    labels: dict, *, now: float, created_key: str, ttl_key: str
) -> bool:
    """Return whether ``now`` is past the container's ``created + ttl``."""
    try:
        created = float(labels[created_key])
        ttl = float(labels[ttl_key])
    except (KeyError, ValueError, TypeError):
        return False  # cannot tell — keep it
    return now - created > ttl


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
