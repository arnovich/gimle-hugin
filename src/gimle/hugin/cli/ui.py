"""Shared CLI UI helpers for Hugin commands.

Keep this module lightweight: it should not import agent/runtime code so it can
be safely imported by all CLI entrypoints without pulling heavy dependencies.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

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


def run_steps_with_spinner(
    *,
    step_fn: Callable[[], bool],
    save_fn: Callable[[], None],
    max_steps: Optional[int],
    prefix: str = "",
    clear_width: int = 40,
    spinner: Optional[Sequence[str]] = None,
    session: Optional[Any] = None,
    interactive: bool = True,
) -> Tuple[int, Optional[Exception]]:
    """Run a step loop with a simple terminal spinner.

    Args:
        step_fn: Function to call for each step, returns True to continue
        save_fn: Function to save state after each step
        max_steps: Maximum number of steps to run (None for unlimited)
        prefix: Prefix string for output
        clear_width: Width to clear when done
        spinner: Optional custom spinner characters
        session: Optional Session object for detecting AskHuman interactions
        interactive: Whether to prompt for human input (default True)

    Returns:
        (step_count, last_error)
    """
    if spinner is None:
        spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    step_count = 0
    last_error: Optional[Exception] = None

    while max_steps is None or step_count < max_steps:
        try:
            if not step_fn():
                # Check if we stopped due to AskHuman
                if session and interactive:
                    ask_human = _find_pending_ask_human(session)
                    if ask_human:
                        # Clear spinner line before prompting
                        print("\r" + " " * clear_width + "\r", end="")
                        _handle_ask_human(ask_human, prefix)
                        save_fn()
                        continue  # Continue stepping after human response
                break
            step_count += 1
            spin_char = spinner[step_count % len(spinner)]
            print(
                f"\r{prefix}{spin_char} Step {step_count}...",
                end="",
                flush=True,
            )
            save_fn()
        except Exception as e:
            last_error = e
            break

    # Clear the spinner line
    print("\r" + " " * clear_width + "\r", end="")
    return step_count, last_error


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


def _handle_ask_human(ask_human_tuple: tuple, prefix: str = "") -> None:
    """Handle an AskHuman interaction by prompting the user.

    Args:
        ask_human_tuple: Tuple of (agent, AskHuman interaction)
        prefix: Prefix for output formatting
    """
    # Import here to avoid circular imports
    from gimle.hugin.interaction.human_response import HumanResponse

    agent, ask_human = ask_human_tuple

    # Display the question
    print()
    print(f"{prefix}┌─────────────────────────────────────────┐")
    print(f"{prefix}│  Agent is asking for human input        │")
    print(f"{prefix}└─────────────────────────────────────────┘")
    print()

    if ask_human.question:
        # Word wrap long questions
        question = ask_human.question
        print(f"{prefix}Question: {question}")
    else:
        print(f"{prefix}The agent is waiting for input.")

    print()
    response = prompt_user(f"{prefix}Your response")

    # Add HumanResponse to the agent's stack
    human_response = HumanResponse(
        stack=agent.stack, response=response, branch=ask_human.branch
    )
    agent.stack.add_interaction(human_response)

    print()
    print(f"{prefix}Response recorded. Continuing...")
    print()
