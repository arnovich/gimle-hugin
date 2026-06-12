"""Jinja template rendering module."""

import re
from typing import Any, Dict

from jinja2 import ChainableUndefined, Environment

# Sentinel tokens used to hide literal Jinja delimiters from the recursive
# renderer. They wrap NUL bytes so they cannot collide with real prompt text,
# and are restored to their original delimiters on the final pass.
_LITERAL_DELIMITERS = {
    "{{": "\x00jinja-open-var\x00",
    "}}": "\x00jinja-close-var\x00",
    "{%": "\x00jinja-open-block\x00",
    "%}": "\x00jinja-close-block\x00",
    "{#": "\x00jinja-open-comment\x00",
    "#}": "\x00jinja-close-comment\x00",
}

# Match a ``{% raw %}…{% endraw %}`` block (whitespace/dash-trim tolerant).
_RAW_BLOCK = re.compile(
    r"\{%-?\s*raw\s*-?%\}(.*?)\{%-?\s*endraw\s*-?%\}",
    re.DOTALL,
)


def contains_jinja(txt: str) -> bool:
    """Check if text contains Jinja template syntax."""
    jinja_patterns = [
        r"\{\{.*?\}\}",
        r"\{%.*?%\}",
        r"\{#.*?#\}",
    ]

    for pattern in jinja_patterns:
        if re.search(pattern, txt):
            return True

    return False


def literal(value: Any) -> str:
    """Mark text as literal so its Jinja delimiters are never rendered.

    Use this for any value injected into a prompt as a ``template_inputs``
    value whose content must reach the model verbatim — e.g. untrusted,
    LLM-generated text. Any ``{{ … }}`` / ``{% … %}`` / ``{# … #}`` inside the
    value is neutralised here and restored after the recursive render
    completes, so it cannot be (mis)interpreted as a template on a later pass.

    This is stronger than wrapping in ``{% raw %}``: the value could itself
    contain ``{% endraw %}`` and break out of such a wrapper.
    """
    text = str(value)
    for delimiter, sentinel in _LITERAL_DELIMITERS.items():
        text = text.replace(delimiter, sentinel)
    return text


def _restore_literals(text: str) -> str:
    """Restore sentinel tokens back to their literal Jinja delimiters."""
    for delimiter, sentinel in _LITERAL_DELIMITERS.items():
        text = text.replace(sentinel, delimiter)
    return text


def _protect_raw_blocks(template: str) -> str:
    """Neutralise ``{% raw %}…{% endraw %}`` so it survives recursion.

    Jinja honours ``{% raw %}`` within a single pass, but the recursive
    renderer would re-evaluate the literal braces it emits on the next pass.
    Stripping the markers and escaping the inner delimiters up front makes the
    block survive every pass and be restored verbatim at the end.
    """
    return _RAW_BLOCK.sub(lambda m: literal(m.group(1)), template)


def render_jinja(template: str, inputs: Dict[str, Any]) -> str:
    """Render a Jinja template with the given inputs.

    Undefined variables — including attribute access on them — render to an
    empty string (``ChainableUndefined``), so ``{{ x }}`` and ``{{ x.attr }}``
    behave consistently when ``x`` is missing.
    """
    env = Environment(undefined=ChainableUndefined)
    for k, v in inputs.items():
        env.globals[k] = v
    return str(env.from_string(template).render().strip())


def render_jinja_recursive(template: str, inputs: Dict[str, Any]) -> str:
    """Recursively render a Jinja template until no Jinja syntax remains.

    Literal regions — ``{% raw %}`` blocks in the template and values marked
    with :func:`literal` — are hidden from the recursion and restored to their
    original delimiters once all real templating has resolved.
    """
    protected = _protect_raw_blocks(template)
    return _restore_literals(_render_to_fixpoint(protected, inputs))


def _render_to_fixpoint(template: str, inputs: Dict[str, Any]) -> str:
    """Render repeatedly until no resolvable Jinja syntax is left."""
    if not contains_jinja(template):
        return template
    return _render_to_fixpoint(render_jinja(template, inputs), inputs)
