"""Tests for the ``CommandAudit`` command log and outcome counters.

Two properties matter: outcome counters are always kept (even with no file),
and when a path is given each command is appended as one JSON line that can be
grepped after the fact. Best-effort writing must never raise.
"""

import json
import os

from gimle.hugin.sandbox.audit import CommandAudit


def _entries(path):
    """Read back the JSONL audit file as a list of dicts."""
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class TestCounters:
    """Counters partition attempts by outcome, with or without a file."""

    def test_counts_without_a_path(self):
        """With no path, counters still tally every recorded outcome."""
        audit = CommandAudit()
        audit.record(session_id="s", agent_id="a", command="ls", outcome="run")
        audit.record(
            session_id="s", agent_id="a", command="dd", outcome="denied"
        )
        audit.record(session_id="s", agent_id="a", command="ls", outcome="run")
        assert audit.counters["run"] == 2
        assert audit.counters["denied"] == 1

    def test_unrecorded_outcome_is_zero(self):
        """A never-seen outcome reads back as zero, not a KeyError."""
        audit = CommandAudit()
        assert audit.counters["timed_out"] == 0


class TestFile:
    """When a path is set, each command is appended as a JSON line."""

    def test_appends_one_line_per_command(self, tmp_path):
        """Two commands produce two JSON lines in order."""
        path = str(tmp_path / "sub" / "audit.jsonl")
        audit = CommandAudit(path)
        audit.record(
            session_id="s", agent_id="a", command="echo hi", outcome="run"
        )
        audit.record(
            session_id="s", agent_id="a", command="rm x", outcome="denied"
        )
        entries = _entries(path)
        assert [e["command"] for e in entries] == ["echo hi", "rm x"]
        assert [e["outcome"] for e in entries] == ["run", "denied"]

    def test_records_the_full_outcome(self, tmp_path):
        """Exit code, duration, and the flag fields are all persisted."""
        path = str(tmp_path / "audit.jsonl")
        audit = CommandAudit(path)
        audit.record(
            session_id="sess",
            agent_id="agent",
            command="sleep 99",
            outcome="timed_out",
            exit_code=-1,
            duration_s=1.5,
            truncated=True,
            timed_out=True,
        )
        (entry,) = _entries(path)
        assert entry["session_id"] == "sess"
        assert entry["agent_id"] == "agent"
        assert entry["exit_code"] == -1
        assert entry["duration_s"] == 1.5
        assert entry["truncated"] is True
        assert entry["timed_out"] is True
        assert entry["oom_killed"] is False

    def test_creates_parent_directories(self, tmp_path):
        """The audit file's parent dirs are created on first write."""
        path = str(tmp_path / "deep" / "nested" / "audit.jsonl")
        CommandAudit(path).record(
            session_id="s", agent_id="a", command="ls", outcome="run"
        )
        assert os.path.isfile(path)

    def test_write_failure_is_swallowed(self, tmp_path):
        """A path that cannot be written (a directory) never raises."""
        path = str(tmp_path)  # a directory: open-for-append will fail
        audit = CommandAudit(path)
        audit.record(session_id="s", agent_id="a", command="ls", outcome="run")
        assert audit.counters["run"] == 1  # counted despite the write failing


class TestBumpAndSummary:
    """Thread-safe counter increments and snapshots for out-of-record bumps."""

    def test_bump_increments_under_the_lock(self):
        """bump() tallies a counter not tied to a recorded command outcome."""
        audit = CommandAudit()
        audit.bump("sandbox_starts")
        audit.bump("sandbox_starts")
        audit.bump("sandbox_start_failures")
        assert audit.counters["sandbox_starts"] == 2
        assert audit.counters["sandbox_start_failures"] == 1

    def test_summary_is_a_snapshot_copy(self):
        """summary() returns a plain dict copy, decoupled from later changes."""
        audit = CommandAudit()
        audit.record(session_id="s", agent_id="a", command="ls", outcome="run")
        snap = audit.summary()
        audit.record(session_id="s", agent_id="a", command="ls", outcome="run")
        assert snap == {"run": 1}  # frozen at the moment it was taken
        assert audit.summary() == {"run": 2}

    def test_empty_summary_is_an_empty_dict(self):
        """An unused audit summarizes to an empty dict (nothing to log)."""
        assert CommandAudit().summary() == {}


class TestRotation:
    """The JSONL file is bounded: it rotates to one .1 backup past the cap."""

    def test_rotates_past_the_cap_and_keeps_writing(self, tmp_path):
        """Once the file exceeds max_bytes it rotates; new lines still land."""
        path = str(tmp_path / "audit.jsonl")
        audit = CommandAudit(path, max_bytes=300)
        for i in range(50):
            audit.record(
                session_id="s", agent_id="a", command=f"cmd-{i}", outcome="run"
            )
        assert os.path.isfile(path + ".1")  # a backup was rotated out
        # The live file stays bounded (roughly the cap plus one entry).
        assert os.path.getsize(path) <= 300 + 1000
        # The most recent command is in the live file — not lost to rotation.
        assert _entries(path)[-1]["command"] == "cmd-49"

    def test_no_rotation_under_the_cap(self, tmp_path):
        """A small log never creates a backup."""
        path = str(tmp_path / "audit.jsonl")
        audit = CommandAudit(path, max_bytes=1_000_000)
        audit.record(session_id="s", agent_id="a", command="ls", outcome="run")
        assert not os.path.exists(path + ".1")

    def test_rotation_failure_is_swallowed(self, tmp_path, monkeypatch):
        """A failing rotation never fails the command; it keeps appending."""
        path = str(tmp_path / "audit.jsonl")
        audit = CommandAudit(path, max_bytes=10)
        audit.record(
            session_id="s", agent_id="a", command="first", outcome="run"
        )

        def _boom(*_args, **_kwargs):
            raise OSError("rotate failed")

        monkeypatch.setattr(os, "replace", _boom)
        # This record is now over the cap, so rotation is attempted and fails —
        # the command must still be counted and appended, never raise.
        audit.record(
            session_id="s", agent_id="a", command="second", outcome="run"
        )
        assert audit.counters["run"] == 2
        assert _entries(path)[-1]["command"] == "second"
