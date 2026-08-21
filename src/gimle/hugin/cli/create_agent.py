#!/usr/bin/env python3
"""Interactive wizard for creating new Hugin agents."""

import argparse
import logging
import os
import re
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Establish builtin tool registration before Environment imports the
# interaction package. Starting from Environment in a fresh CLI process enters
# the inverse import order and leaves AgentCall partially initialised.
import gimle.hugin.tools  # noqa: F401
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


# A directory holding any of these is an agent; the builder writes all
# four, and a hand-written agent has at least one.
AGENT_SUBDIRECTORIES = ("configs", "tasks", "templates", "tools")


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


def _registry_models(provider: str) -> list:
    """Return the registered model names for a provider, newest names first."""
    try:
        from gimle.hugin.llm.models.model_registry import get_model_registry

        names = get_model_registry().get_models_by_provider(provider)
    except Exception:  # noqa: BLE001 - fall back rather than block the wizard
        return []
    return sorted(names, key=lambda n: (not n.endswith("latest"), n))


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
    elif provider in ("anthropic", "openai"):
        # Read from the registry rather than restating it here. The hardcoded
        # lists went stale the moment a model was added, and the docs restated
        # them a third time.
        models = _registry_models(provider)
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


def _supplied(args: argparse.Namespace) -> Dict[str, str]:
    """Return the non-empty command-line values, keyed by field."""
    fields = (
        "name",
        "description",
        "model",
        "builder_model",
        "output",
    )
    return {
        field: getattr(args, field)
        for field in fields
        if getattr(args, field, None)
    }


def run_wizard(
    builder_model: Optional[str] = None,
    args: Optional[argparse.Namespace] = None,
) -> Dict[str, Any]:
    """Collect the build inputs, prompting only for what was not supplied.

    Every field can now arrive as a flag, so ``hugin create --yes`` runs
    unattended -- which is what makes the wizard scriptable and testable at
    all. It previously demanded four screens of provider and credential
    selection before it would even ask what to build.
    """
    args = args or argparse.Namespace()
    supplied = _supplied(args)
    non_interactive = bool(getattr(args, "yes", False))
    dry_run = bool(getattr(args, "dry_run", False))

    if non_interactive and not (
        supplied.get("name") and supplied.get("description")
    ):
        print("    --yes requires --name and --description.")
        sys.exit(2)

    if supplied.get("builder_model"):
        builder_model = supplied["builder_model"]

    # Step 1-3: Provider and model selection (for the builder itself)
    if not builder_model and not non_interactive:
        provider, status = select_provider()
        model = select_model(provider, status)
        if not verify_credentials(provider, status):
            print("    Cancelled.")
            sys.exit(0)
        builder_model = model

    builder_model = builder_model or "sonnet-latest"

    if not non_interactive:
        show_header(
            "Step 4 of 4: Define Your Agent",
            "Tell us about the agent you want to create",
        )

    # Agent name
    if supplied.get("name"):
        raw_name = supplied["name"]
    else:
        raw_name = prompt_user("    Agent name")
        while not raw_name:
            print("    Please enter a name for the agent")
            raw_name = prompt_user("    Agent name")

    agent_name = to_snake_case(raw_name)
    if agent_name != raw_name and not non_interactive:
        print(f"        -> Converted to: {agent_name}")

    # Description
    if supplied.get("description"):
        description = supplied["description"]
    else:
        print()
        print("    Describe what this agent should do:")
        print("    (Be as detailed as you like - what tasks, goals?)")
        print()
        description = prompt_user("    Description")

    # LLM Model for the generated agent (not the builder)
    if supplied.get("model"):
        llm_model = supplied["model"]
    elif non_interactive:
        llm_model = "haiku-latest"
    else:
        print()
        print("    What LLM should the generated agent use?")
        llm_model = prompt_user("    LLM model for the agent", "haiku-latest")

    # Tool implementation style. `--stub-tools` finally gives the long-dead
    # `full_implementation` flag a meaning: a signature that raises
    # NotImplementedError beats hallucinated code for anything needing
    # credentials the user must wire in themselves.
    if getattr(args, "stub_tools", False):
        full_implementation = False
    elif non_interactive:
        full_implementation = True
    else:
        print()
        full_implementation = prompt_yes_no(
            "    Generate full tool implementations? (No = stubs only)",
            default=True,
        )

    # Output path. Checked here, not only at write time: these refusals used
    # to surface after the entire multi-stage LLM build had already run.
    from gimle.hugin.apps.agent_builder.tools.agent_paths import (
        check_output_path,
    )

    default_output = f"./agents/{agent_name}"
    if supplied.get("output") or non_interactive:
        output_path = supplied.get("output") or default_output
        problem = check_output_path(output_path)
        if problem:
            print(f"    {problem}")
            sys.exit(2)
    else:
        print()
        output_path = prompt_user("    Output directory path", default_output)
        while True:
            problem = check_output_path(output_path)
            if not problem:
                break
            print(f"        {problem}")
            output_path = prompt_user(
                "    Output directory path", default_output
            )

    if non_interactive:
        return {
            "agent_name": agent_name,
            "description": description,
            "llm_model": llm_model,
            "full_implementation": full_implementation,
            "dry_run": dry_run,
            "output_path": str(Path(output_path).expanduser().resolve()),
            "builder_model": builder_model,
        }

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
    print(f"        Dry run:     {'yes' if dry_run else 'no'}")
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
        "dry_run": dry_run,
        "output_path": str(Path(output_path).expanduser().resolve()),
        "builder_model": builder_model,
    }


