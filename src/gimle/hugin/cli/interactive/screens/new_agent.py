"""New agent wizard screen for the interactive TUI."""

import curses
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.cli.interactive.logging.handler import (
    clear_agent_context,
    set_agent_context,
)
from gimle.hugin.cli.interactive.screens.base import BaseScreen
from gimle.hugin.cli.interactive.widgets.list_view import ListItem, ListView

if TYPE_CHECKING:
    from gimle.hugin.cli.interactive.app import (
        AgentLaunchConfig,
        InteractiveApp,
    )


def find_agent_directories(task_path: Optional[Path] = None) -> List[Path]:
    """Find directories that look like agent directories.

    Args:
        task_path: If provided, only return this path if it's a valid agent
                   directory. If not provided, scan common locations.

    Returns:
        List of paths that contain tasks/ or configs/ directories.
    """
    candidates = []

    # If task_path is provided, use it exclusively
    if task_path:
        task_path = task_path.resolve()
        if task_path.exists() and task_path.is_dir():
            if (task_path / "tasks").exists() or (
                task_path / "configs"
            ).exists():
                candidates.append(task_path)
        return candidates

    # Check common locations
    cwd = Path.cwd()

    # Current directory itself
    if (cwd / "tasks").exists() or (cwd / "configs").exists():
        candidates.append(cwd)

    # agents/ subdirectory
    agents_dir = cwd / "agents"
    if agents_dir.exists():
        for item in agents_dir.iterdir():
            if item.is_dir():
                if (item / "tasks").exists() or (item / "configs").exists():
                    candidates.append(item)

    # examples/ subdirectory
    examples_dir = cwd / "examples"
    if examples_dir.exists():
        for item in examples_dir.iterdir():
            if item.is_dir():
                if (item / "tasks").exists() or (item / "configs").exists():
                    candidates.append(item)

    # apps/ subdirectory
    apps_dir = cwd / "apps"
    if apps_dir.exists():
        for item in apps_dir.iterdir():
            if item.is_dir() and not item.name.startswith(("_", ".")):
                if (item / "tasks").exists() or (item / "configs").exists():
                    candidates.append(item)

    return candidates


