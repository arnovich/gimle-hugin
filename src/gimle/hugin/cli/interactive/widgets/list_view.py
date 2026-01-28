"""Scrollable list widget for the interactive TUI."""

import curses
from dataclasses import dataclass
from typing import Callable, Generic, List, Optional, TypeVar

from gimle.hugin.cli.interactive.colors import COLOR_SELECTED

T = TypeVar("T")


@dataclass
class ListItem(Generic[T]):
    """A single item in a list view."""

    data: T
    label: str
    secondary: str = ""
    color: int = 0
    prefix: str = ""


class ListView(Generic[T]):
    """A scrollable list view widget."""

    def __init__(
        self,
        items: List[ListItem[T]],
        on_select: Optional[Callable[[T], None]] = None,
    ):
        """Initialize the list view widget."""
        self.items = items
        self.on_select = on_select
        self.selected_idx = 0
        self.scroll_offset = 0

    def set_items(self, items: List[ListItem[T]]) -> None:
        """Update the list items."""
        self.items = items
        if self.selected_idx >= len(items):
            self.selected_idx = max(0, len(items) - 1)
        self._adjust_scroll()

    def render(
        self,
        stdscr: curses.window,
        start_row: int,
        end_row: int,
        start_col: int,
        end_col: int,
    ) -> None:
        """Render the list within the given bounds."""
        visible_height = end_row - start_row
        width = end_col - start_col

        if not self.items:
            try:
                stdscr.addstr(start_row, start_col, "(empty)")
            except curses.error:
                pass
            return

        # Calculate visible items
        self._adjust_scroll_for_height(visible_height)

        for i in range(visible_height):
            item_idx = self.scroll_offset + i
            if item_idx >= len(self.items):
                break

            item = self.items[item_idx]
            row = start_row + i

            # Build display line
            prefix = item.prefix + " " if item.prefix else ""
            label = item.label
            secondary = f" ({item.secondary})" if item.secondary else ""

            line = f"{prefix}{label}{secondary}"
            line = line[: width - 1].ljust(width - 1)

            # Determine attributes
            is_selected = item_idx == self.selected_idx
            if is_selected:
                attr = curses.color_pair(COLOR_SELECTED)
            elif item.color:
                attr = curses.color_pair(item.color)
            else:
                attr = curses.A_NORMAL

            try:
                stdscr.addstr(row, start_col, line, attr)
            except curses.error:
                pass

        # Draw scrollbar if needed
        if len(self.items) > visible_height:
            self._render_scrollbar(stdscr, start_row, end_row, end_col - 1)

    def _render_scrollbar(
        self, stdscr: curses.window, start_row: int, end_row: int, col: int
    ) -> None:
        """Render a simple scrollbar."""
        visible_height = end_row - start_row
        total = len(self.items)

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

    def _adjust_scroll(self) -> None:
        """Adjust scroll to keep selection visible."""
        # This is called when items change
        if self.selected_idx < self.scroll_offset:
            self.scroll_offset = self.selected_idx

    def _adjust_scroll_for_height(self, visible_height: int) -> None:
        """Adjust scroll to keep selection visible given viewport height."""
        if self.selected_idx < self.scroll_offset:
            self.scroll_offset = self.selected_idx
        elif self.selected_idx >= self.scroll_offset + visible_height:
            self.scroll_offset = self.selected_idx - visible_height + 1

    def handle_input(self, key: int, visible_height: int = 20) -> Optional[str]:
        """
        Handle keyboard input for list navigation.

        Returns:
            None - input not handled
            "navigate" - navigation happened (up/down/page)
            "select" - item was selected (Enter pressed)
            "prev" - left arrow pressed (for horizontal navigation)
            "next" - right arrow pressed (for horizontal navigation)
        """
        if not self.items:
            return None

        if key in (curses.KEY_UP, ord("k"), ord("K")):
            self.move_up()
            self._adjust_scroll_for_height(visible_height)
            return "navigate"
        elif key in (curses.KEY_DOWN, ord("j"), ord("J")):
            self.move_down()
            self._adjust_scroll_for_height(visible_height)
            return "navigate"
        elif key == curses.KEY_LEFT:
            return "prev"
        elif key == curses.KEY_RIGHT:
            return "next"
        elif key in (curses.KEY_HOME, ord("g")):
            self.selected_idx = 0
            self._adjust_scroll_for_height(visible_height)
            return "navigate"
        elif key in (curses.KEY_END, ord("G")):
            self.selected_idx = len(self.items) - 1
            self._adjust_scroll_for_height(visible_height)
            return "navigate"
        elif key == curses.KEY_PPAGE:  # Page Up
            self.selected_idx = max(0, self.selected_idx - visible_height)
            self._adjust_scroll_for_height(visible_height)
            return "navigate"
        elif key == curses.KEY_NPAGE:  # Page Down
            self.selected_idx = min(
                len(self.items) - 1, self.selected_idx + visible_height
            )
            self._adjust_scroll_for_height(visible_height)
            return "navigate"
        elif key == curses.KEY_ENTER or key == 10 or key == 13:
            if self.on_select and self.items:
                self.on_select(self.items[self.selected_idx].data)
            return "select"

        return None

    def move_up(self) -> None:
        """Move selection up."""
        if self.selected_idx > 0:
            self.selected_idx -= 1

    def move_down(self) -> None:
        """Move selection down."""
        if self.selected_idx < len(self.items) - 1:
            self.selected_idx += 1

    def get_selected(self) -> Optional[T]:
        """Get the currently selected item data."""
        if self.items and 0 <= self.selected_idx < len(self.items):
            return self.items[self.selected_idx].data
        return None

    def get_selected_index(self) -> int:
        """Get the currently selected index."""
        return self.selected_idx

    def select_index(self, idx: int) -> None:
        """Select a specific index."""
        if 0 <= idx < len(self.items):
            self.selected_idx = idx