def _check_recoverable(agent_path: Path, args: argparse.Namespace) -> None:
    """Refuse to edit into a dirty tree unattended; warn when someone is there.

    An edit rewrites files in place, so the user's own version control is the
    only undo. Uncommitted changes mean the edit can destroy work that exists
    nowhere else -- survivable when a human sees the diff and can say no, and
    unrecoverable under ``--yes``, which is precisely when nobody is watching.

    A directory git cannot answer for (not a repository, no git installed) is
    left alone rather than refused: unversioned agents are ordinary, and
    refusing them would make edit mode unusable for the common case while
    protecting nothing.
    """
    from gimle.hugin.apps.agent_builder.git_guard import uncommitted_changes

    if getattr(args, "allow_dirty", False):
        return
    dirty = uncommitted_changes(agent_path)
    if not dirty:
        return

    print()
    print(f"    {agent_path} has {len(dirty)} uncommitted change(s):")
    for line in dirty[:10]:
        print(f"        {line}")
    if len(dirty) > 10:
        print(f"        ... and {len(dirty) - 10} more")
    print()
    print("    An edit rewrites files in place; committing first gives you")
    print("    a way back. Pass --allow-dirty to skip this check.")
    print()

    if getattr(args, "yes", False):
        print("    Refusing to edit unattended into a dirty tree.")
        sys.exit(2)
    if not prompt_yes_no("    Edit anyway?", default=False):
        print("    Cancelled.")
        sys.exit(0)


def run_edit_wizard(args: argparse.Namespace) -> Dict[str, Any]:
    """Collect the inputs for editing an existing agent.

    Refuses a path that is not an agent *before* the build runs, for the same
    reason ``check_output_path`` is called in the build wizard: these refusals
    otherwise surface after a full multi-stage LLM run has already been paid
    for.
    """
    agent_path = Path(args.edit).expanduser()
    if not agent_path.is_dir():
        print(f"    No such agent directory: {agent_path}")
        sys.exit(2)
    if not any((agent_path / name).is_dir() for name in AGENT_SUBDIRECTORIES):
        print(f"    {agent_path} does not look like an agent directory.")
        print(f"    Expected one of: {', '.join(AGENT_SUBDIRECTORIES)}")
        sys.exit(2)

    _check_recoverable(agent_path, args)

    instruction = getattr(args, "instruction", None)
    if not instruction:
        if getattr(args, "yes", False):
            print("    --edit with --yes requires --instruction.")
            sys.exit(2)
        print()
        print("    What should change about this agent?")
        print()
        instruction = prompt_user("    Instruction")
        while not instruction:
            instruction = prompt_user("    Instruction")

    resolved = str(agent_path.resolve())
    return {
        "agent_path": resolved,
        "instruction": instruction,
        # The writer and the failure reporter both read output_path; an edit
        # writes back where it was loaded from.
        "output_path": resolved,
        "dry_run": bool(getattr(args, "dry_run", False)),
        "builder_model": getattr(args, "builder_model", None)
        or "sonnet-latest",
        "edit": True,
        "authorised_keys": list(getattr(args, "only", None) or []),
    }


