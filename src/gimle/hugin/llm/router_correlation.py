"""Per-edition correlation header for gimle-router.

One ``Session`` run is one "edition". When enabled, this stamps the same
``x-gimle-task`` header on every Anthropic/OpenAI request of that edition so a
router in front of the providers can group the edition's sub-agent calls
(orchestrator, analyst, editor) under one id. ``x-gimle-task`` is gimle-router's
task-id contract; its wire value here is the hugin ``session.id``.

Opt-in: only emitted when ``HUGIN_GIMLE_ROUTER`` is truthy, so a default hugin
deployment that never runs the router sends nothing extra to the providers
(mirrors the ``HUGIN_CAPTURE_RENDERED_PROMPTS`` precedent).

Mechanism: the value is bound once at the single LLM gateway
(``AskOracle.step``) from ``session.id`` and read by the provider adapters when
they build request headers — a request-scoped ``ContextVar`` carries it without
threading a parameter through every model signature. The safety invariant is
that the scope wraps ONLY the one synchronous, non-reentrant ``chat_completion``
call (set immediately before, reset in ``finally``); do NOT widen it. That tight
scope — not single-threadedness — is what stops one edition's id leaking into
another's call; ``ContextVar`` is also per-thread, so the threaded interactive
runner is safe too. Ollama is local and not fronted by the router, so its
adapter is intentionally not stamped.
"""

from __future__ import annotations

import contextvars
import os
from contextlib import contextmanager
from typing import Dict, Iterator, Optional

# gimle-router's task-id header. Its wire value is the hugin Session id; the
# router groups every call sharing this value as one edition.
ROUTER_TASK_HEADER = "x-gimle-task"

_ENABLE_FLAG = "HUGIN_GIMLE_ROUTER"

_session_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "gimle_router_session_id", default=None
)


def _enabled() -> bool:
    return os.getenv(_ENABLE_FLAG, "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


@contextmanager
def correlation_scope(session_id: Optional[str]) -> Iterator[None]:
    """Bind ``session_id`` as the current edition for the block.

    Wrap ONLY the synchronous gateway call — see the module note on not
    widening this scope.
    """
    token = _session_id.set(session_id)
    try:
        yield
    finally:
        _session_id.reset(token)


def router_headers() -> Dict[str, str]:
    """Return the gimle-router correlation headers for the current edition.

    The ``x-gimle-task`` header when the integration is enabled and a session
    is in scope, else ``{}`` (so providers get nothing extra by default).
    """
    if not _enabled():
        return {}
    session_id = _session_id.get()
    return {ROUTER_TASK_HEADER: session_id} if session_id else {}
