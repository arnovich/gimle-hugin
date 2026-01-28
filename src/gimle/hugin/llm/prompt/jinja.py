"""Jinja template rendering module."""

import re
from typing import Any, Dict

from jinja2 import Environment


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


def render_jinja(template: str, inputs: Dict[str, Any]) -> str:
    """Render a Jinja template with the given inputs."""
    env = Environment()
    for k, v in inputs.items():
        env.globals[k] = v
    return str(env.from_string(template).render().strip())


def render_jinja_recursive(template: str, inputs: Dict[str, Any]) -> str:
    """Recursively render a Jinja template until no more Jinja syntax remains."""
    if not contains_jinja(template):
        return template
    return render_jinja_recursive(render_jinja(template, inputs), inputs)
