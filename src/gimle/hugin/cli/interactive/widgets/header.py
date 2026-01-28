"""Header widget for the interactive TUI."""

import curses

from gimle.hugin.cli.interactive.colors import COLOR_HEADER


class Header:
    """A header bar widget for the top of the screen."""

    def __init__(self, title: str = "HUGIN"):
        """Initialize the header widget."""
        self.title = title
        self.subtitle = ""

    def set_title(self, title: str) -> None:
        """Set the header title."""
        self.title = title

    def set_subtitle(self, subtitle: str) -> None:
        """Set the header subtitle."""
        self.subtitle = subtitle

    def render(self, stdscr: curses.window, row: int, width: int) -> None:
        """Render the header at the given row."""
        if self.subtitle:
            display_text = f" HUGIN | {self.title} | {self.subtitle} "
        else:
            display_text = f" HUGIN | {self.title} "

        display_text = display_text.ljust(width - 1)

        try:
            stdscr.addstr(
                row,
                0,
                display_text[: width - 1],
                curses.color_pair(COLOR_HEADER),
            )
        except curses.error:
            pass
