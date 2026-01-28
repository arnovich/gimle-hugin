"""Interaction detail screen for the interactive TUI."""

import curses
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from gimle.hugin.cli.interactive.screens.base import BaseScreen
from gimle.hugin.cli.interactive.state import ArtifactInfo
from gimle.hugin.cli.interactive.widgets.detail_view import DetailView

if TYPE_CHECKING:
    from gimle.hugin.cli.interactive.app import InteractiveApp


class DetailScreen(BaseScreen):
    """Screen showing details of a single interaction."""

    def __init__(self, app: "InteractiveApp"):
        """Initialize the detail screen."""
        super().__init__(app)
        self.detail_view = DetailView()
        self.artifacts: List[ArtifactInfo] = []
        self.selected_artifact_idx = 0
        self._load_content()

    def _load_content(self) -> None:
        """Load the interaction detail content."""
        detail = self.state.interaction_detail
        if detail:
            # Filter out some noise fields
            filtered: Dict[str, Any] = {}
            skip_fields = {"stack", "branch_id"}

            for key, value in detail.items():
                if key not in skip_fields:
                    filtered[key] = value

            # Load artifact metadata for this interaction
            self.artifacts = self._load_artifacts()
            if self.artifacts:
                # Show artifact summary (just count and types)
                artifact_summary = []
                for i, art in enumerate(self.artifacts):
                    short_id = art.id[:8] if len(art.id) > 8 else art.id
                    marker = ">" if i == self.selected_artifact_idx else " "
                    artifact_summary.append(
                        f"{marker} [{i}] {art.type} ({short_id})"
                    )
                filtered["artifacts (press 'a' to view)"] = artifact_summary

            self.detail_view.set_content(filtered)
        else:
            self.detail_view.set_text("(no detail available)")

    def _load_artifacts(self) -> List[ArtifactInfo]:
        """Load artifact info for the current interaction."""
        idx = self.state.selected_interaction_idx
        if idx < 0 or idx >= len(self.state.interactions):
            return []

        interaction = self.state.interactions[idx]
        artifacts = []

        for artifact_id in interaction.artifact_ids:
            info = self.state.load_artifact_info(artifact_id, interaction.id)
            if info:
                artifacts.append(info)

        return artifacts

    def get_title(self) -> str:
        """Return the screen title."""
        detail = self.state.interaction_detail
        if detail:
            int_type = detail.get("type", "Unknown")
            return f"Interaction Detail: {int_type}"
        return "Interaction Detail"

    def get_status_text(self) -> str:
        """Return status bar text."""
        parts = ["Esc:Back", "↑/↓:Scroll", "←/→:Prev/Next"]
        if self.artifacts:
            parts.extend(["a:Artifact", "[/]:Select"])
        parts.extend(["l:Logs", "^L:LogsFull"])
        return " ".join(parts)

    def render(self, stdscr: curses.window) -> None:
        """Render the interaction detail."""
        start_row, end_row, start_col, end_col = self.render_frame(stdscr)

        # Render the detail view
        self.detail_view.render(stdscr, start_row, end_row, start_col, end_col)

    def handle_input(self, key: int) -> Optional[str]:
        """Handle keyboard input for scrolling."""
        height, _ = self.app.get_size()
        visible_height = height - 2

        result = self.detail_view.handle_input(key, visible_height)

        if result:
            return result

        # Left/right arrows to navigate between interactions
        if key == curses.KEY_LEFT:
            idx = self.state.selected_interaction_idx
            if idx > 0:
                self.state.selected_interaction_idx = idx - 1
                self.state.load_interaction_detail(idx - 1)
                self.selected_artifact_idx = 0
                self._load_content()
                return "refresh"
        elif key == curses.KEY_RIGHT:
            idx = self.state.selected_interaction_idx
            if idx < len(self.state.interactions) - 1:
                self.state.selected_interaction_idx = idx + 1
                self.state.load_interaction_detail(idx + 1)
                self.selected_artifact_idx = 0
                self._load_content()
                return "refresh"
        elif key == ord("["):
            # Select previous artifact
            if self.artifacts and self.selected_artifact_idx > 0:
                self.selected_artifact_idx -= 1
                self._load_content()
                return "refresh"
        elif key == ord("]"):
            # Select next artifact
            if (
                self.artifacts
                and self.selected_artifact_idx < len(self.artifacts) - 1
            ):
                self.selected_artifact_idx += 1
                self._load_content()
                return "refresh"
        elif key in (ord("a"), ord("A")):
            # View selected artifact
            if self.artifacts:
                from gimle.hugin.cli.interactive.screens.artifact import (
                    ArtifactScreen,
                )

                artifact = self.artifacts[self.selected_artifact_idx]
                self.app.push_screen(ArtifactScreen(self.app, artifact.id))
                return "refresh"

        return "refresh"
