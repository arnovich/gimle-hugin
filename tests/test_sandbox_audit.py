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
