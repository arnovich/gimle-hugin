"""Base screen class for the interactive TUI."""

import curses
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from gimle.hugin.cli.interactive.colors import COLOR_HEADER, COLOR_STATUS
from gimle.hugin.cli.interactive.widgets.log_panel import LogPanel

if TYPE_CHECKING:
    from gimle.hugin.cli.interactive.app import InteractiveApp
    from gimle.hugin.cli.interactive.state import AppState


class BaseScreen(ABC):
    """Abstract base class for all TUI screens."""

    def __init__(self, app: "InteractiveApp"):
        """Initialize base screen with app reference."""
        self.app = app
        self._log_panel: Optional[LogPanel] = None

    @property
    def state(self) -> "AppState":
        """Return shortcut to app state."""
        return self.app.state

    @property
    def log_panel(self) -> LogPanel:
        """Get or create the log panel widget."""
        if self._log_panel is None:
            self._log_panel = LogPanel(self.state.log_state)
        return self._log_panel

    @abstractmethod
    def render(self, stdscr: curses.window) -> None:
        """Render the screen content."""
        pass

    @abstractmethod
    def handle_input(self, key: int) -> Optional[str]:
        """
        Handle keyboard input.

        Returns:
            None - input handled, no action needed
            "pop" - pop this screen
            "refresh" - request screen refresh
        """
        pass

    @abstractmethod
    def get_title(self) -> str:
        """Get the screen title for the header."""
        pass

    def get_status_text(self) -> str:
        """Get the status bar text."""
        return "Esc:Back  ?:Help  r:Refresh"

    def is_capturing_input(self) -> bool:
        """Return True if screen is capturing text input.

        When True, global keyboard shortcuts are disabled to allow
        typing text. Only ESC will work to exit input mode.
        """
        return False

    def render_header(self, stdscr: curses.window, title: str) -> int:
        """Render the header bar. Returns the next available row."""
        height, width = stdscr.getmaxyx()

        # Header line
        header_text = f" HUGIN | {title} "
        header_text = header_text.ljust(width - 1)

        try:
            stdscr.addstr(
                0, 0, header_text[: width - 1], curses.color_pair(COLOR_HEADER)
            )
        except curses.error:
            pass

        return 1

    def render_status_bar(self, stdscr: curses.window, text: str) -> None:
        """Render the status bar at the bottom."""
        height, width = stdscr.getmaxyx()

        status_text = f" {text} "
        status_text = status_text.ljust(width - 1)

        try:
            stdscr.addstr(
                height - 1,
                0,
                status_text[: width - 1],
                curses.color_pair(COLOR_STATUS),
            )
        except curses.error:
            pass

    def render_frame(self, stdscr: curses.window) -> tuple:
        """
        Render header and status bar, return content area bounds.

        Also renders the log panel at the bottom if visible.

        Returns:
            (start_row, end_row, start_col, end_col)
        """
        height, width = stdscr.getmaxyx()

        start_row = self.render_header(stdscr, self.get_title())
        self.render_status_bar(stdscr, self.get_status_text())

        # Calculate content area end row
        content_end_row = height - 1

        # Reserve space for log panel if visible
        if self.state.log_state.panel_visible:
            panel_height = self.state.log_state.panel_height
            # Ensure panel doesn't take too much space
            min_content = 5  # Minimum content rows
            available = height - start_row - 1 - min_content
            panel_height = min(panel_height, max(4, available))

            # Render the log panel
            panel_start = height - 1 - panel_height
            self.render_log_panel(stdscr, panel_start, height - 1, 0, width)

            # Adjust content area
            content_end_row = panel_start

        return (start_row, content_end_row, 0, width)

    def render_log_panel(
        self,
        stdscr: curses.window,
        start_row: int,
        end_row: int,
        start_col: int,
        end_col: int,
    ) -> None:
        """Render the log panel at the bottom of the screen."""
        # Get current agent_id if we're viewing an agent
        agent_id = self.state.selected_agent_id
        self.log_panel.render(
            stdscr, start_row, end_row, start_col, end_col, agent_id=agent_id
        )

    def handle_log_panel_input(self, key: int) -> Optional[str]:
        """Handle input for the log panel.

        Returns:
            "refresh" if panel handled the input and needs refresh,
            None if input was not handled.
        """
        if not self.state.log_state.panel_visible:
            return None

        result = self.log_panel.handle_input(key)
        if result in ("refresh", "level_changed"):
            return "refresh"
        return None
