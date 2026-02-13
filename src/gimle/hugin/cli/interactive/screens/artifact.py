"""Artifact detail screen for the interactive TUI."""

import curses
import json
from typing import TYPE_CHECKING, Any, Dict, Optional

from gimle.hugin.artifacts.feedback import ArtifactFeedback
from gimle.hugin.cli.interactive.screens.base import BaseScreen
from gimle.hugin.cli.interactive.state import load_artifact_rating
from gimle.hugin.cli.interactive.widgets.detail_view import DetailView
from gimle.hugin.storage.local import LocalStorage

if TYPE_CHECKING:
    from gimle.hugin.cli.interactive.app import InteractiveApp


class ArtifactScreen(BaseScreen):
    """Screen showing full content of an artifact."""

    def __init__(self, app: "InteractiveApp", artifact_id: str):
        """Initialize the artifact screen.

        Args:
            app: The interactive app instance
            artifact_id: The artifact UUID to display
        """
        super().__init__(app)
        self.artifact_id = artifact_id
        self.artifact_type = "Unknown"
        self.artifact_format: Optional[str] = None
        self.detail_view = DetailView()
        self.rating_summary = ""
        self._load_artifact()
        self._load_feedback()

    def _load_artifact(self) -> None:
        """Load the full artifact content."""
        try:
            artifact_path = (
                self.state.storage_path / "artifacts" / self.artifact_id
            )
            if not artifact_path.exists():
                self.detail_view.set_text(
                    f"Artifact not found: {self.artifact_id}"
                )
                return

            with open(artifact_path, "r") as f:
                raw: Dict[str, Any] = json.load(f)

            self.artifact_type = raw.get("type", "Unknown")
            artifact_data = raw.get("data", {})
            self.artifact_format = artifact_data.get("format")

            # Extract content based on artifact type
            if self.artifact_type in ("Text",):
                content = artifact_data.get("content", "")
                if isinstance(content, str):
                    self.detail_view.set_text(content)
                else:
                    self.detail_view.set_content(content)
            elif self.artifact_type in ("File", "Image"):
                # Show metadata for file-based artifacts
                display_data = {
                    "type": self.artifact_type,
                    "name": artifact_data.get("name", ""),
                    "description": artifact_data.get("description", ""),
                    "format": self.artifact_format,
                    "created_at": artifact_data.get("created_at", ""),
                }
                # For images, note that they can't be displayed in terminal
                if self.artifact_type == "Image":
                    display_data["note"] = (
                        "Image content cannot be displayed in terminal"
                    )
                self.detail_view.set_content(display_data)
            elif self.artifact_type == "QueryEngine":
                # Show query engine metadata
                display_data = {
                    "type": self.artifact_type,
                    "name": artifact_data.get("name", ""),
                    "description": artifact_data.get("description", ""),
                    "query_description": artifact_data.get(
                        "query_description", ""
                    ),
                    "created_at": artifact_data.get("created_at", ""),
                }
                self.detail_view.set_content(display_data)
            else:
                # Generic display for other types
                self.detail_view.set_content(artifact_data)

        except Exception as e:
            self.detail_view.set_text(f"Error loading artifact: {e}")

    def _load_feedback(self) -> None:
        """Load feedback summary for this artifact."""
        result = load_artifact_rating(
            self.state.storage_path,
            self.artifact_id,
            storage=self.state.storage,
        )
        if result is not None:
            avg, count = result
            self.rating_summary = (
                f" [{avg:.1f}/5, {count} rating" f"{'s' if count != 1 else ''}]"
            )
        else:
            self.rating_summary = ""

    def _save_rating(self, rating: int) -> str:
        """Save a human rating and return status message."""
        try:
            storage = LocalStorage(base_path=str(self.state.storage_path))
            # Check for existing human rating
            for fb_id in storage.list_feedback(self.artifact_id):
                try:
                    existing = storage.load_feedback(fb_id)
                    if existing.source == "human":
                        return "Already rated this artifact"
                except (ValueError, OSError):
                    continue
            feedback = ArtifactFeedback(
                artifact_id=self.artifact_id,
                rating=rating,
                agent_id=None,
                source="human",
            )
            storage.save_feedback(feedback)
            self._load_feedback()
            return f"Saved rating {rating}/5"
        except Exception as e:
            return f"Error: {e}"

    def get_title(self) -> str:
        """Return the screen title."""
        short_id = (
            self.artifact_id[:12]
            if len(self.artifact_id) > 12
            else self.artifact_id
        )
        format_str = (
            f" ({self.artifact_format})" if self.artifact_format else ""
        )
        return (
            f"Artifact: {self.artifact_type}{format_str}"
            f" - {short_id}{self.rating_summary}"
        )

    def get_status_text(self) -> str:
        """Return status bar text."""
        return (
            "Esc:Back  ↑/↓:Scroll  g/G:Top/Bottom"
            "  r:Rate  l:Logs  ^L:LogsFull"
        )

    def render(self, stdscr: curses.window) -> None:
        """Render the artifact content."""
        start_row, end_row, start_col, end_col = self.render_frame(stdscr)

        # Render the detail view
        self.detail_view.render(stdscr, start_row, end_row, start_col, end_col)

    def handle_input(self, key: int) -> Optional[str]:
        """Handle keyboard input for scrolling and rating."""
        height, _ = self.app.get_size()
        visible_height = height - 2

        # Handle 'r' key for rating
        if key == ord("r"):
            self._handle_rate_key()
            return "refresh"

        result = self.detail_view.handle_input(key, visible_height)

        if result:
            return result

        return "refresh"

    def _handle_rate_key(self) -> None:
        """Handle the 'r' key to capture a rating digit."""
        stdscr = self.app.stdscr
        if stdscr is None:
            return

        height, width = stdscr.getmaxyx()
        prompt = "Rating (1-5, Esc to cancel): "
        try:
            stdscr.addstr(
                height - 1,
                0,
                prompt + " " * (width - len(prompt) - 1),
            )
            stdscr.refresh()
        except curses.error:
            pass

        key = stdscr.getch()
        if key == 27:  # Escape
            msg = "Rating cancelled"
        elif ord("1") <= key <= ord("5"):
            rating = key - ord("0")
            msg = self._save_rating(rating)
        else:
            msg = "Invalid key (press 1-5 to rate)"

        try:
            stdscr.addstr(
                height - 1,
                0,
                msg + " " * (width - len(msg) - 1),
            )
            stdscr.refresh()
        except curses.error:
            pass
        curses.napms(800)
