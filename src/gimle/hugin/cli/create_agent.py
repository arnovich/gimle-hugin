#!/usr/bin/env python3
"""Interactive wizard for creating new Hugin agents."""

import argparse
import logging
import re
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.cli.ui import (
    clear_screen,
    prompt_user,
    prompt_yes_no,
    run_steps_with_spinner,
)
from gimle.hugin.llm.models.provider_utils import (
    ProviderStatus,
    check_anthropic,
    check_ollama,
    check_openai,
    ensure_credentials_loaded,
)
from gimle.hugin.storage.local import LocalStorage

# ANSI color codes (used by show_header and _build_banner)
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
YELLOW = "\033[33m"
WHITE = "\033[97m"
GRAY = "\033[90m"
RESET = "\033[0m"


def _build_banner() -> str:
    """Build the banner with the current version number."""
    from gimle.hugin import __version__

    # fmt: off
    return (
        f"{CYAN}{BOLD}\n"
        f"    ██╗  ██╗██╗   ██╗ ██████╗ ██╗███╗   ██╗\n"
        f"    ██║  ██║██║   ██║██╔════╝ ██║████╗  ██║\n"
        f"    ███████║██║   ██║██║  ███╗██║██╔██╗ ██║\n"
        f"    ██╔══██║██║   ██║██║   ██║██║██║╚██╗██║\n"
        f"    ██║  ██║╚██████╔╝╚██████╔╝██║██║ ╚████║\n"
        f"    ╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═╝╚═╝  ╚═══╝{RESET}\n"
        f"{MAGENTA}    ─────────────────────────────────────────{RESET}\n"
        f"{WHITE}{BOLD}           ⚡ A G E N T   B U I L D E R ⚡{RESET}\n"
        f"{MAGENTA}    ─────────────────────────────────────────{RESET}\n"
        f"{DIM}        Create intelligent agents with ease\n"
        f"        v{__version__}{RESET}\n"
    )
    # fmt: on


def show_header(step: str = "", subtitle: str = "") -> None:
    """Display the banner header with optional step indicator."""
    clear_screen()
    print(_build_banner())
    if step:
        print(f"    {YELLOW}{BOLD}{step}{RESET}")
        if subtitle:
            print(f"    {DIM}{subtitle}{RESET}")
        print()


def to_snake_case(name: str) -> str:
    """Convert a string to snake_case."""
    name = re.sub(r"[\s\-]+", "_", name)
    name = re.sub(r"([a-z])([A-Z])", r"\1_\2", name)
    name = name.lower()
    name = re.sub(r"[^a-z0-9_]", "", name)
    name = re.sub(r"_+", "_", name)
    name = name.strip("_")
    return name


def select_provider() -> Tuple[str, ProviderStatus]:
    """Let user select LLM provider."""
    show_header(
        "Step 1 of 4: Select LLM Provider",
        "Choose which AI provider to use for building your agent",
    )

    all_providers = [
        ("1", "ollama", check_ollama()),
        ("2", "anthropic", check_anthropic()),
        ("3", "openai", check_openai()),
    ]

    # Split into available and unavailable, preserving order
    available_providers: Dict[str, Tuple[str, ProviderStatus]] = {}
    unavailable_providers: list = []
    for num, name, status in all_providers:
        if status.available:
            available_providers[num] = (name, status)
        else:
            unavailable_providers.append((num, name, status))

    # Find first available provider for default
    default_choice = ""
    for num in available_providers:
        default_choice = num
        break

    # Show available providers first
    for num, (name, status) in available_providers.items():
        print(f"    {num}. {status.name}")
        if status.credential_source == "local":
            print("            Running locally")
        elif status.credential_source:
            print(f"            API key found ({status.credential_source})")
            if status.api_key:
                print(f"            Key: {status.api_key}")
        print()

    # Show unavailable providers grayed out
    if unavailable_providers:
        for num, name, status in unavailable_providers:
            print(f"    {GRAY}{num}. {status.name}")
            print(f"            {status.error}{RESET}")
            print()

    if not available_providers:
        print("    No providers available.")
        print("    Please install Ollama or set an API key.")
        sys.exit(1)

    choice = prompt_user("    Select provider", default_choice)
    while choice not in available_providers:
        if any(num == choice for num, _, _ in unavailable_providers):
            match = next(s for n, _, s in unavailable_providers if n == choice)
            print(f"    {match.name} is not available: {match.error}")
        else:
            valid = ", ".join(available_providers.keys())
            print(f"    Invalid choice. Please enter {valid}.")
        choice = prompt_user("    Select provider", default_choice)

    provider_name, status = available_providers[choice]
    return provider_name, status


