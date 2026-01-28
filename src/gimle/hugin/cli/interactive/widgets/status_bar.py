"""Status bar widget for the interactive TUI."""

import curses

from gimle.hugin.cli.interactive.colors import COLOR_STATUS


class StatusBar:
    """A status bar widget for the bottom of the screen."""

    def __init__(self, text: str = ""):
        """Initialize the status bar widget."""
        self.text = text

    def set_text(self, text: str) -> None:
        """Set the status bar text."""
        self.text = text

    def render(self, stdscr: curses.window, row: int, width: int) -> None:
        """Render the status bar at the given row."""
        display_text = f" {self.text} ".ljust(width - 1)

        try:
            stdscr.addstr(
                row,
                0,
                display_text[: width - 1],
                curses.color_pair(COLOR_STATUS),
            )
        except curses.error:
            pass