class NewAgentScreen(BaseScreen):
    """Wizard screen for starting a new agent."""

    # Wizard steps
    STEP_SELECT_DIR = 0
    STEP_SELECT_TASK = 1
    STEP_SELECT_CONFIG = 2
    STEP_SET_PARAMS = 3
    STEP_CONFIRM = 4
    STEP_RUNNING = 5

    def __init__(self, app: "InteractiveApp"):
        """Initialize the new agent wizard screen."""
        super().__init__(app)
        self.step = self.STEP_SELECT_DIR

        # Data for each step
        self.agent_dirs: List[Path] = []
        self.selected_dir: Optional[Path] = None
        self.environment: Optional[Environment] = None

        self.tasks: Dict[str, Any] = {}
        self.selected_task_name: Optional[str] = None
        self.selected_task: Optional[Any] = None

        self.configs: Dict[str, Any] = {}
        self.selected_config_name: Optional[str] = None
        self.selected_config: Optional[Any] = None

        self.task_params: Dict[str, Any] = {}
        self.param_values: Dict[str, str] = {}
        self.param_names: List[str] = []
        self.current_param_idx: int = 0
        self.editing_param: bool = False
        self.param_input_buffer: str = ""

        self.max_steps: int = 100
        self.error_message: Optional[str] = None
        self.running_agent_id: Optional[str] = None

        # List views for selection steps
        self.dir_list: ListView[Path] = ListView(
            items=[], on_select=self._on_dir_select
        )
        self.task_list: ListView[str] = ListView(
            items=[], on_select=self._on_task_select
        )
        self.config_list: ListView[str] = ListView(
            items=[], on_select=self._on_config_select
        )

        # Initialize directory list
        self._load_directories()

    def auto_launch(self, config: "AgentLaunchConfig") -> None:  # noqa: F821
        """Auto-configure and launch an agent from a launch config.

        Skips the wizard steps and goes straight to running.
        """
        task_path = Path(config.task_path).resolve()
        self._on_dir_select(task_path)
        if self.error_message or not self.environment:
            return

        # Select task
        self._on_task_select(config.task_name)
        if self.error_message:
            return  # type: ignore

        # Select config
        if config.config_name:
            self._on_config_select(config.config_name)
        elif self.configs:
            # Use first config
            first_config = list(self.configs.keys())[0]
            self._on_config_select(first_config)
        if self.error_message:
            return  # type: ignore

        # Apply model override
        if config.model and self.selected_config:
            self.selected_config.llm_model = config.model

        # Set parameters
        for name, value in config.parameters.items():
            if name in self.param_values:
                self.param_values[name] = str(value)

        # Set max steps
        self.max_steps = config.max_steps

        # Launch
        self._launch_agent()

    def is_capturing_input(self) -> bool:
        """Return True when editing parameter text."""
        return self.editing_param

    def _load_directories(self) -> None:
        """Load available agent directories."""
        self.agent_dirs = find_agent_directories(task_path=self.state.task_path)
        items = []
        for path in self.agent_dirs:
            # Count tasks and configs
            tasks_count = 0
            configs_count = 0
            tasks_dir = path / "tasks"
            configs_dir = path / "configs"
            if tasks_dir.exists():
                tasks_count = len(list(tasks_dir.glob("*.yaml")))
            if configs_dir.exists():
                configs_count = len(list(configs_dir.glob("*.yaml")))

            secondary = f"{tasks_count} tasks, {configs_count} configs"
            items.append(
                ListItem(
                    data=path,
                    label=path.name,
                    secondary=secondary,
                    prefix="📁",
                )
            )
        self.dir_list.set_items(items)

    def _on_dir_select(self, path: Path) -> None:
        """Handle directory selection."""
        self.selected_dir = path
        self.error_message = None
        try:
            self.environment = Environment.load(
                str(path), storage=self.state.storage
            )
            self._load_tasks()
            self.step = self.STEP_SELECT_TASK
        except Exception as e:
            self.error_message = f"Error loading environment: {e}"

    def _load_tasks(self) -> None:
        """Load available tasks from the environment."""
        if not self.environment:
            return
        self.tasks = self.environment.task_registry.registered()
        items = []
        for name, task in self.tasks.items():
            description = getattr(task, "description", "") or ""
            if len(description) > 50:
                description = description[:47] + "..."
            items.append(
                ListItem(
                    data=name,
                    label=name,
                    secondary=description,
                    prefix="📋",
                )
            )
        self.task_list.set_items(items)

    def _on_task_select(self, task_name: str) -> None:
        """Handle task selection."""
        self.selected_task_name = task_name
        self.error_message = None
        try:
            if self.environment:
                self.selected_task = self.environment.task_registry.get(
                    task_name
                )
                self._load_configs()
                self.step = self.STEP_SELECT_CONFIG
        except Exception as e:
            self.error_message = f"Error loading task: {e}"

    def _load_configs(self) -> None:
        """Load available configs from the environment."""
        if not self.environment:
            return
        self.configs = self.environment.config_registry.registered()
        items = []
        for name, config in self.configs.items():
            model = getattr(config, "llm_model", "unknown")
            items.append(
                ListItem(
                    data=name,
                    label=name,
                    secondary=f"model: {model}",
                    prefix="⚙️",
                )
            )
        self.config_list.set_items(items)

    def _on_config_select(self, config_name: str) -> None:
        """Handle config selection."""
        self.selected_config_name = config_name
        self.error_message = None
        try:
            if self.environment:
                self.selected_config = self.environment.config_registry.get(
                    config_name
                )
                self._setup_params()
                # Always go to params step - shows launch button even without params
                self.step = self.STEP_SET_PARAMS
                # Start with launch button selected if no params
                if not self.param_names:
                    self.current_param_idx = 0  # Will be len(param_names) = 0
        except Exception as e:
            self.error_message = f"Error loading config: {e}"

    def _setup_params(self) -> None:
        """Initialize parameter input from the selected task."""
        self.param_names = []
        self.param_values = {}
        self.task_params = {}

        if not self.selected_task:
            return

        params = getattr(self.selected_task, "parameters", None)
        if not params:
            return

        self.task_params = params
        for param_name, param_spec in params.items():
            self.param_names.append(param_name)
            # Get default value
            if isinstance(param_spec, dict):
                default = param_spec.get("default", "")
            else:
                default = str(param_spec) if param_spec else ""
            self.param_values[param_name] = str(default)

        self.current_param_idx = 0
        self.editing_param = False

    def _get_param_info(self, param_name: str) -> Tuple[str, str, bool]:
        """Get info about a parameter (type, description, required)."""
        spec = self.task_params.get(param_name, {})
        if isinstance(spec, dict):
            param_type = spec.get("type", "string")
            description = spec.get("description", "")
            required = spec.get("required", False)
        else:
            param_type = "string"
            description = ""
            required = False
        return param_type, description, required

    def _launch_agent(self) -> None:
        """Launch the agent with selected configuration."""
        if (
            not self.environment
            or not self.selected_task
            or not self.selected_config
        ):
            self.error_message = "Missing configuration"
            return

        try:
            # Set task parameters
            params: Dict[str, Any] = {}
            for name in self.param_names:
                value = self.param_values.get(name, "")
                param_type, _, _ = self._get_param_info(name)
                # Convert to appropriate type
                if param_type == "integer":
                    try:
                        params[name] = int(value) if value else 0
                    except ValueError:
                        params[name] = value
                elif param_type == "number":
                    try:
                        params[name] = float(value) if value else 0.0
                    except ValueError:
                        params[name] = value
                elif param_type == "boolean":
                    params[name] = value.lower() in ("true", "yes", "1", "y")
                else:
                    params[name] = value

            self.selected_task = self.selected_task.set_input_parameters(params)

            # Create session and agent
            session = Session(environment=self.environment)
            session.create_agent_from_task(
                self.selected_config, self.selected_task
            )

            agent = session.agents[0]
            self.running_agent_id = agent.id
            self.step = self.STEP_RUNNING

            # Get controller for this agent
            controller = self.state.get_controller(agent.id)

            # Run agent in background thread
            def run_agent() -> None:
                # Set agent context for logging
                set_agent_context(agent.id, session.id)
                step_count = 0
                try:
                    while step_count < self.max_steps:
                        # Check controller before each step
                        if not controller.should_continue():
                            # Paused or waiting for step - sleep and retry
                            import time

                            time.sleep(0.1)
                            continue

                        # Take a step
                        if not agent.step():
                            break  # Agent completed

                        step_count += 1
                        self.state.storage.save_session(session)
                except Exception as e:
                    self.error_message = f"Agent error: {e}"
                finally:
                    clear_agent_context()
                    self.state.storage.save_session(session)
                    # Refresh state to show new agent
                    self.state.refresh_data()

            thread = threading.Thread(target=run_agent, daemon=True)
            thread.start()

        except Exception as e:
            self.error_message = f"Error launching agent: {e}"

    def get_title(self) -> str:
        """Return the screen title based on current step."""
        step_titles = {
            self.STEP_SELECT_DIR: "New Agent - Select Directory",
            self.STEP_SELECT_TASK: "New Agent - Select Task",
            self.STEP_SELECT_CONFIG: "New Agent - Select Config",
            self.STEP_SET_PARAMS: "New Agent - Set Parameters",
            self.STEP_CONFIRM: "New Agent - Confirm",
            self.STEP_RUNNING: "New Agent - Running",
        }
        return step_titles.get(self.step, "New Agent")

    def get_status_text(self) -> str:
        """Return status bar text based on current step."""
        if self.step == self.STEP_SET_PARAMS:
            if self.editing_param:
                return "Enter:Save  Esc:Cancel  Backspace:Delete"
            return "Enter:Edit  Tab:Next  Esc:Back"
        elif self.step == self.STEP_CONFIRM:
            return "Enter:Launch  Esc:Back"
        elif self.step == self.STEP_RUNNING:
            return "Press any key to go back to sessions"
        return "Enter:Select  Esc:Back"

    def render(self, stdscr: curses.window) -> None:
        """Render the wizard screen based on current step."""
        start_row, end_row, start_col, end_col = self.render_frame(stdscr)

        # Show error if any
        if self.error_message:
            try:
                stdscr.addstr(
                    start_row,
                    start_col,
                    f"Error: {self.error_message}",
                    curses.A_BOLD,
                )
            except curses.error:
                pass
            start_row += 2

        if self.step == self.STEP_SELECT_DIR:
            self._render_dir_selection(
                stdscr, start_row, end_row, start_col, end_col
            )
        elif self.step == self.STEP_SELECT_TASK:
            self._render_task_selection(
                stdscr, start_row, end_row, start_col, end_col
            )
        elif self.step == self.STEP_SELECT_CONFIG:
            self._render_config_selection(
                stdscr, start_row, end_row, start_col, end_col
            )
        elif self.step == self.STEP_SET_PARAMS:
            self._render_params(stdscr, start_row, end_row, start_col, end_col)
        elif self.step == self.STEP_CONFIRM:
            self._render_confirm(stdscr, start_row, end_row, start_col, end_col)
        elif self.step == self.STEP_RUNNING:
            self._render_running(stdscr, start_row, end_row, start_col, end_col)

    def _render_dir_selection(
        self,
        stdscr: curses.window,
        start_row: int,
        end_row: int,
        start_col: int,
        end_col: int,
    ) -> None:
        """Render directory selection step."""
        if not self.agent_dirs:
            try:
                stdscr.addstr(
                    start_row, start_col, "No agent directories found."
                )
                stdscr.addstr(
                    start_row + 1,
                    start_col,
                    "Agent directories need tasks/ or configs/ folders.",
                )
            except curses.error:
                pass
        else:
            self.dir_list.render(stdscr, start_row, end_row, start_col, end_col)

    def _render_task_selection(
        self,
        stdscr: curses.window,
        start_row: int,
        end_row: int,
        start_col: int,
        end_col: int,
    ) -> None:
        """Render task selection step."""
        if not self.tasks:
            try:
                stdscr.addstr(
                    start_row, start_col, "No tasks found in this directory."
                )
            except curses.error:
                pass
        else:
            self.task_list.render(
                stdscr, start_row, end_row, start_col, end_col
            )

    def _render_config_selection(
        self,
        stdscr: curses.window,
        start_row: int,
        end_row: int,
        start_col: int,
        end_col: int,
    ) -> None:
        """Render config selection step."""
        if not self.configs:
            try:
                stdscr.addstr(
                    start_row, start_col, "No configs found in this directory."
                )
            except curses.error:
                pass
        else:
            self.config_list.render(
                stdscr, start_row, end_row, start_col, end_col
            )

    def _render_params(
        self,
        stdscr: curses.window,
        start_row: int,
        end_row: int,
        start_col: int,
        end_col: int,
    ) -> None:
        """Render parameter input step."""
        width = end_col - start_col
        row = start_row

        try:
            # Show summary of what will be launched
            stdscr.addstr(row, start_col, "Ready to Launch:", curses.A_BOLD)
            row += 1
            stdscr.addstr(
                row,
                start_col,
                f"  Task:   {self.selected_task_name}",
                curses.A_DIM,
            )
            row += 1
            stdscr.addstr(
                row,
                start_col,
                f"  Config: {self.selected_config_name}",
                curses.A_DIM,
            )
            row += 2

            if self.param_names:
                stdscr.addstr(row, start_col, "Parameters:", curses.A_BOLD)
                row += 1

                for i, param_name in enumerate(self.param_names):
                    if row >= end_row - 4:  # Leave room for launch button
                        break

                    param_type, description, required = self._get_param_info(
                        param_name
                    )
                    value = self.param_values.get(param_name, "")

                    # Build display
                    is_current = (
                        i == self.current_param_idx and not self.editing_param
                    )
                    prefix = ">" if is_current else " "
                    req_mark = "*" if required else " "
                    type_str = f"({param_type})"

                    line1 = f"{prefix} {param_name}{req_mark} {type_str}"
                    if description:
                        line1 += f" - {description}"
                    line1 = line1[: width - 1]

                    # Show parameter name and description
                    attr = curses.A_BOLD if is_current else curses.A_NORMAL
                    stdscr.addstr(row, start_col, line1, attr)
                    row += 1

                    # Show value input
                    if i == self.current_param_idx and self.editing_param:
                        # Show editing cursor
                        display_value = self.param_input_buffer + "_"
                    else:
                        display_value = value if value else "(empty)"

                    value_line = f"    Value: {display_value}"
                    value_line = value_line[: width - 1]
                    stdscr.addstr(row, start_col, value_line)
                    row += 2
            else:
                stdscr.addstr(
                    row, start_col, "(No parameters required)", curses.A_DIM
                )
                row += 2

            # Launch button at the bottom
            row += 1
            is_launch_selected = (
                self.current_param_idx == len(self.param_names)
                and not self.editing_param
            )
            launch_prefix = ">" if is_launch_selected else " "
            launch_text = f"{launch_prefix} [ Launch Agent ]"
            launch_attr = (
                curses.A_BOLD | curses.A_REVERSE
                if is_launch_selected
                else curses.A_NORMAL
            )
            stdscr.addstr(row, start_col, launch_text, launch_attr)

            # Navigation hint
            row += 2
            if row < end_row:
                if self.editing_param:
                    hint = "Type value, Enter to save, Esc to cancel"
                elif is_launch_selected:
                    hint = "Press Enter to launch the agent"
                elif self.param_names:
                    hint = "Enter:Edit  ↑↓:Navigate  Tab:Next"
                else:
                    hint = "Press Enter to launch"
                stdscr.addstr(row, start_col, hint, curses.A_DIM)

        except curses.error:
            pass

    def _render_confirm(
        self,
        stdscr: curses.window,
        start_row: int,
        end_row: int,
        start_col: int,
        end_col: int,
    ) -> None:
        """Render confirmation step."""
        row = start_row
        width = end_col - start_col

        try:
            stdscr.addstr(
                row, start_col, "Ready to Launch Agent", curses.A_BOLD
            )
            row += 2

            stdscr.addstr(row, start_col, f"Directory: {self.selected_dir}")
            row += 1
            stdscr.addstr(
                row, start_col, f"Task:      {self.selected_task_name}"
            )
            row += 1
            stdscr.addstr(
                row, start_col, f"Config:    {self.selected_config_name}"
            )
            row += 1

            if self.selected_config:
                model = getattr(self.selected_config, "llm_model", "unknown")
                stdscr.addstr(row, start_col, f"Model:     {model}")
                row += 1

            stdscr.addstr(row, start_col, f"Max steps: {self.max_steps}")
            row += 2

            if self.param_names:
                stdscr.addstr(row, start_col, "Parameters:", curses.A_BOLD)
                row += 1
                for name in self.param_names:
                    value = self.param_values.get(name, "")
                    line = f"  {name}: {value}"[: width - 1]
                    stdscr.addstr(row, start_col, line)
                    row += 1

            row += 1
            stdscr.addstr(
                row, start_col, "Press Enter to launch the agent", curses.A_DIM
            )

        except curses.error:
            pass

    def _render_running(
        self,
        stdscr: curses.window,
        start_row: int,
        end_row: int,
        start_col: int,
        end_col: int,
    ) -> None:
        """Render running state."""
        row = start_row

        try:
            stdscr.addstr(row, start_col, "Agent Running", curses.A_BOLD)
            row += 2

            if self.running_agent_id:
                stdscr.addstr(
                    row, start_col, f"Agent ID: {self.running_agent_id}"
                )
                row += 1

                # Find agent in state and show interaction count
                for agent in self.state.agents:
                    if agent.id == self.running_agent_id:
                        stdscr.addstr(
                            row,
                            start_col,
                            f"Interactions: {agent.num_interactions}",
                        )
                        if agent.is_running:
                            stdscr.addstr(
                                row + 1,
                                start_col,
                                "Status: Running...",
                                curses.A_DIM,
                            )
                        else:
                            stdscr.addstr(
                                row + 1,
                                start_col,
                                "Status: Completed",
                                curses.A_BOLD,
                            )
                        break
                row += 3

            stdscr.addstr(
                row,
                start_col,
                "Press any key to go back to sessions",
                curses.A_DIM,
            )

        except curses.error:
            pass

    def handle_input(self, key: int) -> Optional[str]:
        """Handle keyboard input based on current wizard step."""
        height, _ = self.app.get_size()
        visible_height = height - 2

        # Handle parameter editing mode
        if self.step == self.STEP_SET_PARAMS and self.editing_param:
            return self._handle_param_edit(key)

        # Handle list navigation for selection steps
        if self.step == self.STEP_SELECT_DIR:
            result = self.dir_list.handle_input(key, visible_height)
            if result in ("select", "navigate"):
                return "refresh"
        elif self.step == self.STEP_SELECT_TASK:
            result = self.task_list.handle_input(key, visible_height)
            if result in ("select", "navigate"):
                return "refresh"
        elif self.step == self.STEP_SELECT_CONFIG:
            result = self.config_list.handle_input(key, visible_height)
            if result in ("select", "navigate"):
                return "refresh"
        elif self.step == self.STEP_SET_PARAMS:
            return self._handle_params_navigation(key)
        elif self.step == self.STEP_CONFIRM:
            if key in (curses.KEY_ENTER, 10, 13):
                self._launch_agent()
                return "refresh"
        elif self.step == self.STEP_RUNNING:
            # Any key goes back to sessions
            return "pop"

        return "refresh"

    def _handle_params_navigation(self, key: int) -> Optional[str]:
        """Handle navigation in parameter editing step."""
        # Total items = parameters + launch button
        max_idx = len(
            self.param_names
        )  # Launch button is at index len(param_names)

        if key in (curses.KEY_UP, ord("k"), ord("K")):
            if self.current_param_idx > 0:
                self.current_param_idx -= 1
            return "refresh"
        elif key in (curses.KEY_DOWN, ord("j"), ord("J")):
            if self.current_param_idx < max_idx:
                self.current_param_idx += 1
            return "refresh"
        elif key == ord("\t"):  # Tab
            if self.current_param_idx < max_idx:
                self.current_param_idx += 1
            return "refresh"
        elif key in (curses.KEY_ENTER, 10, 13):
            if self.current_param_idx == max_idx:
                # Launch button selected - launch the agent
                self._launch_agent()
                return "refresh"
            else:
                # Start editing current parameter
                self.editing_param = True
                param_name = self.param_names[self.current_param_idx]
                self.param_input_buffer = self.param_values.get(param_name, "")
                return "refresh"

        return None

    def _handle_param_edit(self, key: int) -> Optional[str]:
        """Handle keyboard input while editing a parameter."""
        if key == 27:  # Escape - cancel editing
            self.editing_param = False
            return "refresh"
        elif key == curses.KEY_ENTER or key == 10 or key == 13:
            # Save and stop editing
            param_name = self.param_names[self.current_param_idx]
            self.param_values[param_name] = self.param_input_buffer
            self.editing_param = False
            return "refresh"
        elif key == curses.KEY_BACKSPACE or key == 127 or key == 8:
            # Delete character
            if self.param_input_buffer:
                self.param_input_buffer = self.param_input_buffer[:-1]
            return "refresh"
        elif 32 <= key <= 126:  # Printable ASCII
            self.param_input_buffer += chr(key)
            return "refresh"

        return "refresh"
