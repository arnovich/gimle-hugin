"""Interactions list screen for the interactive TUI."""

import curses
import logging
import threading
from typing import TYPE_CHECKING, Optional

from gimle.hugin.cli.interactive.colors import (
    COLOR_RUNNING,
    COLOR_SUCCESS,
    COLOR_TASK,
    get_interaction_color,
)
from gimle.hugin.cli.interactive.logging.handler import (
    clear_agent_context,
    set_agent_context,
)
from gimle.hugin.cli.interactive.screens.base import BaseScreen
from gimle.hugin.cli.interactive.state import AgentInfo, InteractionInfo
from gimle.hugin.cli.interactive.widgets.list_view import ListItem, ListView

if TYPE_CHECKING:
    from gimle.hugin.cli.interactive.app import InteractiveApp

logger = logging.getLogger(__name__)


class InteractionsScreen(BaseScreen):
    """Screen showing list of interactions in an agent's stack."""

    # Number of rows used by the agent info header
    HEADER_ROWS = 4

    def __init__(self, app: "InteractiveApp"):
        """Initialize the interactions screen."""
        super().__init__(app)
        self.list_view: ListView[InteractionInfo] = ListView(
            items=[], on_select=self._on_interaction_select
        )
        self._refresh_items()

    def _get_current_agent(self) -> Optional[AgentInfo]:
        """Get the currently selected agent info."""
        for agent in self.state.agents:
            if agent.id == self.state.selected_agent_id:
                return agent
        return None

    def _refresh_items(self) -> None:
        """Refresh the list items from state."""
        items = []
        for i, interaction in enumerate(self.state.interactions):
            color = get_interaction_color(interaction.type)

            # Build prefix with index and artifact indicator
            if interaction.has_artifacts:
                artifact_count = len(interaction.artifact_ids)
                prefix = f"{i:3d}. [{artifact_count}]"
            else:
                prefix = f"{i:3d}.    "

            # Build secondary info
            secondary_parts = []
            if interaction.branch:
                secondary_parts.append(f"branch:{interaction.branch}")
            if interaction.is_error:
                secondary_parts.append("ERROR")
            if interaction.has_artifacts:
                secondary_parts.append(
                    f"{len(interaction.artifact_ids)} artifact(s)"
                )
            secondary = ", ".join(secondary_parts)

            # Build label
            label = f"{interaction.type}: {interaction.label}"

            items.append(
                ListItem(
                    data=interaction,
                    label=label,
                    secondary=secondary,
                    color=color,
                    prefix=prefix,
                )
            )

        self.list_view.set_items(items)

    def _on_interaction_select(self, interaction: InteractionInfo) -> None:
        """Handle interaction selection."""
        idx = self.list_view.get_selected_index()
        self.state.selected_interaction_idx = idx
        self.state.load_interaction_detail(idx)

        from gimle.hugin.cli.interactive.screens.detail import DetailScreen

        self.app.push_screen(DetailScreen(self.app))

    def _navigate_agent(self, direction: int) -> None:
        """Navigate to previous/next agent.

        Args:
            direction: -1 for previous, 1 for next
        """
        if not self.state.agents:
            return

        # Find current agent index
        current_idx = -1
        for i, agent in enumerate(self.state.agents):
            if agent.id == self.state.selected_agent_id:
                current_idx = i
                break

        if current_idx < 0:
            return

        # Calculate new index
        new_idx = current_idx + direction
        if new_idx < 0 or new_idx >= len(self.state.agents):
            return

        # Select the new agent
        new_agent = self.state.agents[new_idx]
        self.state.select_agent(new_agent.id)
        self._refresh_items()

    def get_title(self) -> str:
        """Return the screen title."""
        # Find agent name
        agent_name = "unknown"
        for agent in self.state.agents:
            if agent.id == self.state.selected_agent_id:
                agent_name = agent.config_name
                break
        return f"Agent: {agent_name} | Interactions"

    def get_status_text(self) -> str:
        """Return status bar text."""
        count = len(self.state.interactions)
        artifact_count = sum(
            len(i.artifact_ids) for i in self.state.interactions
        )

        # Show agent control actions based on agent state
        agent = self._get_current_agent()
        if agent and agent.awaiting_input:
            # Agent waiting for human input
            agent_actions = "h:Respond"
        elif agent and agent.is_finished:
            # Finished agents can be re-run (rewind first to change outcome)
            agent_actions = "c:Run"
        elif agent and agent.is_running:
            controller = self.state.get_controller(agent.id)
            if controller.paused:
                agent_actions = "c:Resume s:Step"
            elif controller.step_through:
                agent_actions = "n:Next s:Run p:Pause"
            else:
                agent_actions = "p:Pause s:Step"
        elif agent:
            agent_actions = "c:Run"
        else:
            agent_actions = ""

        parts = ["Esc:Back", "?:Help", "r:Refresh", "w:Rewind"]
        if artifact_count > 0:
            parts.append("a:Artifacts")
        if agent_actions:
            parts.append(agent_actions)
        parts.extend(["l:Logs", "^L:LogsFull"])
        return f"{' '.join(parts)} | {count} int"

    def render(self, stdscr: curses.window) -> None:
        """Render the interactions list."""
        start_row, end_row, start_col, end_col = self.render_frame(stdscr)
        width = end_col - start_col

        # Refresh items in case data changed
        self._refresh_items()

        # Render agent info header
        agent = self._get_current_agent()
        if agent:
            row = start_row
            try:
                # Status indicator and config name
                if agent.awaiting_input:
                    status = "Awaiting Input"
                    status_color = curses.color_pair(COLOR_TASK)
                    status_char = "?"
                elif agent.is_finished:
                    status = "Finished"
                    status_color = curses.color_pair(COLOR_SUCCESS)
                    status_char = "✓"
                elif agent.is_running:
                    controller = self.state.get_controller(agent.id)
                    if controller.paused:
                        status = "Paused"
                    elif controller.step_through:
                        status = "Stepping"
                    else:
                        status = "Running"
                    status_color = curses.color_pair(COLOR_RUNNING)
                    status_char = "●"
                else:
                    status = "Idle"
                    status_color = 0
                    status_char = "○"

                # Line 1: Status and config
                line1 = f"{status_char} {agent.config_name}"
                stdscr.addstr(
                    row, start_col, line1, status_color | curses.A_BOLD
                )
                stdscr.addstr(
                    row, start_col + len(line1) + 2, f"[{status}]", status_color
                )
                row += 1

                # Line 2: Agent ID, interaction count, and artifact count
                short_id = agent.id[:12] if len(agent.id) > 12 else agent.id
                artifact_count = sum(
                    len(i.artifact_ids) for i in self.state.interactions
                )
                line2 = (
                    f"ID: {short_id}  |  "
                    f"{agent.num_interactions} interactions  |  "
                    f"{artifact_count} artifacts"
                )
                stdscr.addstr(row, start_col, line2, curses.A_DIM)
                row += 1

                # Line 3: Timestamps
                modified_str = self.state.get_relative_time(agent.last_modified)
                created_str = ""
                if agent.created_at:
                    created_str = agent.created_at.strftime("%Y-%m-%d %H:%M")
                line3 = f"Created: {created_str}  |  Modified: {modified_str}"
                stdscr.addstr(row, start_col, line3[: width - 1], curses.A_DIM)
                row += 1

                # Separator line
                stdscr.addstr(row, start_col, "─" * (width - 1), curses.A_DIM)

            except curses.error:
                pass

            # Adjust list start position
            start_row += self.HEADER_ROWS

        # Render the list
        self.list_view.render(stdscr, start_row, end_row, start_col, end_col)

    def handle_input(self, key: int) -> Optional[str]:
        """Handle keyboard input."""
        height, _ = self.app.get_size()
        # Account for header, status bar, and agent info header
        visible_height = height - 2 - self.HEADER_ROWS

        result = self.list_view.handle_input(key, visible_height)

        if result == "select":
            # Enter - view interaction detail
            selected = self.list_view.get_selected()
            if selected:
                self._on_interaction_select(selected)
            return "refresh"
        elif result == "prev":
            # Left arrow - go to previous agent
            self._navigate_agent(-1)
            return "refresh"
        elif result == "next":
            # Right arrow - go to next agent
            self._navigate_agent(1)
            return "refresh"
        elif result == "navigate":
            return "refresh"
        elif key in (ord("w"), ord("W")):
            # Rewind to selected interaction with confirmation
            idx = self.list_view.get_selected_index()
            if idx is not None and idx < len(self.state.interactions) - 1:
                # Only show rewind if not already at the last interaction
                num_to_remove = len(self.state.interactions) - idx - 1

                from gimle.hugin.cli.interactive.screens.confirm import (
                    ConfirmScreen,
                )

                selected = self.state.interactions[idx]
                message = (
                    f"Rewind to interaction {idx} ({selected.type}: "
                    f"{selected.label[:30]}...)?\n\n"
                    f"This will permanently delete {num_to_remove} "
                    f"interaction(s) after this point."
                )

                def do_rewind() -> bool:
                    if self.state.selected_agent_id:
                        removed = self.state.rewind_agent_to(
                            self.state.selected_agent_id, idx
                        )
                        return removed >= 0
                    return False

                self.app.push_screen(
                    ConfirmScreen(
                        self.app,
                        title="Rewind Agent",
                        message=message,
                        on_confirm=do_rewind,
                        confirm_text="Rewind",
                    )
                )
            return "refresh"
        elif key in (ord("a"), ord("A")):
            # View all artifacts for this agent
            artifact_count = sum(
                len(i.artifact_ids) for i in self.state.interactions
            )
            if artifact_count > 0:
                from gimle.hugin.cli.interactive.screens.artifacts_list import (
                    ArtifactsListScreen,
                )

                self.app.push_screen(ArtifactsListScreen(self.app))
            return "refresh"
        elif key in (ord("p"), ord("P")):
            # Pause the current agent
            agent = self._get_current_agent()
            if agent and agent.is_running:
                controller = self.state.get_controller(agent.id)
                controller.pause()
            return "refresh"
        elif key in (ord("c"), ord("C")):
            # Continue/resume/run the current agent
            agent = self._get_current_agent()
            if agent:
                if agent.is_finished or not agent.is_running:
                    # Run idle/finished agent
                    self._run_agent(agent)
                else:
                    # Resume paused agent
                    controller = self.state.get_controller(agent.id)
                    controller.resume()
            return "refresh"
        elif key in (ord("s"), ord("S")):
            # Toggle step-through mode
            agent = self._get_current_agent()
            if agent and agent.is_running:
                controller = self.state.get_controller(agent.id)
                controller.toggle_step_through()
            return "refresh"
        elif key in (ord("n"), ord("N")):
            # Request next step (for step-through mode)
            agent = self._get_current_agent()
            if agent and agent.is_running:
                controller = self.state.get_controller(agent.id)
                controller.request_step()
            return "refresh"
        elif key in (ord("h"), ord("H")):
            # Respond to agent awaiting human input
            agent = self._get_current_agent()
            if agent and agent.awaiting_input:
                from gimle.hugin.cli.interactive.screens.human_input import (
                    HumanInputScreen,
                )

                question = (
                    agent.awaiting_input_question
                    or "Agent is waiting for your response:"
                )

                def do_respond(response: str) -> bool:
                    success = self.state.submit_human_response(
                        agent.id, response
                    )
                    if success:
                        # Run the agent after submitting response
                        self._run_agent(agent)
                    return success

                self.app.push_screen(
                    HumanInputScreen(
                        self.app,
                        question=question,
                        on_submit=do_respond,
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
                        logger.info(
                            f"Agent {agent.id} completed after {step_count} steps"
                        )
                        break  # Agent completed

                    step_count += 1
                    self.state.storage.save_session(session)
            except Exception as e:
                logger.error(f"Agent {agent.id} error: {e}")
            finally:
                clear_agent_context()
                self.state.storage.save_session(session)
                # Refresh state to show updated agent
                self.state.refresh_data()

        thread = threading.Thread(target=run_agent, daemon=True)
        thread.start()
