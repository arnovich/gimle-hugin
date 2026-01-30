"""Shared CLI UI helpers for Hugin commands.

Keep this module lightweight: it should not import agent/runtime code so it can
be safely imported by all CLI entrypoints without pulling heavy dependencies.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


# ANSI color codes for terminal output
class Colors:
    """ANSI color codes for terminal styling."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"

    # Bright foreground
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_WHITE = "\033[97m"

    @classmethod
    def enabled(cls) -> bool:
        """Check if terminal colors should be used.

        Colors are enabled by default. Set NO_COLOR=1 to disable.
        """
        return not os.environ.get("NO_COLOR")


HUGIN_LOGO = r"""
    HH   HH  UU   UU  GGGGGG   IIIII  NN   NN
    HH   HH  UU   UU  GG        III   NNN  NN
    HHHHHHH  UU   UU  GG GGG    III   NN N NN
    HH   HH  UU   UU  GG  GG    III   NN  NNN
    HH   HH   UUUUU    GGGGG   IIIII  NN   NN
"""


def make_boxed_banner(
    title: str,
    subtitle_lines: Optional[List[str]] = None,
    *,
    min_inner_width: int = 47,
) -> str:
    """Create a banner that includes the HUGIN logo and a boxed title section."""
    subtitle_lines = subtitle_lines or []
    # Inner width excludes the box borders. Keep at least min_inner_width.
    inner_width = max(
        min_inner_width,
        len(title),
        *(len(line) for line in subtitle_lines),
    )

    def box_line(text: str = "") -> str:
        return f"    │ {text.ljust(inner_width)} │"

    top = f"    ┌{'─' * (inner_width + 2)}┐"
    bottom = f"    └{'─' * (inner_width + 2)}┘"

    lines = [
        HUGIN_LOGO.rstrip("\n"),
        top,
        box_line(title),
        box_line(""),
        *(box_line(line) for line in subtitle_lines),
        bottom,
        "",
    ]
    return "\n".join(lines)


def clear_screen() -> None:
    """Clear the terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def show_header(banner: str, step: str = "", subtitle: str = "") -> None:
    """Display the banner header with optional step indicator."""
    clear_screen()
    print(banner)
    if step:
        print(f"    {step}")
        if subtitle:
            print(f"    {subtitle}")
        print()


def prompt_user(question: str, default: str = "") -> str:
    """Prompt user for input with optional default."""
    if default:
        user_input = input(f"{question} [{default}]: ").strip()
        return user_input if user_input else default
    return input(f"{question}: ").strip()


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Prompt user for yes/no answer."""
    default_str = "Y/n" if default else "y/N"
    answer = input(f"{question} [{default_str}]: ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def select_from_list(
    items: List[str],
    prompt_text: str,
    show_descriptions: Optional[Dict[str, str]] = None,
) -> str:
    """Let user select from a list of items."""
    for i, item in enumerate(items, 1):
        if show_descriptions and item in show_descriptions:
            print(f"        {i}. {item}")
            print(f"           {show_descriptions[item]}")
        else:
            print(f"        {i}. {item}")

    print()
    choice = prompt_user(prompt_text, "1")

    # Handle numeric choice
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(items):
            return items[idx]
    except ValueError:
        pass

    # If not a valid number, treat as direct name
    if choice in items:
        return choice

    # Default to first item
    return items[0]


