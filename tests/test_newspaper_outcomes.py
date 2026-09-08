"""Real newspaper rendering and session reporting, with no provider calls."""

import asyncio
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from apps.financial_newspaper import run as newspaper
from apps.financial_newspaper.outcomes import assess_edition
from apps.financial_newspaper.tools.update_newspaper_layout import (
    update_newspaper_layout,
)
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from tests.test_session_router_outcome import _agent


def _session(count=2, expected=2, finish_type="success"):
    environment = Environment()
    environment.env_vars = {
        "current_date": "September 8, 2026",
        "target_symbols": ["TEST"],
        "number_of_articles": expected,
        "newspaper_articles": [
            {
                "id": f"article-{i}",
                "headline": f"Fixture headline {i}",
                "content": f"Fixture article content {i}.",
                "category": "markets",
                "published": "2026-09-08T12:00:00",
                "related_symbols": ["TEST"],
                "word_count": 4,
                "quality_score": 10,
            }
            for i in range(count)
        ],
    }
    session = Session(environment)
    root = _agent(session, finish_type=finish_type)
    return session, root


def _render(root):
    response = update_newspaper_layout(root.stack)
    assert not response.is_error, response.content
    return False  # root already has a terminal fixture result


@pytest.fixture
def layout_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "layouts"
    path.mkdir()
    monkeypatch.setattr(newspaper, "LAYOUT_DIR", path)
    monkeypatch.setattr(newspaper.webbrowser, "open", Mock())
    return path


def _evidence(layout_dir):
    paths = list(layout_dir.glob("outcome_*.json"))
    assert len(paths) == 1
    return json.loads(paths[0].read_text())


def test_stale_layout_cannot_make_a_new_edition_successful(layout_dir):
    stale = layout_dir / "latest.html"
    stale.write_text("old newspaper")
    session, root = _session()
    root.step = Mock(return_value=False)
    with patch("gimle.hugin.agent.session.report_outcome") as report:
        assert newspaper.run_newspaper_generation(session, 5) is False
    report.assert_called_once_with(session.id, success=False)
    assert stale.read_text() == "old newspaper"
    assert _evidence(layout_dir)["checks"]["current_execution"] is False


def test_fresh_complete_layout_reports_once_without_editor_score(layout_dir):
    session, root = _session()
    root.step = Mock(side_effect=lambda: _render(root))
    with patch("gimle.hugin.agent.session.report_outcome") as report:
        assert newspaper.run_newspaper_generation(session, 5) is True
        session.finalize_router_outcome()
    report.assert_called_once_with(session.id, success=True)
    evidence = _evidence(layout_dir)
    assert all(evidence["checks"].values())
    assert evidence["success"] is True
    assert evidence["quality"] == {
        "independent_evaluation": "not_run",
        "editor_self_score_advisory": 10.0,
    }
    assert Path(evidence["layout_file"]).is_file()
    assert Path(evidence["layout_file"]).name != "latest.html"
    assert session.router_outcome_validator is None


@pytest.mark.parametrize(
    "change,failed_check",
    [
        ("partial", "required_article_count"),
        ("empty_content", "article_fields"),
        ("duplicate_id", "unique_article_ids"),
        ("changed_article", "rendered_current_articles"),
        ("changed_file", "layout_digest"),
        ("missing_file", "layout_digest"),
        ("wrong_execution", "current_execution"),
        ("wrong_session", "current_execution"),
        ("symlink", "layout_in_output_directory"),
    ],
)
def test_invalid_edition_is_a_failure(layout_dir, change, failed_check):
    session, root = _session(count=1 if change == "partial" else 2)
    articles = session.environment.env_vars["newspaper_articles"]
    if change == "empty_content":
        articles[0]["content"] = " "
    if change == "duplicate_id":
        articles[1]["id"] = articles[0]["id"]

    def render_then_change():
        _render(root)
        receipt = session.environment.env_vars["newspaper_layout_receipt"]
        path = Path(receipt["layout_file"])
        if change == "changed_article":
            articles[0]["content"] = "Revised after rendering"
        elif change == "changed_file":
            path.write_text("Different output")
        elif change == "missing_file":
            path.unlink()
        elif change == "wrong_execution":
            receipt["execution_id"] = "another-run"
        elif change == "wrong_session":
            receipt["session_id"] = "another-session"
        elif change == "symlink":
            target = layout_dir / "target.html"
            path.rename(target)
            path.symlink_to(target)
        return False

    root.step = Mock(side_effect=render_then_change)
    with patch("gimle.hugin.agent.session.report_outcome") as report:
        assert newspaper.run_newspaper_generation(session, 5) is False
    report.assert_called_once_with(session.id, success=False)
    assert _evidence(layout_dir)["checks"][failed_check] is False


