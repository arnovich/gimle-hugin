"""Full-screen log viewer for the interactive TUI."""

import curses
from typing import TYPE_CHECKING, List, Optional

from gimle.hugin.cli.interactive.colors import (
    COLOR_HEADER,
    COLOR_STATUS,
    get_log_level_color,
)
from gimle.hugin.cli.interactive.logging import LogManager
from gimle.hugin.cli.interactive.screens.base import BaseScreen

if TYPE_CHECKING:
    from gimle.hugin.cli.interactive.app import InteractiveApp
    from gimle.hugin.cli.interactive.state import LogRecord


class LogsScreen(BaseScreen):
    """Full-screen log viewer with scrolling and filtering."""

    def __init__(self, app: "InteractiveApp"):
        """Initialize the logs screen."""
        super().__init__(app)
        self.scroll_offset = 0
        self.filter_by_agent = False
        self.auto_scroll = True
        self._last_log_count = 0

    def get_title(self) -> str:
        """Return the screen title."""
        log_manager = LogManager.get_instance()
        level_name = log_manager.current_level_name if log_manager else "INFO"
        filter_text = ""
        if self.filter_by_agent and self.state.selected_agent_id:
            agent_short = self.state.selected_agent_id[:8]
            filter_text = f" | Agent: {agent_short}..."
        return f"Logs [{level_name}]{filter_text}"

    def get_status_text(self) -> str:
        """Return status bar text."""
        auto = "ON" if self.auto_scroll else "OFF"
        filter_status = "Agent" if self.filter_by_agent else "All"
        return (
            f"Esc:Back  v:Level  f:Filter({filter_status})  "
            f"a:Auto({auto})  ↑↓:Scroll  ←→:Page  g/G:Top/Bottom"
        )

    def render(self, stdscr: curses.window) -> None:
        """Render the logs screen."""
        height, width = stdscr.getmaxyx()

        # Render header
        self._render_header(stdscr, width)

        # Render status bar
        self._render_status_bar(stdscr, height, width)

        # Content area
        start_row = 1
        end_row = height - 1
        visible_height = end_row - start_row

        # Get logs
        logs = self._get_logs(visible_height * 3)  # Get extra for scrolling

        # Auto-scroll: reset offset when new logs arrive
        if self.auto_scroll:
            new_count = len(logs)
            if new_count != self._last_log_count:
                self.scroll_offset = max(0, len(logs) - visible_height)
                self._last_log_count = new_count

        # Ensure scroll offset is valid
        max_offset = max(0, len(logs) - visible_height)
        self.scroll_offset = min(self.scroll_offset, max_offset)

        if not logs:
            try:
                msg = "(no logs at current level)"
                stdscr.addstr(start_row + 1, 2, msg)
            except curses.error:
                pass
            return

        # Render visible logs
        visible_logs = logs[
            self.scroll_offset : self.scroll_offset + visible_height
        ]

        for i, log in enumerate(visible_logs):
            row = start_row + i
            self._render_log_line(stdscr, row, width, log)

        # Render scrollbar if needed
        if len(logs) > visible_height:
            self._render_scrollbar(stdscr, start_row, end_row, width - 1, logs)

    def _render_header(self, stdscr: curses.window, width: int) -> None:
        """Render the header bar."""
        title = self.get_title()
        header_text = f" HUGIN | {title} "
        header_text = header_text.ljust(width - 1)

        try:
            stdscr.addstr(
                0, 0, header_text[: width - 1], curses.color_pair(COLOR_HEADER)
            )
        except curses.error:
            pass

    def _render_status_bar(
        self, stdscr: curses.window, height: int, width: int
    ) -> None:
        """Render the status bar."""
        status_text = f" {self.get_status_text()} "
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

    def _render_log_line(
        self, stdscr: curses.window, row: int, width: int, log: "LogRecord"
    ) -> None:
        """Render a single log line."""
        # Format: YYYY-MM-DD HH:MM:SS [LEVEL] (agent) logger - message
        time_str = log.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        level_str = f"[{log.level_name:5s}]"

        agent_str = ""
        if log.agent_id:
            agent_str = f"({log.agent_id[:8]}) "

        logger_short = log.logger_name.split(".")[-1] if log.logger_name else ""
        if logger_short:
            logger_short = f"{logger_short}: "

        prefix = f"{time_str} {level_str} {agent_str}{logger_short}"
        message = log.message

        # Truncate to fit
        max_msg_len = width - len(prefix) - 1
        if len(message) > max_msg_len:
            message = message[: max_msg_len - 3] + "..."

        line = f"{prefix}{message}"
        line = line[: width - 1]

        color = get_log_level_color(log.level)
        try:
            stdscr.addstr(row, 0, line, curses.color_pair(color))
        except curses.error:
            pass

    def _render_scrollbar(
        self,
        stdscr: curses.window,
        start_row: int,
        end_row: int,
        col: int,
        logs: List["LogRecord"],
    ) -> None:
        """Render the scrollbar."""
        visible_height = end_row - start_row
        total = len(logs)

        if total <= visible_height:
            return

        # Calculate thumb position and size
        thumb_size = max(1, visible_height * visible_height // total)
        thumb_pos = (
            self.scroll_offset
            * (visible_height - thumb_size)
            // (total - visible_height)
        )

        for i in range(visible_height):
            row = start_row + i
            if thumb_pos <= i < thumb_pos + thumb_size:
                char = "█"
            else:
                char = "│"
            try:
                stdscr.addstr(row, col, char, curses.A_DIM)
            except curses.error:
                pass

    def _get_logs(self, limit: int) -> List["LogRecord"]:
        """Get logs from the manager."""
        log_manager = LogManager.get_instance()
        if not log_manager:
            return []

        agent_id = None
        if self.filter_by_agent:
            agent_id = self.state.selected_agent_id

        return log_manager.get_logs(
            agent_id=agent_id,
            limit=limit,
            min_level=self.state.log_state.current_level,
        )

    def handle_input(self, key: int) -> Optional[str]:
        """Handle keyboard input."""
        log_manager = LogManager.get_instance()
        height, _ = self.app.get_size()
        visible_height = height - 2  # Minus header and status

        if key == 27:  # Escape
            return "pop"

        elif key == curses.KEY_DOWN:
            # Scroll down
            self.scroll_offset += 1
            self.auto_scroll = False
            return "refresh"

        elif key == curses.KEY_UP:
            # Scroll up
            self.scroll_offset = max(0, self.scroll_offset - 1)
            self.auto_scroll = False
            return "refresh"

        elif key == curses.KEY_LEFT:
            # Page up
            self.scroll_offset = max(0, self.scroll_offset - visible_height)
            self.auto_scroll = False
            return "refresh"

        elif key == curses.KEY_RIGHT:
            # Page down
            self.scroll_offset += visible_height
            self.auto_scroll = False
            return "refresh"

        elif key in (ord("g"), curses.KEY_HOME):
            # Jump to top
            self.scroll_offset = 0
            self.auto_scroll = False
            return "refresh"

        elif key in (ord("G"), curses.KEY_END):
            # Jump to bottom
            logs = self._get_logs(visible_height * 3)
            self.scroll_offset = max(0, len(logs) - visible_height)
            self.auto_scroll = True
            return "refresh"

        elif key in (ord("a"), ord("A")):
            # Toggle auto-scroll
            self.auto_scroll = not self.auto_scroll
            return "refresh"

        elif key in (ord("f"), ord("F")):
            # Toggle agent filter
            self.filter_by_agent = not self.filter_by_agent
            self.scroll_offset = 0
            return "refresh"

        elif key in (ord("v"), ord("V")):
            # Cycle log level
            if log_manager:
                log_manager.cycle_level()
                self.state.log_state.current_level = log_manager.current_level
                self.scroll_offset = 0
            return "refresh"

        return None
