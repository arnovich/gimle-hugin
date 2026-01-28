"""Scrollable detail view widget for the interactive TUI."""

import curses
from typing import Any, Dict, List, Optional


class DetailView:
    """A scrollable detail view for showing interaction details."""

    def __init__(self) -> None:
        """Initialize the detail view."""
        self.lines: List[tuple] = []  # List of (text, attr) tuples
        self.scroll_offset = 0

    def set_content(self, data: Dict[str, Any]) -> None:
        """Set the content from a dictionary."""
        self.lines = []
        self.scroll_offset = 0
        self._format_dict(data, indent=0)

    def _format_dict(self, data: Dict[str, Any], indent: int = 0) -> None:
        """Format a dictionary into display lines."""
        prefix = "  " * indent

        for key, value in data.items():
            if (
                key in ("id", "uuid")
                and isinstance(value, str)
                and len(value) > 8
            ):
                # Truncate long IDs
                value = value[:8] + "..."

            if isinstance(value, dict):
                self.lines.append((f"{prefix}{key}:", curses.A_BOLD))
                self._format_dict(value, indent + 1)
            elif isinstance(value, list):
                self.lines.append(
                    (f"{prefix}{key}: [{len(value)} items]", curses.A_BOLD)
                )
                if value and len(value) <= 5:
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            self.lines.append(
                                (f"{prefix}  [{i}]:", curses.A_NORMAL)
                            )
                            self._format_dict(item, indent + 2)
                        else:
                            item_str = str(item)
                            if len(item_str) > 60:
                                item_str = item_str[:60] + "..."
                            self.lines.append(
                                (
                                    f"{prefix}  [{i}]: {item_str}",
                                    curses.A_NORMAL,
                                )
                            )
            elif isinstance(value, str):
                # Handle multiline strings
                if "\n" in value or len(value) > 60:
                    self.lines.append((f"{prefix}{key}:", curses.A_BOLD))
                    for line in value.split("\n"):
                        if len(line) > 70:
                            # Word wrap
                            while line:
                                self.lines.append(
                                    (f"{prefix}  {line[:70]}", curses.A_NORMAL)
                                )
                                line = line[70:]
                        else:
                            self.lines.append(
                                (f"{prefix}  {line}", curses.A_NORMAL)
                            )
                else:
                    self.lines.append(
                        (f"{prefix}{key}: {value}", curses.A_NORMAL)
                    )
            elif value is None:
                self.lines.append((f"{prefix}{key}: null", curses.A_DIM))
            elif isinstance(value, bool):
                self.lines.append(
                    (f"{prefix}{key}: {str(value).lower()}", curses.A_NORMAL)
                )
            else:
                self.lines.append((f"{prefix}{key}: {value}", curses.A_NORMAL))

    def set_text(self, text: str) -> None:
        """Set content from plain text."""
        self.lines = []
        self.scroll_offset = 0
        for line in text.split("\n"):
            self.lines.append((line, curses.A_NORMAL))

    def render(
        self,
        stdscr: curses.window,
        start_row: int,
        end_row: int,
        start_col: int,
        end_col: int,
    ) -> None:
        """Render the detail view within the given bounds."""
        visible_height = end_row - start_row
        width = end_col - start_col

        if not self.lines:
            try:
                stdscr.addstr(start_row, start_col, "(no content)")
            except curses.error:
                pass
            return

        # Adjust scroll
        self._adjust_scroll(visible_height)

        for i in range(visible_height):
            line_idx = self.scroll_offset + i
            if line_idx >= len(self.lines):
                break

            text, attr = self.lines[line_idx]
            row = start_row + i

            # Truncate to width
            display_text = text[: width - 2]

            try:
                stdscr.addstr(row, start_col, display_text, attr)
            except curses.error:
                pass

        # Draw scrollbar if needed
        if len(self.lines) > visible_height:
            self._render_scrollbar(stdscr, start_row, end_row, end_col - 1)

    def _render_scrollbar(
        self, stdscr: curses.window, start_row: int, end_row: int, col: int
    ) -> None:
        """Render a simple scrollbar."""
        visible_height = end_row - start_row
        total = len(self.lines)

        if total <= visible_height:
            return

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

    def _adjust_scroll(self, visible_height: int) -> None:
        """Adjust scroll to stay within bounds."""
        max_scroll = max(0, len(self.lines) - visible_height)
        self.scroll_offset = min(self.scroll_offset, max_scroll)

    def handle_input(self, key: int, visible_height: int = 20) -> Optional[str]:
        """Handle keyboard input for scrolling."""
        if key == curses.KEY_UP or key == ord("k"):
            self.scroll_up()
        elif key == curses.KEY_DOWN or key == ord("j"):
            self.scroll_down()
        elif key == curses.KEY_PPAGE:
            self.scroll_offset = max(0, self.scroll_offset - visible_height)
        elif key == curses.KEY_NPAGE:
            self.scroll_offset += visible_height
            self._adjust_scroll(visible_height)
        elif key == curses.KEY_HOME or key == ord("g"):
            self.scroll_offset = 0
        elif key == ord("G") or key == curses.KEY_END:
            self.scroll_offset = max(0, len(self.lines) - visible_height)

        return None

    def scroll_up(self) -> None:
        """Scroll up one line."""
        if self.scroll_offset > 0:
            self.scroll_offset -= 1

    def scroll_down(self) -> None:
        """Scroll down one line."""
        self.scroll_offset += 1
