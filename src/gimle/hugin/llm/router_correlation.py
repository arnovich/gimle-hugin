"""Per-edition + per-agent correlation headers for gimle-router.

One ``Session`` run is one "edition". When enabled, this stamps two headers on
every Anthropic/OpenAI request of that edition:

  - ``x-gimle-task`` — gimle-router's task-id contract; its wire value is the
    hugin ``session.id``, so the router groups the edition's sub-agent calls
    (journalist, analyst, editor) under one task.
  - ``x-gimle-route`` — gimle-router's use-case key; its value is the calling
    agent's config name (its role), so the router keys each role as its own
    stable use-case (``tag:<role>``). This matters because the router otherwise
    fingerprints the system prompt, which forks a new key whenever the app
    injects a volatile span (the current date) — the explicit route is immune.

Opt-in: only emitted when ``HUGIN_GIMLE_ROUTER`` is truthy, so a default hugin
deployment that never runs the router sends nothing extra to the providers
(mirrors the ``HUGIN_CAPTURE_RENDERED_PROMPTS`` precedent).

Mechanism: both values are bound once at the single LLM gateway
(``AskOracle.step``) — ``session.id`` and the agent's ``config.name`` — and read
by the provider adapters when they build request headers, via request-scoped
``ContextVar``s that carry them without threading a parameter through every
model signature. The safety invariant is that the scope wraps ONLY the one
synchronous, non-reentrant ``chat_completion`` call (set immediately before,
reset in ``finally``); do NOT widen it. That tight scope — not
single-threadedness — is what stops one edition's id leaking into another's
call; ``ContextVar`` is also per-thread, so the threaded interactive runner is
safe too. Ollama is local and not fronted by the router, so its adapter is
intentionally not stamped.
"""

from __future__ import annotations

import contextvars
import os
from contextlib import contextmanager
from typing import Dict, Iterator, Optional

# gimle-router's task-id header. Its wire value is the hugin Session id; the
# router groups every call sharing this value as one edition.
ROUTER_TASK_HEADER = "x-gimle-task"

# gimle-router's use-case route header. Its wire value is the calling agent's
# config name (role); the router keys each role as a stable use-case, bypassing
# system-prompt fingerprinting (which drifts when a date is injected).
ROUTER_ROUTE_HEADER = "x-gimle-route"

_ENABLE_FLAG = "HUGIN_GIMLE_ROUTER"

_session_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "gimle_router_session_id", default=None
)
_route: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "gimle_router_route", default=None
)


def _enabled() -> bool:
    return os.getenv(_ENABLE_FLAG, "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


@contextmanager
def correlation_scope(
    session_id: Optional[str], route: Optional[str] = None
) -> Iterator[None]:
    """Bind ``session_id`` (the edition) and ``route`` (the agent's use-case).

    Wrap ONLY the synchronous gateway call — see the module note on not
    widening this scope.
    """
    session_token = _session_id.set(session_id)
    route_token = _route.set(route)
    try:
        yield
    finally:
        _route.reset(route_token)
        _session_id.reset(session_token)


def router_headers() -> Dict[str, str]:
    """Return the gimle-router correlation headers for the current call.

    ``x-gimle-task`` (the edition/session id) and, when one is in scope,
    ``x-gimle-route`` (the agent's use-case key) — only when the integration is
    enabled and each value is present, else ``{}`` (providers get nothing extra
    by default).
    """
    if not _enabled():
        return {}
    headers: Dict[str, str] = {}
    session_id = _session_id.get()
    if session_id:
        headers[ROUTER_TASK_HEADER] = session_id
    route = _route.get()
    if route:
        headers[ROUTER_ROUTE_HEADER] = route
    return headers