def _confirm_and_write(
    env: Any, session: Any, output_path: str
) -> Optional[int]:
    """Show the pending edit, ask, and write it if the user agrees.

    Returns an exit code when the run is over -- nothing changed, or the user
    declined -- and None when the write happened and the caller should carry on
    to the success screen.
    """
    from gimle.hugin.apps.agent_builder.diff import (
        diff_against_disk,
        render_agent_diff,
    )
    from gimle.hugin.apps.agent_builder.tools.write_agent_files import (
        write_agent_files,
    )

    generated = env.env_vars.get("generated_files") or {}
    target = Path(output_path)
    changed, added, _ = diff_against_disk(generated, target)
    if not changed and not added:
        show_header("No Changes", "The edit did not alter any file")
        print(f"    {target} is already what the instruction asked for.")
        print()
        return 0

    show_header("Review the Edit", "Nothing has been written yet")
    print(render_agent_diff(generated, target))
    print()

    # Warn when the edit would overwrite work someone did by hand after Hugin
    # last wrote the file. The diff shows *what* changes; this says the old
    # side was not machine-written, which is what makes it worth keeping.
    from gimle.hugin.apps.agent_builder.manifest import hand_modified

    # Compare what is *on disk* against the manifest -- the question is
    # whether someone edited the existing file, not what the new one says.
    on_disk = {}
    for key in changed:
        try:
            on_disk[key] = (target / key).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    overwriting = hand_modified(target, on_disk)
    if overwriting:
        print("    Changed by hand since Hugin wrote them:")
        for key in overwriting:
            print(f"        {key}")
        print("    Applying this edit replaces those hand-written versions.")
        print()
    if not prompt_yes_no(
        f"    Apply this edit to {len(changed) + len(added)} file(s)?"
    ):
        print("    Cancelled. Nothing was written.")
        return 0

    written = write_agent_files(session.agents[0].stack, output_path)
    if written.is_error:
        print()
        print(f"    Could not write: {written.content.get('error')}")
        return 1
    return None


def _report_rejected(env: Any, output_path: str) -> None:
    """Land whatever the builder produced and say what was wrong with it.

    A failed build has already cost a full multi-stage run. Printing "reached
    maximum steps" and discarding the payload -- which lived only in memory --
    left the user with nothing to inspect, fix, or resume from.
    """
    from gimle.hugin.apps.agent_builder.tools.validate_agent import (
        validate_files,
    )
    from gimle.hugin.apps.agent_builder.tools.write_agent_files import (
        dump_rejected,
    )

    generated = env.env_vars.get("generated_files", {}) if env else {}
    if not generated:
        print("    No files were generated before the build stopped.")
        print()
        return

    path = dump_rejected(generated, output_path)
    if not path:
        return

    report = validate_files(generated)
    print(f"    Wrote what was built to: {path}")
    print(f"    Validation: {report['summary']}")
    for finding in report["errors"][:8]:
        print(f"      error  {finding['file']}: {finding['message'][:70]}")
    if len(report["errors"]) > 8:
        print(f"      ... and {len(report['errors']) - 8} more")
    print()
    print(f"    Re-check after fixing:  uv run hugin validate {path}")
    print()


def _generated_run_command(output_path: str) -> str:
    """Return the run command for a freshly generated agent.

    Delegates to the same helper the generated README uses, so the CLI and the
    README cannot disagree -- they previously gave two different commands, and
    the README's named an entrypoint that does not exist.
    """
    from gimle.hugin.apps.agent_builder.tools.agent_paths import run_command

    tasks_dir = Path(output_path) / "tasks"
    task_name = None
    if tasks_dir.is_dir():
        tasks = sorted(tasks_dir.glob("*.yaml"))
        if tasks:
            task_name = tasks[0].stem
    return run_command(output_path, task_name)


def _should_run_after_build(non_interactive: bool) -> bool:
    """Ask to launch the agent unless this is an unattended build."""
    if non_interactive:
        return False
    return prompt_yes_no("    Run your new agent now?", default=True)


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