def select_model(provider: str, status: ProviderStatus) -> str:
    """Let user select specific model for provider."""
    show_header(
        "Step 2 of 4: Select Model",
        f"Choose which {status.name} model to use",
    )

    # Get available models for provider
    if provider == "ollama":
        # Show installed models from Ollama
        models = status.models
        if not models or models == ["(no models installed)"]:
            print("    No Ollama models installed.")
            print("    You can install models with: ollama pull <model>")
            print("    Recommended: ollama pull qwen3:8b")
            print()
            custom = prompt_user("    Enter model name to use", "qwen3:8b")
            return custom
    elif provider == "anthropic":
        models = ["sonnet-latest", "haiku-latest", "opus-latest"]
    elif provider == "openai":
        models = ["gpt-4o", "gpt-4o-mini"]
    else:
        models = []

    if not models:
        return prompt_user("    Enter model name")

    print(f"    Available {status.name} models:\n")
    for i, model in enumerate(models, 1):
        print(f"        {i}. {model}")
    print()

    # Default to first model
    default = "1"
    choice = prompt_user("    Select model", default)

    # Handle numeric choice or direct model name
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(models):
            return models[idx]
    except ValueError:
        pass

    # If not a valid number, treat as model name
    return choice


def verify_credentials(provider: str, status: ProviderStatus) -> bool:
    """Verify and confirm credentials."""
    show_header(
        "Step 3 of 4: Verify Setup",
        "Confirm your credentials and configuration",
    )

    if provider == "ollama":
        if status.available:
            print("    Ollama is running locally.")
            print(f"    Installed models: {', '.join(status.models[:5])}")
            if len(status.models) > 5:
                print(f"        ... and {len(status.models) - 5} more")
            print()
            input("    Press Enter to continue...")
            return True
        else:
            print(f"    {status.error}")
            return prompt_yes_no("    Continue anyway?", default=False)

    # For cloud providers
    if status.available:
        print(f"    {status.name} API key found!")
        print(f"    Source: {status.credential_source}")
        if status.api_key:
            print(f"    Key: {status.api_key}")
        print()
        if prompt_yes_no("    Use this API key?", default=True):
            # Ensure credentials are loaded into environment
            ensure_credentials_loaded(provider)
            return True
        return False
    else:
        print(f"    {status.error}")
        print()
        print("    You can set the API key by:")
        print(
            f"      - Setting {provider.upper()}_API_KEY environment variable"
        )
        print("      - Adding it to a .env file in current directory")
        return prompt_yes_no("\n    Continue anyway?", default=False)


def run_wizard(builder_model: Optional[str] = None) -> Dict[str, Any]:
    """Run the interactive wizard and collect user input."""
    # Step 1-3: Provider and model selection (for the builder itself)
    if not builder_model:
        provider, status = select_provider()
        model = select_model(provider, status)
        if not verify_credentials(provider, status):
            print("    Cancelled.")
            sys.exit(0)
        builder_model = model

    show_header(
        "Step 4 of 4: Define Your Agent",
        "Tell us about the agent you want to create",
    )

    # Agent name
    raw_name = prompt_user("    Agent name")
    while not raw_name:
        print("    Please enter a name for the agent")
        raw_name = prompt_user("    Agent name")

    agent_name = to_snake_case(raw_name)
    if agent_name != raw_name:
        print(f"        -> Converted to: {agent_name}")

    # Description
    print()
    print("    Describe what this agent should do:")
    print("    (Be as detailed as you like - what tasks, goals, behaviors?)")
    print()
    description = prompt_user("    Description")

    # LLM Model for the generated agent (not the builder)
    print()
    print("    What LLM should the generated agent use?")
    llm_model = prompt_user("    LLM model for the agent", "haiku-latest")

    # Tool implementation style
    print()
    full_implementation = prompt_yes_no(
        "    Generate full tool implementations? (No = stubs only)",
        default=True,
    )

    # Output path
    print()
    output_path = prompt_user(
        "    Output directory path", f"./agents/{agent_name}"
    )

    # Confirmation screen
    show_header("Ready to Build", "Review your configuration")

    impl_style = "Full implementation" if full_implementation else "Stubs only"
    print("    ┌─────────────────────────────────────────┐")
    print("    │        Configuration Summary            │")
    print("    └─────────────────────────────────────────┘")
    print()
    print(f"        Name:        {agent_name}")
    print(f"        Agent LLM:   {llm_model}")
    print(f"        Tool style:  {impl_style}")
    print(f"        Output:      {output_path}")
    print(f"        Builder LLM: {builder_model}")
    print()
    print("        Description:")
    # Word wrap description at ~55 chars
    wrapped = textwrap.wrap(description, width=55)
    for line in wrapped:
        print(f"          {line}")
    print()

    if not prompt_yes_no("    Proceed with agent creation?"):
        print("    Cancelled.")
        sys.exit(0)

    return {
        "agent_name": agent_name,
        "description": description,
        "llm_model": llm_model,
        "full_implementation": full_implementation,
        "output_path": str(Path(output_path).resolve()),
        "builder_model": builder_model,
    }


