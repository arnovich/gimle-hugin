"""Artifacts list screen for the interactive TUI."""

import curses
from typing import TYPE_CHECKING, Optional

from gimle.hugin.cli.interactive.colors import COLOR_TOOL
from gimle.hugin.cli.interactive.screens.base import BaseScreen
from gimle.hugin.cli.interactive.state import ArtifactInfo
from gimle.hugin.cli.interactive.widgets.list_view import ListItem, ListView

if TYPE_CHECKING:
    from gimle.hugin.cli.interactive.app import InteractiveApp


class ArtifactsListScreen(BaseScreen):
    """Screen showing list of all artifacts for an agent."""

    def __init__(self, app: "InteractiveApp"):
        """Initialize the artifacts list screen."""
        super().__init__(app)
        self.list_view: ListView[ArtifactInfo] = ListView(
            items=[], on_select=self._on_artifact_select
        )
        self._refresh_items()

    def _refresh_items(self) -> None:
        """Refresh the list items from state."""
        artifacts = self.state.get_all_artifacts_for_agent()
        items = []

        for i, artifact in enumerate(artifacts):
            # Build prefix with index
            prefix = f"{i:3d}."

            # Build label with type and format
            format_str = f" ({artifact.format})" if artifact.format else ""
            label = f"{artifact.type}{format_str}"

            # Build secondary info with preview
            preview = artifact.preview
            if len(preview) > 50:
                preview = preview[:47] + "..."
            # Replace newlines with spaces for display
            preview = preview.replace("\n", " ")

            # Short ID
            short_id = artifact.id[:8] if len(artifact.id) > 8 else artifact.id

            secondary = f"{short_id} - {preview}" if preview else short_id

            items.append(
                ListItem(
                    data=artifact,
                    label=label,
                    secondary=secondary,
                    color=COLOR_TOOL,
                    prefix=prefix,
                )
            )

        self.list_view.set_items(items)

    def _on_artifact_select(self, artifact: ArtifactInfo) -> None:
        """Handle artifact selection."""
        from gimle.hugin.cli.interactive.screens.artifact import ArtifactScreen

        self.app.push_screen(ArtifactScreen(self.app, artifact.id))

    def get_title(self) -> str:
        """Return the screen title."""
        # Find agent name
        agent_name = "unknown"
        for agent in self.state.agents:
            if agent.id == self.state.selected_agent_id:
                agent_name = agent.config_name
                break
        return f"Agent: {agent_name} | Artifacts"

    def get_status_text(self) -> str:
        """Return status bar text."""
        artifacts = self.state.get_all_artifacts_for_agent()
        count = len(artifacts)
        return (
            f"Esc:Back  Enter:View  ↑/↓:Nav  l:Logs  ^L:LogsFull | {count} art"
        )

    def render(self, stdscr: curses.window) -> None:
        """Render the artifacts list."""
        start_row, end_row, start_col, end_col = self.render_frame(stdscr)

        # Refresh items in case data changed
        self._refresh_items()

        if not self.list_view.items:
            try:
                stdscr.addstr(
                    start_row, start_col, "(No artifacts for this agent)"
                )
            except curses.error:
                pass
            return

        # Render the list
        self.list_view.render(stdscr, start_row, end_row, start_col, end_col)

    def handle_input(self, key: int) -> Optional[str]:
        """Handle keyboard input."""
        height, _ = self.app.get_size()
        visible_height = height - 2

        result = self.list_view.handle_input(key, visible_height)

        if result in ("select", "navigate"):
            return "refresh"

        return "refresh" if result else None
