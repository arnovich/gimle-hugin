"""Gimle Hugin Apps - Production-like application showcases."""

from pathlib import Path


def get_apps_path() -> Path:
    """Get the path to the bundled apps directory."""
    return Path(__file__).parent
