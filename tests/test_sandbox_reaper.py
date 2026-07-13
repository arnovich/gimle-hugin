"""Tests for out-of-band reaping of abandoned local sandbox workspaces.

The reaper's one invariant: it removes a workspace only when its owner is gone,
and never a live peer's. These pin exactly that, using an injected liveness
check so the tests are deterministic (no real dead PIDs).
"""

import json
import os
import time

from gimle.hugin.sandbox.local import OWNER_FILE
from gimle.hugin.sandbox.reaper import reap_local_workspaces

NOW = 1_000_000.0


def _session_dir(root, name, pid=None, mtime=None):
    """Create a session dir under root, optionally stamped with ``pid``."""
    path = os.path.join(str(root), name)
    os.makedirs(path)
    if pid is not None:
        with open(os.path.join(path, OWNER_FILE), "w") as handle:
            json.dump({"pid": pid, "created": NOW}, handle)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _dead(pid):
    """Report every PID as dead."""
    return False


def _only(alive_pid):
    """Return a liveness check where only ``alive_pid`` is alive."""
    return lambda pid: pid == alive_pid


def test_dead_owner_workspace_is_reaped(tmp_path):
    """A workspace whose owner PID is gone is removed."""
    _session_dir(tmp_path, "sess-dead", pid=4242)
    reaped = reap_local_workspaces(str(tmp_path), now=NOW, pid_alive=_dead)
    assert reaped == ["sess-dead"]
    assert not os.path.exists(tmp_path / "sess-dead")


def test_live_owner_workspace_is_kept(tmp_path):
    """A workspace whose owner is still alive is never removed."""
    _session_dir(tmp_path, "sess-live", pid=4242)
    reaped = reap_local_workspaces(
        str(tmp_path), now=NOW, pid_alive=_only(4242)
    )
    assert reaped == []
    assert os.path.isdir(tmp_path / "sess-live")


def test_unstamped_old_workspace_is_reaped(tmp_path):
    """An unstamped directory older than min_age is treated as an orphan."""
    _session_dir(tmp_path, "sess-orphan", mtime=NOW - 3600)
    reaped = reap_local_workspaces(
        str(tmp_path), now=NOW, min_age_s=30, pid_alive=_dead
    )
    assert reaped == ["sess-orphan"]


def test_unstamped_young_workspace_is_kept(tmp_path):
    """An unstamped directory younger than min_age (mid-startup) is left."""
    _session_dir(tmp_path, "sess-starting", mtime=NOW - 5)
    reaped = reap_local_workspaces(
        str(tmp_path), now=NOW, min_age_s=30, pid_alive=_dead
    )
    assert reaped == []
    assert os.path.isdir(tmp_path / "sess-starting")


def test_missing_root_is_a_noop(tmp_path):
    """Reaping a root that does not exist yet returns nothing."""
    assert reap_local_workspaces(str(tmp_path / "nope"), now=time.time()) == []


def test_only_dead_owners_are_reaped_among_several(tmp_path):
    """A mixed set: dead owners go, the live one stays."""
    _session_dir(tmp_path, "a-dead", pid=111)
    _session_dir(tmp_path, "b-live", pid=222)
    _session_dir(tmp_path, "c-dead", pid=333)
    reaped = reap_local_workspaces(str(tmp_path), now=NOW, pid_alive=_only(222))
    assert sorted(reaped) == ["a-dead", "c-dead"]
    assert os.path.isdir(tmp_path / "b-live")