def test_valid_output_cannot_promote_a_failed_root(layout_dir):
    session, root = _session(finish_type="failure")
    root.step = Mock(side_effect=lambda: _render(root))
    with patch("gimle.hugin.agent.session.report_outcome") as report:
        assert newspaper.run_newspaper_generation(session, 5) is False
    report.assert_called_once_with(session.id, success=False)
    assert _evidence(layout_dir)["output_complete"] is True
    assert _evidence(layout_dir)["success"] is False


@pytest.mark.parametrize("active", [False, True])
def test_wait_or_exhaustion_is_reported_as_incomplete(layout_dir, active):
    session, root = _session(finish_type=None)
    root.step = Mock(return_value=active)
    with patch("gimle.hugin.agent.session.report_outcome") as report:
        assert newspaper.run_newspaper_generation(session, 1) is False
    report.assert_called_once_with(session.id, success=False)
    assert _evidence(layout_dir)["success"] is False


@pytest.mark.parametrize(
    "error",
    [RuntimeError, TimeoutError, KeyboardInterrupt, asyncio.CancelledError],
)
def test_interruption_reports_once_and_preserves_exception(layout_dir, error):
    session, root = _session()
    root.step = Mock(side_effect=error("interrupted"))
    with patch("gimle.hugin.agent.session.report_outcome") as report:
        with pytest.raises(error, match="interrupted"):
            newspaper.run_newspaper_generation(session, 5)
    report.assert_called_once_with(session.id, success=False)
    assert _evidence(layout_dir)["success"] is False
    assert session.router_outcome_validator is None


def test_layouts_from_other_sessions_do_not_overwrite_evidence(layout_dir):
    first, first_root = _session()
    second, second_root = _session()
    first_root.step = Mock(side_effect=lambda: _render(first_root))
    second_root.step = Mock(side_effect=lambda: _render(second_root))
    with patch("gimle.hugin.agent.session.report_outcome"):
        assert newspaper.run_newspaper_generation(first, 5)
        first_file = first.environment.env_vars["newspaper_layout_receipt"][
            "layout_file"
        ]
        first_bytes = Path(first_file).read_bytes()
        assert newspaper.run_newspaper_generation(second, 5)
    second_file = second.environment.env_vars["newspaper_layout_receipt"][
        "layout_file"
    ]
    assert first_file != second_file
    assert Path(first_file).read_bytes() == first_bytes
    assert assess_edition(first)["output_complete"]
    assert assess_edition(second)["output_complete"]
    assert len(list(layout_dir.glob("outcome_*.json"))) == 2


def test_existing_application_validator_is_preserved(layout_dir):
    session, root = _session()
    previous = Mock(return_value=False)
    session.router_outcome_validator = previous
    root.step = Mock(side_effect=lambda: _render(root))
    with patch("gimle.hugin.agent.session.report_outcome") as report:
        assert newspaper.run_newspaper_generation(session, 5) is False
    report.assert_called_once_with(session.id, success=False)
    previous.assert_called_once_with(session)
    assert session.router_outcome_validator is previous


def test_same_session_cannot_silently_reuse_a_terminal_outcome(layout_dir):
    session, root = _session()
    root.step = Mock(side_effect=lambda: _render(root))
    with patch("gimle.hugin.agent.session.report_outcome") as report:
        assert newspaper.run_newspaper_generation(session, 5)
        with pytest.raises(ValueError, match="fresh session"):
            newspaper.run_newspaper_generation(session, 5)
    report.assert_called_once_with(session.id, success=True)
