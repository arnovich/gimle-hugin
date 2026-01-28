"""Log panel widget for the interactive TUI."""

import curses
from typing import TYPE_CHECKING, List, Optional

from gimle.hugin.cli.interactive.colors import (
    COLOR_LOG_PANEL,
    get_log_level_color,
)
from gimle.hugin.cli.interactive.logging import LogManager

if TYPE_CHECKING:
    from gimle.hugin.cli.interactive.state import LogRecord, LogState


class LogPanel:
    """A split panel widget for displaying logs."""

    def __init__(self, log_state: "LogState"):
        """Initialize the log panel.

        Args:
            log_state: Reference to the shared log state.
        """
        self.log_state = log_state
        self._last_log_count = 0

    def render(
        self,
        stdscr: curses.window,
        start_row: int,
        end_row: int,
        start_col: int,
        end_col: int,
        agent_id: Optional[str] = None,
    ) -> None:
        """Render the log panel.

        Args:
            stdscr: The curses window.
            start_row: Top row of the panel area.
            end_row: Bottom row of the panel area (exclusive).
            start_col: Left column.
            end_col: Right column (exclusive).
            agent_id: Optional agent ID to filter logs by.
        """
        height = end_row - start_row
        width = end_col - start_col

        if height < 2 or width < 20:
            return

        # Draw panel border/header
        log_manager = LogManager.get_instance()
        if not log_manager:
            return

        level_name = log_manager.current_level_name
        header = f" Logs [{level_name}] "
        if agent_id:
            header = f" Logs [{level_name}] (agent: {agent_id[:8]}...) "

        # Draw top border with header
        border = "─" * (width - 2)
        header_line = "┌" + header + border[len(header) :] + "┐"
        header_line = header_line[: width - 1]

        try:
            stdscr.addstr(
                start_row,
                start_col,
                header_line,
                curses.color_pair(COLOR_LOG_PANEL),
            )
        except curses.error:
            pass

        # Get logs to display
        log_height = height - 2  # Subtract header and bottom border
        logs = self._get_logs(
            log_height * 2, agent_id
        )  # Get extra for scrolling

        # Auto-scroll: reset offset when new logs arrive
        if self.log_state.auto_scroll:
            new_count = len(logs)
            if new_count != self._last_log_count:
                # New logs arrived, scroll to bottom
                self.log_state.scroll_offset = max(0, len(logs) - log_height)
                self._last_log_count = new_count

        # Calculate visible range
        offset = self.log_state.scroll_offset
        visible_logs = logs[offset : offset + log_height]

        # Render log lines
        for i, log in enumerate(visible_logs):
            row = start_row + 1 + i
            if row >= end_row - 1:
                break

            # Format: HH:MM:SS [LEVEL] message
            time_str = log.timestamp.strftime("%H:%M:%S")
            level_short = log.level_name[:4]
            msg = log.message

            # Truncate message to fit
            prefix = f"│{time_str} [{level_short}] "
            max_msg_len = (
                width - len(prefix) - 2
            )  # -2 for right border + margin
            if len(msg) > max_msg_len:
                msg = msg[: max_msg_len - 3] + "..."

            line = f"{prefix}{msg}"
            line = line.ljust(width - 2) + "│"
            line = line[: width - 1]

            color = get_log_level_color(log.level)
            try:
                stdscr.addstr(row, start_col, line, curses.color_pair(color))
            except curses.error:
                pass

        # Fill empty rows
        for i in range(len(visible_logs), log_height):
            row = start_row + 1 + i
            if row >= end_row - 1:
                break
            empty_line = "│" + " " * (width - 3) + "│"
            empty_line = empty_line[: width - 1]
            try:
                stdscr.addstr(
                    row,
                    start_col,
                    empty_line,
                    curses.color_pair(COLOR_LOG_PANEL),
                )
            except curses.error:
                pass

        # Draw bottom border with hints
        auto_indicator = "A" if self.log_state.auto_scroll else " "
        hints = (
            f" v:Level  j/k:Scroll  a:Auto[{auto_indicator}]  ^L:Full  l:Hide "
        )
        bottom = "└" + hints + "─" * (width - len(hints) - 2) + "┘"
        bottom = bottom[: width - 1]

        try:
            stdscr.addstr(
                end_row - 1,
                start_col,
                bottom,
                curses.color_pair(COLOR_LOG_PANEL),
            )
        except curses.error:
            pass

    def _get_logs(
        self, limit: int, agent_id: Optional[str] = None
    ) -> List["LogRecord"]:
        """Get logs from the manager."""
        log_manager = LogManager.get_instance()
        if not log_manager:
            return []

        return log_manager.get_logs(
            agent_id=agent_id,
            limit=limit,
            min_level=self.log_state.current_level,
        )

    def handle_input(self, key: int, visible_height: int = 6) -> Optional[str]:
        """Handle keyboard input for the log panel.

        Args:
            key: The key code pressed.
            visible_height: Height of visible log area.

        Returns:
            None - input not handled
            "refresh" - screen needs refresh
            "level_changed" - log level was changed
        """
        log_manager = LogManager.get_instance()

        if key in (ord("j"), ord("J"), curses.KEY_DOWN):
            # Scroll down
            self.log_state.scroll_offset += 1
            self.log_state.auto_scroll = False
            return "refresh"

        elif key in (ord("k"), ord("K"), curses.KEY_UP):
            # Scroll up
            self.log_state.scroll_offset = max(
                0, self.log_state.scroll_offset - 1
            )
            self.log_state.auto_scroll = False
            return "refresh"

        elif key in (ord("g"),):
            # Jump to top
            self.log_state.scroll_offset = 0
            self.log_state.auto_scroll = False
            return "refresh"

        elif key in (ord("G"),):
            # Jump to bottom (enable auto-scroll)
            self.log_state.auto_scroll = True
            return "refresh"

        elif key in (ord("a"), ord("A")):
            # Toggle auto-scroll
            self.log_state.auto_scroll = not self.log_state.auto_scroll
            return "refresh"

        elif key in (ord("v"), ord("V")):
            # Cycle log level
            if log_manager:
                log_manager.cycle_level()
                self.log_state.current_level = log_manager.current_level
            return "level_changed"

        return None

    def scroll_to_bottom(self) -> None:
        """Scroll to the bottom of the logs."""
        self.log_state.auto_scroll = True
