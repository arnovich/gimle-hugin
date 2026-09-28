"""Storage provenance must never authorize imports into operator processes."""

import logging
import sys
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from gimle.hugin.cli import cli, helpers, monitor_agents
from gimle.hugin.cli.interactive.state import AppState


def test_monitor_startup_ignores_storage_extension_paths(
    extension_trust_probe: Any,
) -> None:
    """Opening a stored trace must not execute the metadata writer's code."""
    probe = extension_trust_probe
    monitor_agents.run_monitor_server(
        storage_path=str(probe.storage_path), open_browser=False
    )
    assert not probe.attacker_marker.exists()


@pytest.mark.parametrize(
    "method",
    ["serve_agent_data", "serve_artifact_viewer", "serve_interaction_detail"],
)
def test_monitor_requests_ignore_late_storage_extension_paths(
    extension_trust_probe: Any, method: str
) -> None:
    """Later HTTP requests cannot import paths added after monitor startup."""
    probe = extension_trust_probe
    handler = object.__new__(monitor_agents.AgentMonitorHTTPRequestHandler)
    handler.wfile = BytesIO()
    handler.send_error = MagicMock()
    handler.load_agent_lightweight = MagicMock(return_value=None)
    getattr(handler, method)("missing")
    assert not probe.attacker_marker.exists()


def test_monitor_explicit_extensions_load_with_source(
    extension_trust_probe: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """An explicit package path works and is identified in startup output."""
    probe = extension_trust_probe
    monitor_agents.run_monitor_server(
        storage_path=str(probe.storage_path),
        open_browser=False,
        extension_paths=[str(probe.trusted)],
    )
    assert probe.trusted_marker.exists()
    assert not probe.attacker_marker.exists()
    output = capsys.readouterr().out
    assert str(probe.trusted) in output
    assert "extension_paths" in output


def test_interactive_resume_requires_explicit_task_path(
    extension_trust_probe: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """Storage metadata cannot supply the environment for resumed execution."""
    caplog.set_level(
        logging.WARNING, logger="gimle.hugin.cli.interactive.state"
    )
    probe = extension_trust_probe
    state = AppState(str(probe.storage_path))
    assert state.load_agent_for_resume(probe.session.id, probe.agent.id) is None
    assert not probe.attacker_marker.exists()
    assert "--task-path" in caplog.text


@pytest.mark.parametrize("metadata_exists", [False, True])
def test_interactive_resume_uses_only_explicit_task_path(
    extension_trust_probe: Any,
    metadata_exists: bool,
) -> None:
    """Trusted resumption works even when storage names an unrelated package."""
    probe = extension_trust_probe
    if not metadata_exists:
        (probe.storage_path / ".hugin_metadata.json").unlink()
    state = AppState(str(probe.storage_path), task_path=str(probe.trusted))
    result = state.load_agent_for_resume(probe.session.id, probe.agent.id)
    assert result is not None
    session, agent = result
    try:
        assert agent.id == probe.agent.id
        assert probe.trusted_marker.exists()
        assert not probe.attacker_marker.exists()
    finally:
        session.close()


def test_failed_explicit_resume_does_not_fall_back_to_storage(
    extension_trust_probe: Any,
) -> None:
    """A missing trusted package must not trigger imports from metadata."""
    probe = extension_trust_probe
    state = AppState(
        str(probe.storage_path), task_path=str(probe.trusted / "missing")
    )
    assert state.load_agent_for_resume(probe.session.id, probe.agent.id) is None
    assert not probe.attacker_marker.exists()


def test_interactive_browsing_needs_no_task_path(
    extension_trust_probe: Any,
) -> None:
    """Viewing stored sessions remains available without authorizing imports."""
    probe = extension_trust_probe
    state = AppState(str(probe.storage_path))
    state.refresh_data()
    assert any(session.id == probe.session.id for session in state.sessions)
    assert not probe.attacker_marker.exists()


def test_monitor_cli_forwards_repeated_explicit_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise both parsers so the top-level CLI preserves explicit trust."""
    run_server = MagicMock()
    monkeypatch.setattr(monitor_agents, "run_monitor_server", run_server)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "hugin",
            "monitor",
            "--storage-path",
            str(tmp_path),
            "--extension-path",
            "first",
            "--extension-path",
            "second",
            "--no-browser",
        ],
    )
    assert cli.main() == 0
    assert run_server.call_args.kwargs["extension_paths"] == ["first", "second"]


@pytest.mark.parametrize("paths", [None, ["trusted_one", "trusted_two"]])
def test_app_monitor_forwards_only_explicit_paths(
    monkeypatch: pytest.MonkeyPatch, paths: Any
) -> None:
    """App launches opt into named packages without trusting storage paths."""
    process = MagicMock()
    monkeypatch.setattr(helpers.subprocess, "Popen", process)
    monkeypatch.setattr(helpers.time, "sleep", lambda _: None)
    helpers.start_monitor_dashboard("storage", extension_paths=paths)
    command = process.call_args.args[0]
    selected = [
        command[index + 1]
        for index, value in enumerate(command)
        if value == "--extension-path"
    ]
    assert selected == (paths or [])
