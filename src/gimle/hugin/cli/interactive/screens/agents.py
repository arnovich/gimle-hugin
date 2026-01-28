"""Agents list screen for the interactive TUI."""

import curses
import threading
from typing import TYPE_CHECKING, Optional

from gimle.hugin.cli.interactive.colors import (
    COLOR_RUNNING,
    COLOR_SUCCESS,
    COLOR_TASK,
)
from gimle.hugin.cli.interactive.logging.handler import (
    clear_agent_context,
    set_agent_context,
)
from gimle.hugin.cli.interactive.screens.base import BaseScreen
from gimle.hugin.cli.interactive.state import AgentInfo
from gimle.hugin.cli.interactive.widgets.list_view import ListItem, ListView

if TYPE_CHECKING:
    from gimle.hugin.cli.interactive.app import InteractiveApp


class AgentsScreen(BaseScreen):
    """Screen showing list of agents in a session."""

    def __init__(self, app: "InteractiveApp"):
        """Initialize the agents screen."""
        super().__init__(app)
        self.list_view: ListView[AgentInfo] = ListView(
            items=[], on_select=self._on_agent_select
        )
        self._refresh_items()

    def _refresh_items(self) -> None:
        """Refresh the list items from state."""
        items = []
        for agent in self.state.agents:
            # Get controller status
            controller = self.state.get_controller(agent.id)
            ctrl_status = controller.get_status()

            # Determine display based on running state and controller
            if agent.awaiting_input:
                # Agent waiting for human input
                prefix = "?"
                color = COLOR_TASK
                status_text = "Awaiting Input"
            elif agent.is_finished:
                # Agent completed (terminal Waiting state)
                prefix = "✓"
                color = COLOR_SUCCESS
                status_text = "Finished"
            elif agent.is_running:
                if ctrl_status == "Paused":
                    prefix = "⏸"
                    color = COLOR_TASK  # Yellow for paused
                    status_text = "Paused"
                elif ctrl_status == "Step":
                    prefix = "⏯"
                    color = COLOR_TASK
                    status_text = "Step-through"
                else:
                    prefix = "●"
                    color = COLOR_RUNNING
                    status_text = "Running"
            else:
                prefix = "○"
                color = 0
                status_text = "Idle"

            # Build secondary info
            interactions_text = f"{agent.num_interactions} interactions"
            time_text = self.state.get_relative_time(agent.last_modified)
            secondary = f"[{status_text}] {interactions_text}, {time_text}"

            items.append(
                ListItem(
                    data=agent,
                    label=agent.config_name,
                    secondary=secondary,
                    color=color,
                    prefix=prefix,
                )
            )

        self.list_view.set_items(items)

    def _on_agent_select(self, agent: AgentInfo) -> None:
        """Handle agent selection."""
        self.state.select_agent(agent.id)

        from gimle.hugin.cli.interactive.screens.interactions import (
            InteractionsScreen,
        )

        self.app.push_screen(InteractionsScreen(self.app))

    def _navigate_session(self, direction: int) -> None:
        """Navigate to previous/next session.

        Args:
            direction: -1 for previous, 1 for next
        """
        if not self.state.sessions:
            return

        # Find current session index
        current_idx = -1
        for i, session in enumerate(self.state.sessions):
            if session.id == self.state.selected_session_id:
                current_idx = i
                break

        if current_idx < 0:
            return

        # Calculate new index
        new_idx = current_idx + direction
        if new_idx < 0 or new_idx >= len(self.state.sessions):
            return

        # Select the new session
        new_session = self.state.sessions[new_idx]
        self.state.select_session(new_session.id)
        self._refresh_items()

    def get_title(self) -> str:
        """Return the screen title."""
        session_id = self.state.selected_session_id or ""
        short_id = session_id[:8] if len(session_id) > 8 else session_id
        return f"Session {short_id} | Agents"

    def get_status_text(self) -> str:
        """Return status bar text."""
        count = len(self.state.agents)

        # Show relevant actions based on selected agent state
        selected = self.list_view.get_selected()
        if selected and selected.awaiting_input:
            # Agent waiting for human input
            actions = "h:Respond"
        elif selected and selected.is_finished:
            # Finished agents can be re-run
            actions = "c:Run"
        elif selected and selected.is_running:
            controller = self.state.get_controller(selected.id)
            if controller.paused:
                actions = "c:Resume"
            else:
                actions = "p:Pause"
        elif selected:
            actions = "c:Run"
        else:
            actions = ""

        parts = ["Esc:Back", "?:Help", "r:Refresh"]
        if actions:
            parts.append(actions)
        parts.extend(["d:Del", "l:Logs", "^L:LogsFull"])
        return f"{' '.join(parts)} | {count} agents"

    def render(self, stdscr: curses.window) -> None:
        """Render the agents list."""
        start_row, end_row, start_col, end_col = self.render_frame(stdscr)

        # Refresh items in case data changed
        self._refresh_items()

        # Render the list
        self.list_view.render(stdscr, start_row, end_row, start_col, end_col)

    def handle_input(self, key: int) -> Optional[str]:
        """Handle keyboard input."""
        height, _ = self.app.get_size()
        visible_height = height - 2

        result = self.list_view.handle_input(key, visible_height)

        if result == "select":
            # Enter - drill into agent
            selected = self.list_view.get_selected()
            if selected:
                self._on_agent_select(selected)
            return "refresh"
        elif result == "prev":
            # Left arrow - go to previous session
            self._navigate_session(-1)
            return "refresh"
        elif result == "next":
            # Right arrow - go to next session
            self._navigate_session(1)
            return "refresh"
        elif result == "navigate":
            return "refresh"
        elif key in (ord("p"), ord("P")):
            # Pause selected agent
            agent = self.list_view.get_selected()
            if agent:
                controller = self.state.get_controller(agent.id)
                controller.pause()
            return "refresh"
        elif key in (ord("c"), ord("C")):
            # Continue/resume/run selected agent
            selected = self.list_view.get_selected()
            if selected:
                if selected.is_finished or not selected.is_running:
                    # Run idle/finished agent
                    self._run_agent(selected)
                else:
                    # Resume paused agent
                    controller = self.state.get_controller(selected.id)
                    controller.resume()
            return "refresh"
        elif key in (ord("h"), ord("H")):
            # Respond to agent awaiting human input
            selected = self.list_view.get_selected()
            if selected and selected.awaiting_input:
                from gimle.hugin.cli.interactive.screens.human_input import (
                    HumanInputScreen,
                )

                # Capture the agent in a local variable to satisfy type checker
                agent_to_respond = selected
                question = (
                    agent_to_respond.awaiting_input_question
                    or "Agent is waiting for your response:"
                )

                def do_respond(response: str) -> bool:
                    success = self.state.submit_human_response(
                        agent_to_respond.id, response
                    )
                    if success:
                        # Run the agent after submitting response
                        self._run_agent(agent_to_respond)
                    return success

                self.app.push_screen(
                    HumanInputScreen(
                        self.app,
                        question=question,
                        on_submit=do_respond,
                    )
                )
            return "refresh"
        elif key in (ord("d"), ord("D")):
            # Delete selected agent with confirmation
            selected = self.list_view.get_selected()
            if selected:
                from gimle.hugin.cli.interactive.screens.confirm import (
                    ConfirmScreen,
                )

                message = (
                    f"Are you sure you want to delete agent '{selected.config_name}'? "
                    f"This will permanently delete {selected.num_interactions} "
                    "interaction(s) and all associated data."
                )

                def do_delete() -> bool:
                    return self.state.delete_agent(selected.id)

                self.app.push_screen(
                    ConfirmScreen(
                        self.app,
                        title="Delete Agent",
                        message=message,
                        on_confirm=do_delete,
                    )
                )
            return "refresh"

        return "refresh" if result else None

    def _run_agent(self, agent_info: AgentInfo) -> None:
        """Run/resume an idle agent.

        Args:
            agent_info: The agent info for the agent to run
        """
        if not self.state.selected_session_id:
            return

        # Load the session and agent
        result = self.state.load_agent_for_resume(
            self.state.selected_session_id, agent_info.id
        )
        if not result:
            return

        session, agent = result

        # Get controller for this agent
        controller = self.state.get_controller(agent.id)

        # Mark as running in the UI
        agent_info.is_running = True

        # Run agent in background thread
        max_steps = 100

        def run_agent() -> None:
            # Set agent context for logging
            set_agent_context(agent.id, self.state.selected_session_id)
            step_count = 0
            try:
                while step_count < max_steps:
                    # Check controller before each step
                    if not controller.should_continue():
                        import time

                        time.sleep(0.1)
                        continue

                    # Take a step
                    if not agent.step():
                        break  # Agent completed

                    step_count += 1
                    self.state.storage.save_session(session)
            except Exception:
                pass
            finally:
                clear_agent_context()
                self.state.storage.save_session(session)
                # Refresh state to show updated agent
                self.state.refresh_data()

        thread = threading.Thread(target=run_agent, daemon=True)
        thread.start()
