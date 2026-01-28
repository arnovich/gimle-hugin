"""Human input screen for responding to agent questions."""

import curses
from typing import TYPE_CHECKING, Callable, Optional

from gimle.hugin.cli.interactive.colors import COLOR_SELECTED
from gimle.hugin.cli.interactive.screens.base import BaseScreen

if TYPE_CHECKING:
    from gimle.hugin.cli.interactive.app import InteractiveApp


class HumanInputScreen(BaseScreen):
    """A screen for entering human response to an agent question."""

    def __init__(
        self,
        app: "InteractiveApp",
        question: str,
        on_submit: Callable[[str], bool],
    ):
        """Initialize the human input screen.

        Args:
            app: The interactive app instance
            question: The question from the agent
            on_submit: Callback to execute on submission, returns success
        """
        super().__init__(app)
        self.question = question
        self.on_submit = on_submit
        self.input_text = ""
        self.cursor_pos = 0

    def get_title(self) -> str:
        """Return the screen title."""
        return "Respond to Agent"

    def get_status_text(self) -> str:
        """Return status bar text."""
        return "Enter:Submit  Esc:Cancel  Ctrl+U:Clear"

    def render(self, stdscr: curses.window) -> None:
        """Render the input dialog."""
        start_row, end_row, start_col, end_col = self.render_frame(stdscr)
        height, width = stdscr.getmaxyx()

        content_height = end_row - start_row
        content_width = end_col - start_col

        # Calculate dialog box dimensions
        box_width = min(70, content_width - 4)
        question_lines = self._wrap_text(self.question, box_width - 4)
        # Height: question lines + input area (3 lines) + padding
        box_height = len(question_lines) + 8

        # Center the dialog
        box_top = start_row + (content_height - box_height) // 2
        box_left = start_col + (content_width - box_width) // 2

        # Draw the dialog box
        self._draw_box(stdscr, box_top, box_left, box_height, box_width)

        # Draw question label
        try:
            stdscr.addstr(
                box_top + 1,
                box_left + 2,
                "Agent Question:",
                curses.A_BOLD,
            )
        except curses.error:
            pass

        # Draw question text
        for i, line in enumerate(question_lines):
            try:
                stdscr.addstr(
                    box_top + 2 + i, box_left + 2, line[: box_width - 4]
                )
            except curses.error:
                pass

        # Draw input area
        input_row = box_top + len(question_lines) + 4
        try:
            stdscr.addstr(
                input_row - 1,
                box_left + 2,
                "Your Response:",
                curses.A_BOLD,
            )
        except curses.error:
            pass

        # Draw input box (3 lines for multi-line input)
        input_width = box_width - 6
        for row_offset in range(3):
            try:
                stdscr.addstr(
                    input_row + row_offset,
                    box_left + 3,
                    " " * input_width,
                    curses.color_pair(COLOR_SELECTED),
                )
            except curses.error:
                pass

        # Draw input text with wrapping
        input_lines = self._wrap_input_text(self.input_text, input_width)
        for i, line in enumerate(input_lines[:3]):
            try:
                stdscr.addstr(
                    input_row + i,
                    box_left + 3,
                    line[:input_width],
                    curses.color_pair(COLOR_SELECTED),
                )
            except curses.error:
                pass

        # Draw cursor
        if len(input_lines) <= 3:
            cursor_line = len(input_lines) - 1 if input_lines else 0
            cursor_col = len(input_lines[-1]) if input_lines else 0
            try:
                stdscr.addstr(
                    input_row + cursor_line,
                    box_left + 3 + cursor_col,
                    "_",
                    curses.color_pair(COLOR_SELECTED) | curses.A_BLINK,
                )
            except curses.error:
                pass

        # Draw submit hint
        try:
            stdscr.addstr(
                box_top + box_height - 2,
                box_left + 2,
                "Press Enter to submit, Esc to cancel",
                curses.A_DIM,
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

    def _wrap_input_text(self, text: str, width: int) -> list:
        """Wrap input text, preserving character positions."""
        if not text:
            return [""]

        lines = []
        current_line = ""

        for char in text:
            if char == "\n":
                lines.append(current_line)
                current_line = ""
            elif len(current_line) >= width:
                lines.append(current_line)
                current_line = char
            else:
                current_line += char

        lines.append(current_line)
        return lines

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
        if key in (ord("\n"), ord("\r"), curses.KEY_ENTER):
            # Submit the response
            if self.input_text.strip():
                self.on_submit(self.input_text)
            return "pop"
        elif key in (27,):  # Escape
            return "pop"
        elif key == 21:  # Ctrl+U - clear input
            self.input_text = ""
            return "refresh"
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            # Backspace
            if self.input_text:
                self.input_text = self.input_text[:-1]
            return "refresh"
        elif key == curses.KEY_DC:
            # Delete key (same as backspace for now)
            if self.input_text:
                self.input_text = self.input_text[:-1]
            return "refresh"
        elif 32 <= key <= 126:
            # Printable ASCII characters
            self.input_text += chr(key)
            return "refresh"

        return None