class AnimatedSpinner:
    """A spinner that animates in a background thread."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(
        self,
        prefix: str = "",
        status: str = "Thinking...",
        clear_width: int = 60,
    ):
        """Initialize the animated spinner.

        Args:
            prefix: Prefix string to show before the spinner
            status: Initial status message
            clear_width: Width to use when clearing the line
        """
        self.prefix = prefix
        self.status = status
        self.clear_width = clear_width
        self.step_count = 0
        self.start_time = time.time()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._frame_index = 0

    def _format_elapsed(self) -> str:
        """Format elapsed time as seconds."""
        elapsed = int(time.time() - self.start_time)
        return f"{elapsed}s"

    def _render(self) -> None:
        """Render the current spinner state."""
        with self._lock:
            frame = self.FRAMES[self._frame_index % len(self.FRAMES)]
            elapsed = self._format_elapsed()
            line = f"\r{self.prefix}{frame} {self.status} ({elapsed})"
            # Pad to clear width and move cursor back
            line = line.ljust(self.clear_width)
            print(line, end="", flush=True)

    def _spin_loop(self) -> None:
        """Background thread loop for animation."""
        while self._running:
            self._render()
            self._frame_index += 1
            time.sleep(0.1)

    def start(self) -> None:
        """Start the spinner animation."""
        self._running = True
        self.start_time = time.time()
        self._thread = threading.Thread(target=self._spin_loop, daemon=True)
        self._thread.start()

    def stop(self, show_completed: bool = False) -> None:
        """Stop the spinner.

        Args:
            show_completed: If True, show "Completed (Xs)" instead of clearing
        """
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)

        if show_completed:
            elapsed = self._format_elapsed()
            use_color = Colors.enabled()
            dim = Colors.DIM if use_color else ""
            reset = Colors.RESET if use_color else ""
            # Show completed message and move to new line
            line = f"\r{dim}{self.prefix}Completed ({elapsed}){reset}"
            print(line.ljust(self.clear_width))
        else:
            # Just clear the line
            print("\r" + " " * self.clear_width + "\r", end="", flush=True)

    def update_status(self, status: str) -> None:
        """Update the status message."""
        with self._lock:
            self.status = status

    def increment_step(self) -> None:
        """Increment the step counter."""
        with self._lock:
            self.step_count += 1


def run_steps_with_spinner(
    *,
    step_fn: Callable[[], bool],
    save_fn: Callable[[], None],
    max_steps: Optional[int],
    prefix: str = "",
    user_prefix: str = "👤 ",
    status_message: str = "Thinking...",
    clear_width: int = 60,
    spinner: Optional[Sequence[str]] = None,
    session: Optional[Any] = None,
    interactive: bool = True,
) -> Tuple[int, Optional[Exception]]:
    """Run a step loop with a smoothly animated spinner.

    Args:
        step_fn: Function to call for each step, returns True to continue
        save_fn: Function to save state after each step
        max_steps: Maximum number of steps to run (None for unlimited)
        prefix: Prefix string for agent output (e.g., "🐣 ")
        user_prefix: Prefix string for user input (e.g., "👤 ")
        status_message: Base status message to show
        clear_width: Width to clear when done
        spinner: Deprecated, uses AnimatedSpinner frames
        session: Optional Session object for detecting AskHuman interactions
        interactive: Whether to prompt for human input (default True)

    Returns:
        (step_count, last_error)
    """
    animated = AnimatedSpinner(
        prefix=prefix,
        status=status_message,
        clear_width=clear_width,
    )
    animated.start()

    step_count = 0
    last_error: Optional[Exception] = None

    try:
        while max_steps is None or step_count < max_steps:
            try:
                # Update status based on session state
                if session:
                    status = _get_session_status(session, status_message)
                    animated.update_status(status)

                if not step_fn():
                    # Check if we stopped due to AskHuman
                    if session and interactive:
                        ask_human = _find_pending_ask_human(session)
                        if ask_human:
                            # Stop spinner with completion message
                            animated.stop(show_completed=True)
                            _handle_ask_human(ask_human, prefix, user_prefix)
                            save_fn()
                            # Restart spinner for next round
                            animated = AnimatedSpinner(
                                prefix=prefix,
                                status=status_message,
                                clear_width=clear_width,
                            )
                            animated.start()
                            continue  # Continue stepping after human response
                    break
                step_count += 1
                animated.increment_step()
                save_fn()
            except Exception as e:
                last_error = e
                break
    finally:
        animated.stop(show_completed=True)

    return step_count, last_error


def _get_session_status(session: Any, default: str) -> str:
    """Get a status message based on what the session is doing."""
    # Import here to avoid circular imports
    from gimle.hugin.interaction.agent_call import AgentCall
    from gimle.hugin.interaction.waiting import Waiting

    for agent in session.agents:
        interactions = agent.stack.interactions
        if not interactions:
            continue
        last = interactions[-1]
        # Check if waiting for a sub-agent
        if isinstance(last, Waiting) and len(interactions) >= 2:
            prev = interactions[-2]
            if isinstance(prev, AgentCall) and prev.config:
                config_name = prev.config.name
                # Clean up builtin prefix for display
                if config_name.startswith("builtins."):
                    config_name = config_name.replace("builtins.", "")
                return f"Running {config_name}..."
    return default


def _find_pending_ask_human(session: Any) -> Optional[Any]:
    """Find a pending AskHuman interaction in the session.

    Returns the (agent, AskHuman) tuple if found, None otherwise.
    """
    # Import here to avoid circular imports
    from gimle.hugin.interaction.ask_human import AskHuman

    for agent in session.agents:
        if agent.stack.interactions:
            last_interaction = agent.stack.interactions[-1]
            if isinstance(last_interaction, AskHuman):
                return (agent, last_interaction)
    return None


def _handle_ask_human(
    ask_human_tuple: tuple,
    prefix: str = "",
    user_prefix: str = "👤 ",
) -> None:
    """Handle an AskHuman interaction by prompting the user.

    Args:
        ask_human_tuple: Tuple of (agent, AskHuman interaction)
        prefix: Prefix for agent output (e.g., "🐣 " for BabyHugin)
        user_prefix: Prefix for user input (default: "👤 ")
    """
    # Import here to avoid circular imports
    from gimle.hugin.interaction.human_response import HumanResponse

    agent, ask_human = ask_human_tuple

    # Color setup - high contrast between agent (bold green) and user (dim gray)
    use_color = Colors.enabled()
    agent_style = f"{Colors.BOLD}{Colors.BRIGHT_GREEN}" if use_color else ""
    user_style = f"{Colors.DIM}{Colors.WHITE}" if use_color else ""
    reset = Colors.RESET if use_color else ""

    # Display the question (agent output in bold green with agent prefix)
    print()
    if ask_human.question:
        print(f"{agent_style}{prefix}{ask_human.question}{reset}")
    else:
        print(f"{agent_style}{prefix}Waiting for input...{reset}")

    print()
    # User input prompt in dim style with user prefix
    response = input(f"{user_style}{user_prefix}{reset}").strip()

    # Add HumanResponse to the agent's stack
    human_response = HumanResponse(
        stack=agent.stack, response=response, branch=ask_human.branch
    )
    agent.stack.add_interaction(human_response)

    print()