def step_cap_outcome(step_count: int, max_steps: int, wrote_files: bool) -> str:
    """Decide what hitting the step cap means for a build.

    ``test_agent`` runs *after* the write and out of the same allowance: its
    sub-agent's steps count against the builder's budget. So a build that
    produced a complete, validated agent could still exhaust the budget in the
    optional test that follows -- and the agent was discarded to `.rejected`
    for it. That happened twice while testing `--interactive`, which makes it
    likelier again, since asking a question costs steps too.

    Returns:
        ``"ok"``, ``"capped_after_write"`` (the build succeeded, the test did
        not finish), or ``"capped_empty"`` (a real failure: nothing was made).
    """
    if step_count < max_steps:
        return "ok"
    return "capped_after_write" if wrote_files else "capped_empty"


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser.

    Split out from ``main`` so flag defaults can be asserted directly. Which
    flags default off is a behavioural property -- ``--interactive`` off keeps
    scripted runs unattended -- and a test that cannot read the default cannot
    check it.
    """
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
    parser.add_argument("--name", help="Agent name (skips the prompt)")
    parser.add_argument(
        "--description", help="What the agent should do (skips the prompt)"
    )
    parser.add_argument("--model", help="LLM model for the generated agent")
    parser.add_argument(
        "--builder-model", help="LLM model that builds the agent"
    )
    parser.add_argument("--output", help="Directory to write the agent to")
    parser.add_argument(
        "--edit",
        metavar="PATH",
        help="Edit the existing agent in PATH instead of creating one",
    )
    parser.add_argument(
        "--instruction",
        help="What to change, with --edit",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Edit even when the target has uncommitted changes",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Let the builder ask a clarifying question when the description "
        "or instruction is ambiguous, instead of guessing",
    )
    parser.add_argument(
        "--only",
        action="append",
        metavar="FILE",
        help="Restrict an edit to these files, e.g. --only tools/x.py "
        "(repeatable)",
    )
    parser.add_argument(
        "--stub-tools",
        action="store_true",
        help="Emit tool signatures that raise NotImplementedError, rather "
        "than generated bodies",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Do not prompt; requires --name and --description",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate without writing the agent directory",
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
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Run the agent builder wizard."""
    args = build_parser().parse_args(argv)

    # Run wizard
    editing = bool(getattr(args, "edit", None))
    if args.interactive and args.yes:
        # --yes exists to run without a human; --interactive exists to ask
        # one questions. Silently preferring either would surprise somebody.
        print("    --interactive and --yes cannot be used together.")
        return 2
    if getattr(args, "instruction", None) and not editing:
        print("    --instruction only applies with --edit.")
        return 2
    user_input = run_edit_wizard(args) if editing else run_wizard(args=args)

    # Set up storage path
    storage_path = Path("./storage/agent_builder")

    # Configure logging to file (not stdout)
    log_file = setup_file_logging(storage_path, args.log_level)

    # Show building screen
    show_header(
        "Editing Your Agent" if editing else "Building Your Agent",
        (
            "Please wait while the AI edits your agent..."
            if editing
            else "Please wait while the AI creates your agent..."
        ),
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

    session: Optional[Session] = None
    try:
        # Load agent_builder environment with user input
        env = Environment.load(
            str(builder_path),
            storage=storage,
            env_vars={"user_input": user_input},
        )

        # Get config and task
        config = env.config_registry.get(
            "agent_builder_interactive" if args.interactive else "agent_builder"
        )
        task = env.task_registry.get("edit_agent" if editing else "build_agent")

        # Override the builder's model with user's selection
        builder_model = user_input.get("builder_model", "sonnet-latest")
        config.llm_model = builder_model

        # Inject user input as task parameters
        task = task.set_input_parameters(user_input)
        if user_input.get("dry_run") and task.task_sequence:
            # There is no on-disk agent to execute in preview mode. Review and
            # final validation still run; the writer is forced into dry-run by
            # the environment value and records its preview for this CLI.
            task.task_sequence = [
                name for name in task.task_sequence if name != "test_agent"
            ]

        # Create and run session
        # Which command wrote a file is the useful half of provenance --
        # "Hugin wrote this" is much less informative than "an --apply run
        # wrote this, on that date".
        env.env_vars["provenance_command"] = os.environ.get(
            "HUGIN_PROVENANCE_COMMAND"
        ) or ("hugin create --edit" if editing else "hugin create")

        if user_input.get("authorised_keys"):
            env.env_vars["authorised_keys"] = user_input["authorised_keys"]

        if editing and not args.yes:
            # Hold the writer at preview until the user has seen the diff.
            # Unattended edits (--yes) have nobody to ask, so they write.
            env.env_vars["await_confirmation"] = True

        session = Session(environment=env)
        session.create_agent_from_task(config, task)

        agent = session.agents[0]
        print(f"    Builder agent: {agent.id}")
        print(f"    Using model:   {builder_model}")
        print(f"    Log file:      {log_file}")
        print()

        started = time.monotonic()
        step_count, last_error = run_steps_with_spinner(
            step_fn=agent.step,
            save_fn=lambda: storage.save_session(session),
            max_steps=args.max_steps,
            prefix="    ",
            clear_width=40,
            session=session,
        )
        elapsed = time.monotonic() - started
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
            _report_rejected(env, user_input["output_path"])
            print(f"    See full details in: {log_file}")
            print(f"    Monitor session with: hugin monitor -s {storage_path}")
            print()
            return 1

        cap_outcome = step_cap_outcome(
            step_count, args.max_steps, bool(env.env_vars.get("written_keys"))
        )
        if cap_outcome == "capped_empty":
            print(f"    Error: Reached maximum steps ({args.max_steps})")
            print("    The agent may not have finished building.")
            print()
            _report_rejected(env, user_input["output_path"])
            print(f"    Monitor session: hugin monitor -s {storage_path}")
            return 1

        if cap_outcome == "capped_after_write":
            print(f"    Note: reached maximum steps ({args.max_steps}).")
            print("    The agent was written; the test run after it did not")
            print("    finish. Try it yourself, or re-run with --max-steps.")
            print()

        dry_run_result = env.env_vars.get("dry_run_result")
        # An edit awaiting confirmation has deliberately not written yet, and
        # its preview is the thing about to be shown -- treat a recorded
        # preview as evidence the builder finished, not as an incomplete build.
        awaiting = bool(env.env_vars.get("await_confirmation")) and bool(
            dry_run_result
        )
        if (
            not env.env_vars.get("written_keys")
            and not awaiting
            and not (user_input.get("dry_run") and dry_run_result)
        ):
            # Ask whether the writer actually succeeded, not whether the
            # directory exists. Re-running the builder over an existing agent,
            # or any earlier partial write, leaves the directory in place, so
            # existence reported a refused build as "Agent Created
            # Successfully!" and offered to run a stale agent.
            print()
            print("    ┌─────────────────────────────────────────┐")
            print("    │           Build Incomplete              │")
            print("    └─────────────────────────────────────────┘")
            print()
            print("    The builder finished but wrote no agent.")
            print()
            _report_rejected(env, user_input["output_path"])
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
    finally:
        # Release session-owned resources (sandboxes, background workers) on
        # every exit path; a no-op until the agent builder uses the bash tool.
        if session is not None:
            session.close()

    if env.env_vars.pop("await_confirmation", False):
        outcome = _confirm_and_write(env, session, user_input["output_path"])
        if outcome is not None:
            return outcome

    if user_input.get("dry_run"):
        show_header(
            "Dry Run Complete", "The agent passed without being written"
        )
        preview = env.env_vars["dry_run_result"]
        print(f"    Target: {user_input['output_path']}")
        print(f"    Would write: {len(preview.get('would_write', []))} file(s)")
        print(
            f"    Would remove: {len(preview.get('would_remove', []))} file(s)"
        )
        print(f"    Built in: {elapsed:.0f}s over {step_count} steps")
        return 0

    if editing:
        # Report the files that actually changed, not the whole payload. An
        # edit's whole claim is that it was surgical, and "wrote 12 files"
        # when one was asked for is exactly the failure worth seeing.
        changed = env.env_vars.get("changed_keys", [])
        show_header("Agent Updated", "Your agent has been edited in place")
        print(f"        Location: {user_input['output_path']}")
        print(f"        Edited in: {elapsed:.0f}s over {step_count} steps")
        print()
        if changed:
            print(f"    Changed {len(changed)} file(s):")
            for key in changed:
                print(f"        {key}")
        else:
            print("    No file needed changing.")
        print()
        print("    Run it with:")
        print()
        print(f"        {_generated_run_command(user_input['output_path'])}")
        print()
        return 0

    # Success screen
    show_header("Agent Created Successfully!", "Your agent is ready to use")

    print("    ┌─────────────────────────────────────────┐")
    print("    │            Agent Details                │")
    print("    └─────────────────────────────────────────┘")
    print()
    output_path = user_input["output_path"]
    print(f"        Location: {output_path}")
    print(f"        Built in: {elapsed:.0f}s over {step_count} steps")
    requirements = Path(output_path) / "requirements.txt"
    if requirements.exists():
        print(f"        Install:  uv pip install -r {requirements}")
    report = Path(output_path) / "BUILD_REPORT.md"
    if report.exists():
        print(f"        Report:   {report}")
    print()
    print("    Run your new agent with:")
    print()
    print(f"        {_generated_run_command(output_path)}")
    print()

    # Ask if user wants to run the agent now
    if _should_run_after_build(args.yes):
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
