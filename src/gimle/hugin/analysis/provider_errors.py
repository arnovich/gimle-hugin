"""Tell a provider outage apart from an agent doing badly.

Both look identical from outside: the run did not finish. Conflating them is
not cosmetic. A golden-set run during an exhausted API balance once scored 11
of 15 cases as build failures and reported zero infrastructure failures --
indistinguishable from the builder collapsing, when nothing had been asked of
it. The same confusion inside a before/after replay is worse: it would call a
billing lapse a regression and revert a change that was fine.

Lives in `src` rather than beside either consumer because the eval harness and
the replay both need it, and two copies would drift into disagreeing about
what counts as an outage.
"""

from typing import Tuple

# Blips worth waiting out: the same request may succeed on a retry.
TRANSIENT_MARKERS: Tuple[str, ...] = (
    "APIConnectionError",
    "APITimeoutError",
    "RateLimitError",
    "InternalServerError",
    "overloaded_error",
    "Connection error",
    "Request timed out",
    "Too Many Requests",
)

# Also not the agent's fault, but retrying cannot help: the account cannot
# make the call at all.
TERMINAL_MARKERS: Tuple[str, ...] = (
    "credit balance is too low",
    "authentication_error",
    "invalid x-api-key",
    "permission_error",
    "billing",
)

PROVIDER_MARKERS: Tuple[str, ...] = TRANSIENT_MARKERS + TERMINAL_MARKERS


def is_provider_failure(text: str) -> bool:
    """Return True when the text shows the provider, not the agent, failed."""
    return any(marker in text for marker in PROVIDER_MARKERS)


def is_retryable(text: str) -> bool:
    """Return True when re-running could plausibly succeed."""
    return any(marker in text for marker in TRANSIENT_MARKERS)
