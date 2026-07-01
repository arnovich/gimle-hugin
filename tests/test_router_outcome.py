"""Tests for the gimle-router per-edition outcome report.

Covers the opt-in flag, the payload contract, target-URL config, and the
best-effort guarantee that a failed report never breaks the edition.
"""

import json
import urllib.error
from unittest.mock import patch

import pytest

from gimle.hugin.llm.router_outcome import report_outcome


@pytest.fixture
def enabled(monkeypatch):
    """Turn the opt-in integration on for a test."""
    monkeypatch.setenv("HUGIN_GIMLE_ROUTER", "1")


class _FakeResponse:
    """Minimal context-manager stand-in for a urlopen response."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b"ok"


def _capture():
    """Return a urlopen replacement that records the Request it was handed."""
    captured: dict = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["method"] = request.method
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse()

    return captured, fake_urlopen


# --- the opt-in flag -------------------------------------------------------


def test_disabled_by_default_sends_nothing():
    """With no flag set, nothing is posted and the call is a no-op."""
    with patch("urllib.request.urlopen") as urlopen:
        assert report_outcome("ed-1", success=True) is False
        urlopen.assert_not_called()


def test_enabled_posts_the_outcome(enabled):
    """With the flag on, the edition's result is POSTed as JSON."""
    captured, fake = _capture()
    with patch("urllib.request.urlopen", fake):
        sent = report_outcome("ed-1", success=True, score=8.0)
    assert sent is True
    assert captured["url"] == "http://127.0.0.1:4000/gimle/outcome"
    assert captured["method"] == "POST"
    assert captured["body"] == {
        "task_id": "ed-1",
        "success": True,
        "score": 8.0,
    }
    # urllib title-cases header names when storing them.
    assert captured["headers"].get("Content-type") == "application/json"
    assert captured["timeout"] == pytest.approx(5.0)


def test_success_only_and_score_only(enabled):
    """Each signal is optional; only what's provided is sent."""
    captured, fake = _capture()
    with patch("urllib.request.urlopen", fake):
        report_outcome("ed", success=False)
    assert captured["body"] == {"task_id": "ed", "success": False}
    with patch("urllib.request.urlopen", fake):
        report_outcome("ed", score=3.5)
    assert captured["body"] == {"task_id": "ed", "score": 3.5}


def test_custom_router_url_is_honored(enabled, monkeypatch):
    """The target is the router's own address, trailing slash tolerated."""
    monkeypatch.setenv("GIMLE_ROUTER_URL", "http://router.local:9000/")
    captured, fake = _capture()
    with patch("urllib.request.urlopen", fake):
        report_outcome("ed", success=True)
    assert captured["url"] == "http://router.local:9000/gimle/outcome"


# --- nothing to report -----------------------------------------------------


def test_empty_task_id_is_a_noop(enabled):
    """A missing edition id has nothing to correlate, so nothing is sent."""
    with patch("urllib.request.urlopen") as urlopen:
        assert report_outcome("", success=True) is False
        assert report_outcome(None, success=True) is False
        urlopen.assert_not_called()


def test_no_signal_is_a_noop(enabled):
    """Neither success nor score means there is nothing to report."""
    with patch("urllib.request.urlopen") as urlopen:
        assert report_outcome("ed") is False
        urlopen.assert_not_called()


# --- best-effort -----------------------------------------------------------


def test_network_error_is_swallowed(enabled):
    """A router that's down must not break the edition that produced the run."""

    def boom(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    with patch("urllib.request.urlopen", boom):
        assert report_outcome("ed", success=True) is False  # no raise
