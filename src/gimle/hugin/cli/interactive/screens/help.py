"""Help overlay screen for the interactive TUI."""

import curses
from typing import TYPE_CHECKING, Optional

from gimle.hugin.cli.interactive.screens.base import BaseScreen

if TYPE_CHECKING:
    from gimle.hugin.cli.interactive.app import InteractiveApp


HELP_TEXT = """
HUGIN INTERACTIVE MODE - HELP

NAVIGATION
  ↑/k         Move selection up
  ↓/j         Move selection down
  ←/→         Navigate between sessions/agents
  Enter       Select / Drill down
  Esc         Go back one screen
  g/Home      Jump to first item
  G/End       Jump to last item
  PgUp/PgDn   Page up / Page down

GLOBAL
  ?           Show this help
  q           Quit application (from sessions)
  r           Refresh current view
  l           Toggle log panel (split view)
  Ctrl+L      Open full-screen logs

LOGS (panel and viewer)
  v           Cycle log level (DEBUG/INFO/WARNING/ERROR)
  ↑/↓/j/k     Scroll logs up/down
  ←/→         Page left/right
  g/G         Jump to top/bottom
  a           Toggle auto-scroll
  f           Toggle agent filter (viewer only)

SESSIONS SCREEN (main screen)
  n           Start new agent
  d           Delete selected session

AGENTS SCREEN
  ←/→         Navigate between sessions
  c           Run/resume agent
  p           Pause selected agent
  h           Respond to agent (when awaiting input)
  d           Delete selected agent

INTERACTIONS SCREEN
  ←/→         Navigate between agents
  c           Run/resume agent
  p           Pause selected agent
  h           Respond to agent (when awaiting input)
  s           Toggle step-through mode
  n           Next step (step-through mode)
  w           Rewind to selected interaction
  a           View all artifacts

INTERACTION DETAIL
  ←/→         Previous/next interaction
  ↑/↓         Scroll content
  a           View artifact (if present)
  [/]         Select artifact (when multiple)

NEW AGENT WIZARD
  Tab         Next field
  Enter       Edit/save field
  Esc         Cancel/go back
  Backspace   Delete while editing

HUMAN INPUT (responding to agent)
  Enter       Submit response
  Esc         Cancel without responding
  Ctrl+U      Clear input
  Backspace   Delete last character

ARTIFACTS LIST
  Enter       View selected artifact
  ↑/↓         Navigate list

ARTIFACT DETAIL
  ↑/↓         Scroll content
  g/G         Jump to top/bottom

Press any key to close this help.
"""


class HelpScreen(BaseScreen):
    """Help overlay showing keyboard shortcuts."""

    def __init__(self, app: "InteractiveApp"):
        """Initialize the help screen."""
        super().__init__(app)
        self.scroll_offset = 0
        self.lines = HELP_TEXT.strip().split("\n")

    def get_title(self) -> str:
        """Return the screen title."""
        return "Help"

    def get_status_text(self) -> str:
        """Return status bar text."""
        return "Press any key to close"

    def render(self, stdscr: curses.window) -> None:
        """Render the help content."""
        height, width = stdscr.getmaxyx()

        # Draw a border/box
        start_row = 2
        end_row = height - 2
        start_col = 4
        end_col = width - 4

        visible_height = end_row - start_row

        # Draw background
        for row in range(start_row, end_row):
            try:
                stdscr.addstr(row, start_col, " " * (end_col - start_col))
            except curses.error:
                pass

        # Draw border
        try:
            # Top border
            stdscr.addstr(
                start_row - 1,
                start_col,
                "┌" + "─" * (end_col - start_col - 2) + "┐",
            )
            # Bottom border
            stdscr.addstr(
                end_row, start_col, "└" + "─" * (end_col - start_col - 2) + "┘"
            )
            # Side borders
            for row in range(start_row, end_row):
                stdscr.addstr(row, start_col, "│")
                stdscr.addstr(row, end_col - 1, "│")
        except curses.error:
            pass

        # Draw content
        content_start = start_col + 2
        content_width = end_col - start_col - 4

        for i in range(
            min(visible_height, len(self.lines) - self.scroll_offset)
        ):
            line_idx = self.scroll_offset + i
            if line_idx >= len(self.lines):
                break

            line = self.lines[line_idx]
            row = start_row + i

            # Truncate line to fit
            display_line = line[:content_width]

            try:
                stdscr.addstr(row, content_start, display_line)
            except curses.error:
                pass

    def handle_input(self, key: int) -> Optional[str]:
        """Handle keyboard input - any key closes help."""
        return "pop"