def setup_file_logging(log_dir: Path, log_level: str) -> Path:
    """Configure logging to write to a file instead of stdout.

    Returns the path to the log file.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "builder.log"

    # Remove any existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Configure file handler only
    file_handler = logging.FileHandler(log_file, mode="w")
    file_handler.setLevel(getattr(logging, log_level))
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root_logger.addHandler(file_handler)
    root_logger.setLevel(getattr(logging, log_level))

    return log_file


def main() -> int:
    """Run the agent builder wizard."""
    parser = argparse.ArgumentParser(
        description="Interactive wizard for creating new Hugin agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run the interactive wizard
  uv run create-agent

  # Run with more steps allowed for complex agents
  uv run create-agent --max-steps 50

  # Run with debug logging (writes to ./storage/agent_builder/builder.log)
  uv run create-agent --log-level DEBUG
        """,
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=200,
        help="Maximum steps for the builder agent (default: 200)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="WARNING",
        help="Logging level for log file (default: WARNING)",
    )
    args = parser.parse_args()

    # Run wizard
    user_input = run_wizard()

    # Set up storage path
    storage_path = Path("./storage/agent_builder")

    # Configure logging to file (not stdout)
    log_file = setup_file_logging(storage_path, args.log_level)

    # Show building screen
    show_header(
        "Building Your Agent", "Please wait while the AI creates your agent..."
    )
    print("  To monitor progress, run:")
    print(f"    uv run hugin monitor -s {storage_path}\n")

    # Find agent_builder app path
    builder_path = None

    # Try the package location first (works for both dev and installed)
    try:
        from gimle.hugin.apps import get_apps_path

        apps_path = get_apps_path()
        candidate = apps_path / "agent_builder"
        if candidate.exists():
            builder_path = candidate
    except ImportError:
        pass

    # Fallback: Try relative to this script (development with old apps/ location)
    if not builder_path:
        script_dir = Path(__file__).parent
        project_root = script_dir.parent.parent.parent.parent
        candidate = project_root / "apps" / "agent_builder"
        if candidate.exists():
            builder_path = candidate

    if not builder_path:
        print("    Error: Could not find agent_builder app.")
        print("    Make sure the package is installed correctly.")
        return 1

    # Set up storage
    storage = LocalStorage(base_path=str(storage_path))

    try:
        # Load agent_builder environment with user input
        env = Environment.load(
            str(builder_path),
            storage=storage,
            env_vars={"user_input": user_input},
        )

        # Get config and task
        config = env.config_registry.get("agent_builder")
        task = env.task_registry.get("build_agent")

        # Override the builder's model with user's selection
        builder_model = user_input.get("builder_model", "sonnet-latest")
        config.llm_model = builder_model

        # Inject user input as task parameters
        task = task.set_input_parameters(user_input)

        # Create and run session
        session = Session(environment=env)
        session.create_agent_from_task(config, task)

        agent = session.agents[0]
        print(f"    Builder agent: {agent.id}")
        print(f"    Using model:   {builder_model}")
        print(f"    Log file:      {log_file}")
        print()

        step_count, last_error = run_steps_with_spinner(
            step_fn=agent.step,
            save_fn=lambda: storage.save_session(session),
            max_steps=args.max_steps,
            prefix="    ",
            clear_width=40,
        )
        if last_error:
            logging.error("Error during agent step", exc_info=last_error)

        # Final save
        storage.save_session(session)

        if last_error:
            print()
            print("    ┌─────────────────────────────────────────┐")
            print("    │              Build Error                │")
            print("    └─────────────────────────────────────────┘")
            print()
            print(f"    Error: {type(last_error).__name__}")
            print(f"    {str(last_error)[:60]}")
            print()
            print(f"    See full details in: {log_file}")
            print(f"    Monitor session with: hugin monitor -s {storage_path}")
            print()
            return 1

        if step_count >= args.max_steps:
            print(f"    Error: Reached maximum steps ({args.max_steps})")
            print("    The agent may not have finished building.")
            print(f"    Monitor session: hugin monitor -s {storage_path}")
            return 1

    except Exception as e:
        logging.exception("Error setting up agent builder")
        print()
        print("    ┌─────────────────────────────────────────┐")
        print("    │           Setup Error                   │")
        print("    └─────────────────────────────────────────┘")
        print()
        print(f"    Error: {type(e).__name__}")
        print(f"    {str(e)[:60]}")
        print()
        print(f"    See full details in: {log_file}")
        print()
        return 1

    # Success screen
    show_header("Agent Created Successfully!", "Your agent is ready to use")

    print("    ┌─────────────────────────────────────────┐")
    print("    │            Agent Details                │")
    print("    └─────────────────────────────────────────┘")
    print()
    print(f"        Location: {user_input['output_path']}")
    print()
    print("    Run your new agent with:")
    print()
    print(f"        hugin run -p {user_input['output_path']}")
    print()

    # Ask if user wants to run the agent now
    if prompt_yes_no("    Run your new agent now?", default=True):
        print()
        print("    Starting agent runner...")
        print()

        # Import and call run_interactive from run_agent
        from gimle.hugin.cli.run_agent import run_interactive

        # Create a minimal args namespace with the output path
        run_args = argparse.Namespace(
            task_path=user_input["output_path"],
            task=None,
            config=None,
            model=None,
            max_steps=None,
            storage_path=None,
            log_level="WARNING",
            parameters=None,
        )

        return run_interactive(run_args, skip_confirmation=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
