"""Redaction for anything read out of persisted traces.

Traces are stored verbatim: ``ToolCall.args`` is the model's raw argument dict,
``ToolResult.result`` is whatever the tool returned, and with
``HUGIN_CAPTURE_RENDERED_PROMPTS=1`` the full rendered prompts are kept too.
Nothing in the storage layer redacts -- ``_sanitize_for_json`` only coerces
types.

So any summary built from traces is a path by which a credential in a run
reaches a terminal, a CI log, or a model provider. Error strings are the worst
offender: a 401 carries the key in the query string, and a traceback carries the
failing call's arguments.
"""

import re
from typing import Any, Dict, List

# Ordered most specific first; each is replaced wholesale.
_PATTERNS = (
    re.compile(r"-----BEGIN[^-]*PRIVATE KEY-----.*?-----END[^-]*-----", re.S),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{8,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}"),
    re.compile(r"\bAKIA[0-9A-Z]{8,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{8,}"),
    re.compile(
        r"\bey[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+"
    ),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{8,}", re.I),
    re.compile(
        r"(?<=[?&])[A-Za-z_\-]*(?:key|token|secret|password|pwd)=[^&\s\"']+",
        re.I,
    ),
    re.compile(
        r"\b(?:authorization|api[ _-]?key|access[ _-]?token|refresh[ _-]?token|"
        r"token|secret|password|passwd|pwd)\s*[:=]\s*"
        r"(?:[\"'][^\"'\r\n]+[\"']|[^,;\r\n]+)",
        re.I,
    ),
    re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
)

REDACTED = "[redacted]"

# Anything that looks like a value rather than structure gets masked out of an
# error signature, so two runs failing the same way group together.
_VOLATILE = (
    (re.compile(r"'[^']*'|\"[^\"]*\""), "'?'"),
    (re.compile(r"\b[0-9a-fA-F]{8,}\b"), "<hex>"),
    (re.compile(r"\b\d+\b"), "<n>"),
    (re.compile(r"https?://\S+"), "<url>"),
    (re.compile(r"(/[\w.\-]+){2,}"), "<path>"),
)

MAX_SIGNATURE = 200


def redact(text: Any) -> Any:
    """Mask credential-shaped substrings in ``text``.

    Accepts ``Any`` because it is fed values read straight out of trace JSON,
    which is not guaranteed to be a string.
    """
    if not isinstance(text, str):
        return text
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def error_signature(text: Any) -> str:
    """Reduce an error message to a groupable, value-free signature.

    Two jobs at once, and that is deliberate: masking the variable parts is
    what makes "the same failure" countable, and the variable parts are exactly
    where credentials and personal data live. Reporting raw messages would give
    better-looking detail and leak.
    """
    if not isinstance(text, str):
        text = str(text)
    signature = redact(text.strip())
    for pattern, placeholder in _VOLATILE:
        signature = pattern.sub(placeholder, signature)
    signature = " ".join(signature.split())
    if len(signature) > MAX_SIGNATURE:
        signature = signature[:MAX_SIGNATURE] + "..."
    return signature


def redact_structure(value: Any, _depth: int = 0) -> Any:
    """Recursively redact strings inside a nested structure."""
    if _depth > 6:
        return "..."
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {
            str(redact(str(key))): redact_structure(item, _depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_structure(item, _depth + 1) for item in value[:20]]
    return value


def top_counts(counter: Dict[str, int], limit: int = 5) -> List[Dict[str, Any]]:
    """Return the ``limit`` most common entries, largest first."""
    ordered = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"value": key, "count": count} for key, count in ordered[:limit]]
