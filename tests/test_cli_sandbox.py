"""Tests for the ``hugin sandbox`` CLI command."""

import argparse
import json
import os

from gimle.hugin.cli.cli import cmd_sandbox
from gimle.hugin.sandbox.local import OWNER_FILE


def _abandoned(root, name):
    """Create a workspace whose owner PID is (almost certainly) dead."""
    path = os.path.join(str(root), name)
    os.makedirs(path)
    with open(os.path.join(path, OWNER_FILE), "w") as handle:
        json.dump({"pid": 2_000_000_000, "created": 0.0}, handle)


def test_prune_removes_abandoned_workspace(tmp_path, capsys):
    """`hugin sandbox prune` reaps a dead-owner workspace and reports it."""
    _abandoned(tmp_path, "sess-x")
    args = argparse.Namespace(action="prune", root=str(tmp_path))

    rc = cmd_sandbox(args)

    assert rc == 0
    assert not os.path.exists(tmp_path / "sess-x")
    assert "sess-x" in capsys.readouterr().out


def test_list_reports_workspaces(tmp_path, capsys):
    """`hugin sandbox list` prints a row per workspace without removing any."""
    _abandoned(tmp_path, "sess-y")
    args = argparse.Namespace(action="list", root=str(tmp_path))

    rc = cmd_sandbox(args)

    assert rc == 0
    assert os.path.isdir(tmp_path / "sess-y")  # list must not delete
    out = capsys.readouterr().out
    assert "sess-y" in out
    assert "dead" in out


def test_list_on_empty_root(tmp_path, capsys):
    """Listing a root with no workspaces says so cleanly."""
    args = argparse.Namespace(action="list", root=str(tmp_path))
    assert cmd_sandbox(args) == 0
    assert "No sandbox workspaces" in capsys.readouterr().out
