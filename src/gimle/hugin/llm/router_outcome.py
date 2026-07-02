"""Per-edition outcome report for gimle-router.

Companion to ``router_correlation.py``: where that stamps ``x-gimle-task`` on an
edition's LLM calls so the router can group them, this reports the edition's
RESULT once it finishes, so the router's live A/B tripwire can tell whether a
cheaper candidate model was good enough — without it the router sees the calls
but never learns if the edition succeeded.

One ``Session`` run is one edition. Its result is POSTed ONCE, at the edition
boundary, to the router's control-plane endpoint ``POST {base}/gimle/outcome``
as ``{"task_id": session.id, "success": <bool>, "score": <number>}`` (either
field optional; at least one required by the router).

Opt-in and best-effort, mirroring the header:
  - Only sent when ``HUGIN_GIMLE_ROUTER`` is truthy (the same flag that enables
    the header) — a default run reports nothing.
  - Target base URL: the outcome endpoint lives on the SAME router the model
    calls already go through, so by default it reuses ``ANTHROPIC_BASE_URL`` (or
    ``OPENAI_BASE_URL``) — point that at the router and there's nothing else to
    set. ``GIMLE_ROUTER_URL`` is only an override for the rare case where the
    control-plane is on a different host than the provider proxy.
  - Any error is logged and swallowed — an eval signal must never fail the
    edition it measures.

Uses only the standard library so the loose HTTP-only coupling to the router
adds no dependency (matching hugin's deliberately gimle-free runtime deps).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_ENABLE_FLAG = "HUGIN_GIMLE_ROUTER"
# Prefer an explicit override, then the provider base URLs the model calls
# already use (same router), then a local default. One server, one place to set.
_URL_ENVS = ("GIMLE_ROUTER_URL", "ANTHROPIC_BASE_URL", "OPENAI_BASE_URL")
_DEFAULT_URL = "http://127.0.0.1:4000"
_OUTCOME_PATH = "/gimle/outcome"
_TIMEOUT_SECONDS = 5.0


def _enabled() -> bool:
    return os.getenv(_ENABLE_FLAG, "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _base_url() -> str:
    for env in _URL_ENVS:
        value = os.getenv(env, "").strip().rstrip("/")
        if value:
            return value
    return _DEFAULT_URL


def report_outcome(
    task_id: Optional[str],
    *,
    success: Optional[bool] = None,
    score: Optional[float] = None,
) -> bool:
    """Report one edition's result to gimle-router.

    Returns ``True`` iff a report was sent and accepted; ``False`` if the
    integration is disabled, there is nothing to report, or the POST failed.
    Never raises — reporting an outcome must not break the run that produced it.

    No-ops (``False``) when the flag is off, ``task_id`` is empty, or neither
    ``success`` nor ``score`` is given.
    """
    if not _enabled() or not task_id:
        return False
    payload: Dict[str, object] = {"task_id": task_id}
    if success is not None:
        payload["success"] = bool(success)
    if score is not None:
        payload["score"] = float(score)
    if "success" not in payload and "score" not in payload:
        return False

    url = _base_url() + _OUTCOME_PATH
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as resp:
            resp.read()  # drain so the connection can be reused/closed cleanly
        return True
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning(
            "gimle-router: failed to report outcome for task %s: %s",
            task_id,
            exc,
        )
        return False
