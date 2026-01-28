"""Color definitions for the curses TUI."""

import curses
import logging
from typing import Dict

# Color pair IDs
COLOR_NORMAL = 0
COLOR_HEADER = 1
COLOR_SELECTED = 2
COLOR_STATUS = 3
COLOR_ORACLE = 4
COLOR_TOOL = 5
COLOR_TASK = 6
COLOR_ERROR = 7
COLOR_SUCCESS = 8
COLOR_DIM = 9
COLOR_HIGHLIGHT = 10
COLOR_RUNNING = 11

# Log level colors
COLOR_LOG_DEBUG = 12
COLOR_LOG_INFO = 13
COLOR_LOG_WARNING = 14
COLOR_LOG_ERROR = 15
COLOR_LOG_PANEL = 16


def init_colors() -> Dict[str, int]:
    """Initialize curses color pairs. Returns dict of color_name -> pair_number."""
    curses.start_color()
    curses.use_default_colors()

    # Define color pairs (foreground, background)
    # Using -1 for default terminal background
    curses.init_pair(COLOR_HEADER, curses.COLOR_WHITE, curses.COLOR_BLUE)
    curses.init_pair(COLOR_SELECTED, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(COLOR_STATUS, curses.COLOR_WHITE, curses.COLOR_BLUE)
    curses.init_pair(COLOR_ORACLE, curses.COLOR_CYAN, -1)
    curses.init_pair(COLOR_TOOL, curses.COLOR_GREEN, -1)
    curses.init_pair(COLOR_TASK, curses.COLOR_YELLOW, -1)
    curses.init_pair(COLOR_ERROR, curses.COLOR_RED, -1)
    curses.init_pair(COLOR_SUCCESS, curses.COLOR_GREEN, -1)
    curses.init_pair(COLOR_DIM, curses.COLOR_WHITE, -1)
    curses.init_pair(COLOR_HIGHLIGHT, curses.COLOR_MAGENTA, -1)
    curses.init_pair(COLOR_RUNNING, curses.COLOR_GREEN, -1)

    # Log level colors
    curses.init_pair(COLOR_LOG_DEBUG, curses.COLOR_CYAN, -1)
    curses.init_pair(COLOR_LOG_INFO, curses.COLOR_WHITE, -1)
    curses.init_pair(COLOR_LOG_WARNING, curses.COLOR_YELLOW, -1)
    curses.init_pair(COLOR_LOG_ERROR, curses.COLOR_RED, -1)
    curses.init_pair(COLOR_LOG_PANEL, curses.COLOR_WHITE, curses.COLOR_BLACK)

    return {
        "normal": COLOR_NORMAL,
        "header": COLOR_HEADER,
        "selected": COLOR_SELECTED,
        "status": COLOR_STATUS,
        "oracle": COLOR_ORACLE,
        "tool": COLOR_TOOL,
        "task": COLOR_TASK,
        "error": COLOR_ERROR,
        "success": COLOR_SUCCESS,
        "dim": COLOR_DIM,
        "highlight": COLOR_HIGHLIGHT,
        "running": COLOR_RUNNING,
        "log_debug": COLOR_LOG_DEBUG,
        "log_info": COLOR_LOG_INFO,
        "log_warning": COLOR_LOG_WARNING,
        "log_error": COLOR_LOG_ERROR,
        "log_panel": COLOR_LOG_PANEL,
    }


def get_interaction_color(interaction_type: str) -> int:
    """Get the color pair for an interaction type."""
    type_lower = interaction_type.lower()

    if "oracle" in type_lower:
        return COLOR_ORACLE
    elif "tool" in type_lower:
        return COLOR_TOOL
    elif "task" in type_lower:
        return COLOR_TASK
    elif "human" in type_lower:
        return COLOR_HIGHLIGHT
    elif "error" in type_lower:
        return COLOR_ERROR

    return COLOR_NORMAL


def get_log_level_color(level: int) -> int:
    """Get the color pair for a log level."""
    if level >= logging.ERROR:
        return COLOR_LOG_ERROR
    elif level >= logging.WARNING:
        return COLOR_LOG_WARNING
    elif level >= logging.INFO:
        return COLOR_LOG_INFO
    else:
        return COLOR_LOG_DEBUG
