"""Sessions list screen for the interactive TUI."""

import curses
from typing import TYPE_CHECKING, Optional

from gimle.hugin.cli.interactive.colors import (
    COLOR_RUNNING,
    COLOR_SUCCESS,
    COLOR_TASK,
)
from gimle.hugin.cli.interactive.screens.base import BaseScreen
from gimle.hugin.cli.interactive.state import SessionInfo
from gimle.hugin.cli.interactive.widgets.list_view import ListItem, ListView

if TYPE_CHECKING:
    from gimle.hugin.cli.interactive.app import InteractiveApp


class SessionsScreen(BaseScreen):
    """Screen showing list of all sessions."""

    def __init__(self, app: "InteractiveApp"):
        """Initialize the sessions screen."""
        super().__init__(app)
        self.list_view: ListView[SessionInfo] = ListView(
            items=[], on_select=self._on_session_select
        )
        self._refresh_items()

    def _refresh_items(self) -> None:
        """Refresh the list items from state."""
        items = []
        for session in self.state.sessions:
            # Determine prefix and color based on session state
            if session.num_awaiting_input > 0:
                prefix = "?"
                color = COLOR_TASK
            elif session.num_running > 0:
                prefix = "●"
                color = COLOR_RUNNING
            elif (
                session.num_finished == session.num_agents
                and session.num_agents > 0
            ):
                prefix = "✓"
                color = COLOR_SUCCESS
            else:
                prefix = "○"
                color = 0

            # Format ID (truncate)
            session_id = session.id[:8] if len(session.id) > 8 else session.id

            # Build agent status summary
            status_parts = []
            if session.num_running > 0:
                status_parts.append(f"{session.num_running} running")
            if session.num_awaiting_input > 0:
                status_parts.append(f"{session.num_awaiting_input} awaiting")
            if session.num_finished > 0:
                status_parts.append(f"{session.num_finished} done")
            if session.num_idle > 0:
                status_parts.append(f"{session.num_idle} idle")

            # Format created time
            created_text = ""
            if session.created_at:
                created_text = session.created_at.strftime("%Y-%m-%d %H:%M")

            # Build secondary info
            agents_text = f"{session.num_agents} agent"
            if session.num_agents != 1:
                agents_text += "s"

            if status_parts:
                agents_text += f" ({', '.join(status_parts)})"

            time_text = self.state.get_relative_time(session.last_modified)

            if created_text:
                secondary = f"{agents_text} | Created: {created_text} | Updated: {time_text}"
            else:
                secondary = f"{agents_text} | Updated: {time_text}"

            items.append(
                ListItem(
                    data=session,
                    label=session_id,
                    secondary=secondary,
                    color=color,
                    prefix=prefix,
                )
            )

        self.list_view.set_items(items)

    def _on_session_select(self, session: SessionInfo) -> None:
        """Handle session selection."""
        self.state.select_session(session.id)

        from gimle.hugin.cli.interactive.screens.agents import AgentsScreen

        self.app.push_screen(AgentsScreen(self.app))

    def get_title(self) -> str:
        """Return the screen title."""
        return "Sessions"

    def get_status_text(self) -> str:
        """Return status bar text."""
        count = len(self.state.sessions)
        return (
            f"q:Quit  ?:Help  r:Refresh  n:New  d:Del  "
            f"l:Logs  ^L:LogsFull | {count} sessions"
        )

    def render(self, stdscr: curses.window) -> None:
        """Render the sessions list."""
        start_row, end_row, start_col, end_col = self.render_frame(stdscr)

        # Refresh items in case data changed
        self._refresh_items()

        # Render the list
        self.list_view.render(stdscr, start_row, end_row, start_col, end_col)

    def handle_input(self, key: int) -> Optional[str]:
        """Handle keyboard input."""
        height, _ = self.app.get_size()
        visible_height = height - 2  # Subtract header and status bar

        result = self.list_view.handle_input(key, visible_height)

        if result == "select":
            # Enter - drill into session
            selected = self.list_view.get_selected()
            if selected:
                self._on_session_select(selected)
            return "refresh"
        elif result == "navigate":
            return "refresh"
        elif key in (ord("n"), ord("N")):
            # Start new agent
            from gimle.hugin.cli.interactive.screens.new_agent import (
                NewAgentScreen,
            )

            self.app.push_screen(NewAgentScreen(self.app))
            return "refresh"
        elif key in (ord("d"), ord("D")):
            # Delete selected session with confirmation
            selected = self.list_view.get_selected()
            if selected:
                from gimle.hugin.cli.interactive.screens.confirm import (
                    ConfirmScreen,
                )

                session_id = selected.id[:8]
                message = (
                    f"Are you sure you want to delete session '{session_id}'? "
                    f"This will permanently delete {selected.num_agents} agent(s) "
                    "and all associated data."
                )

                def do_delete() -> bool:
                    return self.state.delete_session(selected.id)

                self.app.push_screen(
                    ConfirmScreen(
                        self.app,
                        title="Delete Session",
                        message=message,
                        on_confirm=do_delete,
                    )
                )
            return "refresh"

        return "refresh" if result else None
