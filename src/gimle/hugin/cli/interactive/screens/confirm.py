"""Confirmation dialog screen for the interactive TUI."""

import curses
from typing import TYPE_CHECKING, Callable, Optional

from gimle.hugin.cli.interactive.colors import COLOR_ERROR, COLOR_SELECTED
from gimle.hugin.cli.interactive.screens.base import BaseScreen

if TYPE_CHECKING:
    from gimle.hugin.cli.interactive.app import InteractiveApp


class ConfirmScreen(BaseScreen):
    """A confirmation dialog screen."""

    def __init__(
        self,
        app: "InteractiveApp",
        title: str,
        message: str,
        on_confirm: Callable[[], bool],
        confirm_text: str = "Delete",
        cancel_text: str = "Cancel",
    ):
        """Initialize the confirmation screen.

        Args:
            app: The interactive app instance
            title: Dialog title
            message: Message to display
            on_confirm: Callback to execute on confirmation, returns success
            confirm_text: Text for the confirm button
            cancel_text: Text for the cancel button
        """
        super().__init__(app)
        self.title = title
        self.message = message
        self.on_confirm = on_confirm
        self.confirm_text = confirm_text
        self.cancel_text = cancel_text
        self.selected_confirm = False  # Start with cancel selected

    def get_title(self) -> str:
        """Return the screen title."""
        return self.title

    def get_status_text(self) -> str:
        """Return status bar text."""
        return "←/→:Select  Enter:Confirm  Esc:Cancel  y:Yes  n:No"

    def render(self, stdscr: curses.window) -> None:
        """Render the confirmation dialog."""
        start_row, end_row, start_col, end_col = self.render_frame(stdscr)
        height, width = stdscr.getmaxyx()

        content_height = end_row - start_row
        content_width = end_col - start_col

        # Calculate dialog box dimensions
        box_width = min(60, content_width - 4)
        message_lines = self._wrap_text(self.message, box_width - 4)
        box_height = len(message_lines) + 6  # padding + buttons

        # Center the dialog
        box_top = start_row + (content_height - box_height) // 2
        box_left = start_col + (content_width - box_width) // 2

        # Draw the dialog box
        self._draw_box(stdscr, box_top, box_left, box_height, box_width)

        # Draw message
        for i, line in enumerate(message_lines):
            try:
                stdscr.addstr(
                    box_top + 2 + i, box_left + 2, line[: box_width - 4]
                )
            except curses.error:
                pass

        # Draw buttons
        button_row = box_top + box_height - 3
        cancel_text = f" {self.cancel_text} "
        confirm_text = f" {self.confirm_text} "
        total_button_width = len(cancel_text) + len(confirm_text) + 4
        button_start = box_left + (box_width - total_button_width) // 2

        # Cancel button
        cancel_attr = (
            curses.color_pair(COLOR_SELECTED) | curses.A_BOLD
            if not self.selected_confirm
            else 0
        )
        try:
            stdscr.addstr(button_row, button_start, cancel_text, cancel_attr)
        except curses.error:
            pass

        # Confirm button
        confirm_attr = (
            curses.color_pair(COLOR_ERROR) | curses.A_BOLD
            if self.selected_confirm
            else curses.color_pair(COLOR_ERROR)
        )
        try:
            stdscr.addstr(
                button_row,
                button_start + len(cancel_text) + 4,
                confirm_text,
                confirm_attr,
            )
        except curses.error:
            pass

    def _wrap_text(self, text: str, width: int) -> list:
        """Wrap text to fit within width."""
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            if len(current_line) + len(word) + 1 <= width:
                if current_line:
                    current_line += " " + word
                else:
                    current_line = word
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines if lines else [""]

    def _draw_box(
        self,
        stdscr: curses.window,
        top: int,
        left: int,
        height: int,
        width: int,
    ) -> None:
        """Draw a box border."""
        # Draw corners
        try:
            stdscr.addch(top, left, curses.ACS_ULCORNER)
            stdscr.addch(top, left + width - 1, curses.ACS_URCORNER)
            stdscr.addch(top + height - 1, left, curses.ACS_LLCORNER)
            stdscr.addch(
                top + height - 1, left + width - 1, curses.ACS_LRCORNER
            )
        except curses.error:
            pass

        # Draw horizontal lines
        for x in range(left + 1, left + width - 1):
            try:
                stdscr.addch(top, x, curses.ACS_HLINE)
                stdscr.addch(top + height - 1, x, curses.ACS_HLINE)
            except curses.error:
                pass

        # Draw vertical lines
        for y in range(top + 1, top + height - 1):
            try:
                stdscr.addch(y, left, curses.ACS_VLINE)
                stdscr.addch(y, left + width - 1, curses.ACS_VLINE)
            except curses.error:
                pass

        # Clear interior
        for y in range(top + 1, top + height - 1):
            try:
                stdscr.addstr(y, left + 1, " " * (width - 2))
            except curses.error:
                pass

    def handle_input(self, key: int) -> Optional[str]:
        """Handle keyboard input."""
        if key in (curses.KEY_LEFT, ord("h"), ord("H")):
            self.selected_confirm = False
            return "refresh"
        elif key in (curses.KEY_RIGHT, ord("l"), ord("L")):
            self.selected_confirm = True
            return "refresh"
        elif key in (ord("\n"), ord("\r"), curses.KEY_ENTER):
            if self.selected_confirm:
                self.on_confirm()
            return "pop"
        elif key in (ord("q"), ord("Q"), 27):  # q or Escape
            return "pop"
        elif key in (ord("y"), ord("Y")):
            # Quick confirm with 'y'
            self.on_confirm()
            return "pop"
        elif key in (ord("n"), ord("N")):
            # Quick cancel with 'n'
            return "pop"

        return None
