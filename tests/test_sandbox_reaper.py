"""Tests for out-of-band reaping of abandoned local sandbox workspaces.

The reaper's one invariant: it removes a workspace only when its owner is gone,
and never a live peer's. These pin exactly that, using an injected liveness
check so the tests are deterministic (no real dead PIDs).
"""

import json
import os
import time

from gimle.hugin.sandbox.docker import (
    LABEL_CREATED,
    LABEL_OWNER_PID,
    LABEL_OWNER_START,
    LABEL_SESSION,
    LABEL_TTL,
)
from gimle.hugin.sandbox.local import OWNER_FILE
from gimle.hugin.sandbox.reaper import (
    _container_is_abandoned,
    list_local_workspaces,
    reap_abandoned_containers,
    reap_local_workspaces,
)

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


def test_list_describes_each_workspace(tmp_path):
    """The lister reports name, owner pid, liveness, and age."""
    _session_dir(tmp_path, "live", pid=222, mtime=NOW - 100)
    _session_dir(tmp_path, "dead", pid=333, mtime=NOW - 200)
    infos = list_local_workspaces(str(tmp_path), now=NOW, pid_alive=_only(222))
    by_name = {info.name: info for info in infos}
    assert by_name["live"].alive is True
    assert by_name["live"].pid == 222
    assert by_name["dead"].alive is False
    assert by_name["dead"].age_s == 200


def _stamp(root, name, record, mtime=None):
    """Create a session dir under root stamped with an arbitrary record."""
    path = os.path.join(str(root), name)
    os.makedirs(path)
    with open(os.path.join(path, OWNER_FILE), "w") as handle:
        json.dump(record, handle)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


class TestPidReuseDisambiguation:
    """The start-time token separates the true owner from a recycled PID."""

    def test_reused_pid_is_reaped(self, tmp_path):
        """A live PID with a DIFFERENT start time is not the owner — reaped."""
        _stamp(tmp_path, "sess", {"pid": 222, "start_time": "OLD"})
        reaped = reap_local_workspaces(
            str(tmp_path),
            now=NOW,
            pid_alive=_only(222),
            start_time_of=lambda pid: "NEW",
        )
        assert reaped == ["sess"]

    def test_same_incarnation_is_kept(self, tmp_path):
        """A live PID whose start time matches the stamp is the owner — kept."""
        _stamp(tmp_path, "sess", {"pid": 222, "start_time": "SAME"})
        reaped = reap_local_workspaces(
            str(tmp_path),
            now=NOW,
            pid_alive=_only(222),
            start_time_of=lambda pid: "SAME",
        )
        assert reaped == []
        assert os.path.isdir(tmp_path / "sess")

    def test_unknowable_start_time_keeps_workspace(self, tmp_path):
        """When the start time can't be read now, err toward keeping."""
        _stamp(tmp_path, "sess", {"pid": 222, "start_time": "OLD"})
        reaped = reap_local_workspaces(
            str(tmp_path),
            now=NOW,
            pid_alive=_only(222),
            start_time_of=lambda pid: None,
        )
        assert reaped == []


def _labels(pid, start="SAME", created=NOW, ttl=3600):
    """Build the container labels a DockerSandbox would stamp."""
    return {
        LABEL_SESSION: "sess",
        LABEL_OWNER_PID: str(pid),
        LABEL_OWNER_START: start,
        LABEL_CREATED: str(created),
        LABEL_TTL: str(ttl),
    }


def _abandoned(labels, *, now=NOW, pid_alive=_dead, start_time_of=None):
    """Call _container_is_abandoned with the real docker label keys."""
    return _container_is_abandoned(
        labels,
        now=now,
        pid_alive=pid_alive,
        start_time_of=start_time_of or (lambda pid: "SAME"),
        created_key=LABEL_CREATED,
        pid_key=LABEL_OWNER_PID,
        start_key=LABEL_OWNER_START,
        ttl_key=LABEL_TTL,
    )


class TestContainerReaping:
    """Container abandonment mirrors the local reaper's dead-owner rule."""

    def test_dead_owner_container_is_abandoned(self):
        """A container whose owner PID is gone is abandoned."""
        assert _abandoned(_labels(4242), pid_alive=_dead) is True

    def test_live_owner_container_is_kept(self):
        """A container whose owner is alive (same incarnation) is kept."""
        assert (
            _abandoned(
                _labels(222, start="SAME"),
                pid_alive=_only(222),
                start_time_of=lambda pid: "SAME",
            )
            is False
        )

    def test_reused_pid_is_abandoned(self):
        """A live PID with a different start time is not the owner — abandoned."""
        assert (
            _abandoned(
                _labels(222, start="OLD"),
                pid_alive=_only(222),
                start_time_of=lambda pid: "NEW",
            )
            is True
        )

    def test_unidentifiable_owner_kept_until_ttl(self):
        """A garbled PID label leans on the TTL: fresh kept, stale reaped."""
        fresh = _labels("not-an-int", created=NOW - 10, ttl=3600)
        stale = _labels("not-an-int", created=NOW - 7200, ttl=3600)
        assert _abandoned(fresh) is False
        assert _abandoned(stale) is True

    def test_reap_is_a_noop_without_docker(self, monkeypatch):
        """Without the docker SDK / a daemon, reaping is a silent no-op."""
        # docker isn't a hard dependency; simulate its absence deterministically.
        import builtins

        real_import = builtins.__import__

        def no_docker(name, *args, **kwargs):
            if name == "docker":
                raise ImportError("no docker in this env")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_docker)
        assert reap_abandoned_containers(now=NOW) == []


class TestCorruptStampIsHandled:
    """A malformed owner stamp is tolerated, never crashing the sweep."""

    def test_null_pid_does_not_crash_sweep(self, tmp_path):
        """A null pid (int(None) -> TypeError) is treated as unstamped."""
        _stamp(tmp_path, "bad", {"pid": None}, mtime=NOW - 3600)
        _session_dir(tmp_path, "dead", pid=333)
        reaped = reap_local_workspaces(str(tmp_path), now=NOW, pid_alive=_dead)
        # Both go: the dead-owner one by PID, the null-pid one by age.
        assert sorted(reaped) == ["bad", "dead"]

    def test_vanished_dir_does_not_abort_listing(self, tmp_path):
        """A directory removed mid-scan is skipped, not fatal, for the lister."""
        _session_dir(tmp_path, "gone", pid=333, mtime=NOW - 10)

        def racing_pid_alive(pid):
            # Simulate a concurrent reaper removing the dir mid-scan.
            import shutil

            shutil.rmtree(tmp_path / "gone", ignore_errors=True)
            return False

        infos = list_local_workspaces(
            str(tmp_path), now=NOW, pid_alive=racing_pid_alive
        )
        assert infos == []  # skipped cleanly, no exception
