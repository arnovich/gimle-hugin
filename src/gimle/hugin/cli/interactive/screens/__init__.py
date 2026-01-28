"""Screen classes for the interactive TUI."""

from gimle.hugin.cli.interactive.screens.agents import AgentsScreen
from gimle.hugin.cli.interactive.screens.base import BaseScreen
from gimle.hugin.cli.interactive.screens.detail import DetailScreen
from gimle.hugin.cli.interactive.screens.interactions import InteractionsScreen
from gimle.hugin.cli.interactive.screens.logs import LogsScreen
from gimle.hugin.cli.interactive.screens.sessions import SessionsScreen

__all__ = [
    "BaseScreen",
    "SessionsScreen",
    "AgentsScreen",
    "InteractionsScreen",
    "DetailScreen",
    "LogsScreen",
]
