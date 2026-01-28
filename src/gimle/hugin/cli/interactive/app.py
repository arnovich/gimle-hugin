"""Main TUI application for interactive agent runner."""

import curses
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from gimle.hugin.cli.interactive.colors import init_colors
from gimle.hugin.cli.interactive.logging import LogManager
from gimle.hugin.cli.interactive.state import AppState

if TYPE_CHECKING:
    from gimle.hugin.cli.interactive.screens.base import BaseScreen


@dataclass
class AgentLaunchConfig:
    """Pre-configured agent launch parameters for auto-launching."""

    task_path: str
    task_name: str
    config_name: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    max_steps: int = 100
    model: Optional[str] = None


class InteractiveApp:
    """Main application class for the interactive TUI."""

    def __init__(
        self,
        storage_path: str,
        task_path: Optional[str] = None,
        launch_config: Optional[AgentLaunchConfig] = None,
    ):
        """Initialize the interactive TUI application."""
        self.storage_path = storage_path
        self.task_path = task_path
        self.launch_config = launch_config
        self.state = AppState(storage_path, task_path=task_path)
        self.screen_stack: List["BaseScreen"] = []
        self.stdscr: Optional[curses.window] = None
        self.running = False
        self.needs_refresh = True

    def run(self) -> None:
        """Run the TUI application."""
        curses.wrapper(self._main)

    def _main(self, stdscr: curses.window) -> None:
        """Run the main curses loop."""
        self.stdscr = stdscr
        self.running = True

        # Setup curses
        curses.curs_set(0)  # Hide cursor
        stdscr.keypad(True)  # Enable special keys
        stdscr.nodelay(False)  # Blocking input
        stdscr.timeout(100)  # 100ms timeout for responsive updates

        # Initialize colors
        init_colors()

        # Initialize logging
        log_manager = LogManager.initialize(Path(self.storage_path))
        log_manager.attach_to_loggers()

        # Load initial data
        self.state.refresh_data()

        # Start storage watcher
        self.state.start_watcher()
        self.state.add_update_callback(self._on_data_update)

        # Push initial screen
        from gimle.hugin.cli.interactive.screens.sessions import SessionsScreen

        self.push_screen(SessionsScreen(self))

        # If launch config provided, push NewAgentScreen and auto-launch
        if self.launch_config:
            from gimle.hugin.cli.interactive.screens.new_agent import (
                NewAgentScreen,
            )

            screen = NewAgentScreen(self)
            screen.auto_launch(self.launch_config)
            self.push_screen(screen)

        # Main loop
        try:
            while self.running and self.screen_stack:
                self._render()
                self._handle_input()
        finally:
            self.state.stop_watcher()
            LogManager.shutdown()

    def _on_data_update(self) -> None:
        """Handle storage data updates."""
        self.needs_refresh = True

    def _render(self) -> None:
        """Render the current screen."""
        if not self.stdscr or not self.screen_stack:
            return

        if self.needs_refresh:
            self.stdscr.clear()
            self.screen_stack[-1].render(self.stdscr)
            self.stdscr.refresh()
            self.needs_refresh = False

    def _handle_input(self) -> None:
        """Handle keyboard input."""
        if not self.stdscr or not self.screen_stack:
            return

        try:
            key = self.stdscr.getch()
        except curses.error:
            return

        if key == -1:  # Timeout, no input
            return

        current_screen = self.screen_stack[-1]

        # If screen is capturing text input, bypass global shortcuts
        # and let the screen handle all input (except delegated below)
        if current_screen.is_capturing_input():
            result = current_screen.handle_input(key)
            if result == "pop":
                self.pop_screen()
            elif result == "refresh":
                self.needs_refresh = True
            return

        # Global keys (case-insensitive)
        # 'q' only quits from the root screen (sessions list)
        if key in (ord("q"), ord("Q")):
            if len(self.screen_stack) == 1:
                self.running = False
            return
        elif key == 27:  # Escape - go back one screen
            self.pop_screen()
            return
        elif key == ord("?"):
            self._show_help()
            return
        elif key in (ord("r"), ord("R")):
            self.state.refresh_data()
            self.needs_refresh = True
            return
        elif key in (ord("l"), ord("L")):
            # Toggle log panel (skip if already on LogsScreen)
            from gimle.hugin.cli.interactive.screens.logs import LogsScreen

            if not isinstance(current_screen, LogsScreen):
                self.state.log_state.panel_visible = (
                    not self.state.log_state.panel_visible
                )
                self.needs_refresh = True
                return
            # Fall through to let LogsScreen handle it
        elif key == 12:  # Ctrl+L - open logs screen
            self._show_logs()
            return

        # Delegate to current screen
        result = current_screen.handle_input(key)

        if result == "pop":
            self.pop_screen()
        elif result == "refresh":
            self.needs_refresh = True

    def push_screen(self, screen: "BaseScreen") -> None:
        """Push a new screen onto the stack."""
        self.screen_stack.append(screen)
        self.needs_refresh = True

    def pop_screen(self) -> None:
        """Pop the current screen from the stack."""
        if len(self.screen_stack) > 1:
            self.screen_stack.pop()
            self.needs_refresh = True
        else:
            # Last screen, quit the app
            self.running = False

    def quit(self) -> None:
        """Quit the application."""
        self.running = False

    def _show_help(self) -> None:
        """Show the help overlay."""
        from gimle.hugin.cli.interactive.screens.help import HelpScreen

        self.push_screen(HelpScreen(self))

    def _show_logs(self) -> None:
        """Show the logs screen."""
        from gimle.hugin.cli.interactive.screens.logs import LogsScreen

        self.push_screen(LogsScreen(self))

    def get_size(self) -> tuple:
        """Get the terminal size."""
        if self.stdscr:
            return self.stdscr.getmaxyx()
        return (24, 80)
