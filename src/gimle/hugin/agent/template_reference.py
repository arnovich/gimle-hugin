"""Shared syntax for bare prompt-template references."""

import re

BARE_TEMPLATE_REFERENCE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
