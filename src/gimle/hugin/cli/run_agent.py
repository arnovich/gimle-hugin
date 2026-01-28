#!/usr/bin/env python3
"""Run an agent with a specified task."""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.cli.ui import (
    make_boxed_banner,
    prompt_user,
    prompt_yes_no,
    run_steps_with_spinner,
    select_from_list,
)
from gimle.hugin.cli.ui import show_header as _show_header

# Import for completion summary
from gimle.hugin.interaction.task_result import TaskResult
from gimle.hugin.storage.local import LocalStorage


def print_completion_summary(session: Session, prefix: str = "    ") -> None:
    """Print a summary of artifacts and results after agent completion.

    Args:
        session: The session containing agents
        prefix: Indentation prefix for output lines
    """
    # Collect all artifacts from all agents
    all_artifacts = []
    for agent in session.agents:
        all_artifacts.extend(agent.stack.artifacts)

    # Find TaskResult interactions to get final results
    task_results = []
    for agent in session.agents:
        for interaction in agent.stack.interactions:
            if isinstance(interaction, TaskResult):
                task_results.append((agent, interaction))

    # Print artifacts summary
    if all_artifacts:
        print()
        print(f"{prefix}Artifacts ({len(all_artifacts)}):")
        for artifact in all_artifacts:
            artifact_type = artifact.__class__.__name__
            # Try to get a name/title from the artifact
            name = ""
            if hasattr(artifact, "title") and artifact.title:
                name = f' "{artifact.title}"'
            elif hasattr(artifact, "filename") and artifact.filename:
                name = f' "{artifact.filename}"'
            elif hasattr(artifact, "format") and artifact.format:
                name = f" ({artifact.format})"
            print(f"{prefix}  - {artifact_type}{name}")

    # Print task results
    if task_results:
        print()
        for agent, task_result in task_results:
            agent_name = agent.config.name if agent.config else "Agent"
            if task_result.finish_type:
                print(
                    f"{prefix}Result ({agent_name}): {task_result.finish_type}"
                )
            if task_result.result:
                # Show the result summary, but limit length
                if isinstance(task_result.result, dict):
                    result_str = str(task_result.result.get("summary", ""))
                    if not result_str and "message" in task_result.result:
                        result_str = str(task_result.result.get("message", ""))
                    if not result_str:
                        result_str = str(task_result.result)
                else:
                    result_str = str(task_result.result)  # type: ignore
                # Truncate if too long
                if len(result_str) > 200:
                    result_str = result_str[:197] + "..."
                if result_str:
                    # Handle multi-line results
                    lines = result_str.split("\n")
                    if len(lines) > 1:
                        print(f"{prefix}  {lines[0]}")
                        for line in lines[1:5]:  # Show up to 5 lines
                            print(f"{prefix}  {line}")
                        if len(lines) > 5:
                            print(
                                f"{prefix}  ... ({len(lines) - 5} more lines)"
                            )
                    else:
                        print(f"{prefix}  {result_str}")


# ASCII art banner
BANNER = make_boxed_banner(
    "A G E N T   R U N N E R",
    ["Run your agents interactively"],
)


def show_header(step: str = "", subtitle: str = "") -> None:
    """Display the banner header with optional step indicator."""
    _show_header(BANNER, step=step, subtitle=subtitle)


def prompt_for_parameters(
    task_params: Dict[str, Any],
) -> Dict[str, Any]:
    """Interactively prompt for task parameters."""
    result: Dict[str, Any] = {}

    for param_name, param_spec in task_params.items():
        # Handle both simple values and dict specs
        if isinstance(param_spec, dict) and "type" in param_spec:
            param_type = param_spec.get("type", "string")
            description = param_spec.get("description", "")
            default = param_spec.get("default", "")
            is_required = param_spec.get("required", False)
            choices = (
                param_spec.get("choices")
                or param_spec.get("categories")
                or param_spec.get("values")
            )
        else:
            # Simple value - use it as default
            param_type = "string"
            description = ""
            default = str(param_spec) if param_spec else ""
            is_required = False
            choices = None

        # Build enhanced prompt line
        required_tag = "[required]" if is_required else "[optional]"
        type_tag = f"({param_type})"

        prompt_parts = [f"\n    {param_name} {type_tag} {required_tag}"]
        if description:
            prompt_parts.append(f": {description}")

        print("".join(prompt_parts))

        # Show default if present
        if default:
            print(f"    [default: {default}]")

        if param_type == "categorical":
            if not isinstance(choices, list) or not all(
                isinstance(c, str) for c in choices
            ):
                print("    [error: categorical param missing 'choices' list]")
                value = prompt_user("    > ", str(default) if default else "")
            else:
                print("    Choices:")
                for i, c in enumerate(choices, 1):
                    print(f"      {i}. {c}")
                print("    Enter a number or exact value.")
                value = prompt_user("    > ", str(default) if default else "1")
        else:
            # Get value from user
            value = prompt_user("    > ", str(default) if default else "")

        # Convert to appropriate type
        if param_type == "integer":
            try:
                result[param_name] = int(value)
            except ValueError:
                result[param_name] = value
        elif param_type == "number":
            try:
                result[param_name] = float(value)
            except ValueError:
                result[param_name] = value
        elif param_type == "boolean":
            result[param_name] = value.lower() in ("true", "yes", "1", "y")
        elif param_type == "categorical" and isinstance(choices, list):
            # accept numeric selection or exact value
            selected = value.strip()
            try:
                idx = int(selected) - 1
                if 0 <= idx < len(choices):
                    result[param_name] = choices[idx]
                else:
                    result[param_name] = selected
            except ValueError:
                result[param_name] = selected
        else:
            result[param_name] = value

    return result


def find_agent_directories() -> List[Path]:
    """Find directories that look like agent directories."""
    candidates = []

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


def _ensure_ollama_model(model_name: str) -> Optional[str]:
    """Ensure an Ollama model is installed and registered.

    Args:
        model_name: The Ollama model name (e.g., 'llama3.1:8b')

    Returns:
        The registry name if successful, None if failed.
    """
    import subprocess

    from gimle.hugin.llm.models.model_registry import get_model_registry
    from gimle.hugin.llm.models.ollama import OllamaModel

    registry = get_model_registry()

    # Create registry name from ollama model name
    registry_name = model_name.replace(":", "-").replace(".", "-")

    # Check if model is installed in Ollama
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=10
        )
        installed_models = result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"Error: Could not check Ollama models: {e}")
        return None

    model_installed = model_name in installed_models

    # If already registered AND installed, we're good
    if registry_name in registry.models and model_installed:
        print(f"Model '{registry_name}' ready")
        return registry_name

    if not model_installed:
        print(f"Model '{model_name}' not installed. Installing...")
        try:
            # Run ollama pull with streaming output
            process = subprocess.Popen(
                ["ollama", "pull", model_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            if process.stdout:
                for line in process.stdout:
                    print(line.rstrip())
            process.wait()
            if process.returncode != 0:
                print(f"Error: Failed to install model '{model_name}'")
                return None
            print(f"Successfully installed '{model_name}'")
        except FileNotFoundError:
            print("Error: 'ollama' command not found. Please install Ollama.")
            return None
        except Exception as e:
            print(f"Error installing model: {e}")
            return None

    # Register the model dynamically (or re-register if needed)
    if registry_name not in registry.models:
        registry.register_model(
            registry_name,
            OllamaModel(
                model_name=model_name,
                strict_tool_calling=True,
                timeout_seconds=120,
            ),
        )
        print(f"Registered model as '{registry_name}'")
    else:
        print(f"Model '{registry_name}' ready")

    return registry_name


def run_interactive(
    args: argparse.Namespace, skip_confirmation: bool = False
) -> int:
    """Run in interactive mode when required arguments are missing."""
    # Configure logging to WARNING to suppress INFO messages during interactive mode
    from gimle.hugin.utils.logging import setup_logging

    setup_logging(level=logging.WARNING)

    show_header("Agent Runner", "Select and run your agents")

    # Step 1: Get task path if not provided
    task_path: Optional[Path] = None
    if args.task_path:
        task_path = Path(args.task_path)
        if not task_path.is_absolute():
            task_path = task_path.resolve()
    else:
        # Find agent directories
        candidates = find_agent_directories()

        if not candidates:
            print("    No agent directories found.")
            print()
            print("    Enter the path to an agent directory:")
            path_str = prompt_user("    Path")
            task_path = Path(path_str).resolve()
        elif len(candidates) == 1:
            task_path = candidates[0]
            print(f"    Found agent directory: {task_path}")
            print()
        else:
            print("    Found multiple agent directories:\n")
            path_strs = [str(p) for p in candidates]
            selected = select_from_list(path_strs, "    Select directory")
            task_path = Path(selected)

    if not task_path.exists():
        print(f"\n    Error: Path '{task_path}' does not exist")
        return 1

    if not task_path.is_dir():
        print(f"\n    Error: Path '{task_path}' is not a directory")
        return 1

    # Load environment to get available tasks
    storage_path = args.storage_path or "./storage"
    storage = LocalStorage(base_path=storage_path)

    try:
        env = Environment.load(str(task_path), storage=storage)
    except Exception as e:
        print(f"\n    Error loading environment from {task_path}: {e}")
        return 1

    # Step 2: Select task if not provided
    task_name = args.task
    if not task_name:
        show_header("Select Task", f"Agent: {task_path.name}")

        tasks = env.task_registry.registered()
        if not tasks:
            print("    No tasks found in this agent directory.")
            return 1

        task_names = list(tasks.keys())
        descriptions = {name: task.description for name, task in tasks.items()}

        print("    Available tasks:\n")
        task_name = select_from_list(
            task_names, "    Select task", descriptions
        )

    # Get the task
    try:
        task_template = env.task_registry.get(task_name)
    except ValueError:
        print(f"\n    Error: Task '{task_name}' not found")
        print(f"    Available: {list(env.task_registry.registered().keys())}")
        return 1

    # Step 3: Get parameters if task has parameters and none provided
    parameters: Dict[str, Any] = {}
    if task_template.parameters and not args.parameters:
        show_header(
            "Task Parameters",
            f"Task: {task_name}",
        )

        print(f"    Task: {task_template.name}")
        if task_template.description:
            print(f"    Description: {task_template.description}")
        print()
        print("    This task has parameters. Enter values below:")

        parameters = prompt_for_parameters(task_template.parameters)
    elif args.parameters:
        try:
            parameters = json.loads(args.parameters)
        except json.JSONDecodeError as e:
            print(f"\n    Error: Invalid JSON in --parameters: {e}")
            return 1

    # Materialize schema -> concrete template inputs
    task = task_template.set_input_parameters(parameters)

    # Step 4: Select config
    configs = env.config_registry.registered()
    if not configs:
        print("\n    Error: No configs found in task path")
        return 1

    if args.config:
        try:
            config = env.config_registry.get(args.config)
        except ValueError:
            print(f"\n    Error: Config '{args.config}' not found")
            print(f"    Available: {list(configs.keys())}")
            return 1
    else:
        config = list(configs.values())[0]

    # Handle model override
    if args.model:
        model_name = args.model
        if model_name.startswith("ollama:"):
            ollama_model = model_name[7:]
            model_name = _ensure_ollama_model(ollama_model)
            if model_name is None:
                return 1
        config.llm_model = model_name

    # Step 5: Ask for max steps (empty = no limit)
    print()
    max_steps_str = prompt_user("    Maximum steps (empty for no limit)", "")
    try:
        max_steps = int(max_steps_str) if max_steps_str else None
    except ValueError:
        max_steps = None

    # Step 6: Ask about monitor
    print()
    run_monitor = prompt_yes_no("    Run monitor dashboard?", default=True)

    # Show confirmation
    show_header("Ready to Run", "Review your configuration")

    print("    ┌─────────────────────────────────────────┐")
    print("    │        Run Configuration                │")
    print("    └─────────────────────────────────────────┘")
    print()
    print(f"        Agent:    {task_path.name}")
    print(f"        Task:     {task_name}")
    print(f"        Config:   {config.name}")
    print(f"        Model:    {config.llm_model}")
    print(f"        Max steps: {max_steps if max_steps else 'unlimited'}")
    if not run_monitor:
        print(f"        Monitor:  run `hugin monitor -s {storage_path}`")
    if task.parameters:
        print("        Parameters:")
        for k, v in task.parameters.items():
            if isinstance(k, str) and k.startswith("_"):
                val = str(v)
            elif isinstance(v, dict) and "value" in v:
                val = str(v.get("value"))
            else:
                val = str(v)
            if len(val) > 40:
                val = val[:37] + "..."
            print(f"          {k}: {val}")
    print()

    if not skip_confirmation:
        if not prompt_yes_no("    Run agent?"):
            print("    Cancelled.")
            return 0

    # Start monitor if requested
    monitor_process = None
    monitor_port = 8001
    if run_monitor:
        import subprocess
        import webbrowser

        monitor_cmd = [
            sys.executable,
            "-m",
            "gimle.hugin.cli.monitor_agents",
            "--storage-path",
            storage_path,
            "--port",
            str(monitor_port),
            "--no-browser",
        ]
        monitor_process = subprocess.Popen(
            monitor_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Give monitor a moment to start, then open browser
        import time

        time.sleep(1)
        webbrowser.open(f"http://localhost:{monitor_port}")
        print(f"    Monitor started at http://localhost:{monitor_port}")
        print(f"    Storage: {storage_path}")
        print()

    # Run the agent
    show_header("Running Agent", f"Task: {task_name}")

    session = Session(environment=env)
    session.create_agent_from_task(config, task)

    agent = session.agents[0]
    print(f"    Agent ID:  {agent.id}")
    print(f"    Model:     {config.llm_model}")
    print(f"    Storage:   {storage_path}")
    if run_monitor:
        print(f"    Monitor:   http://localhost:{monitor_port}")
    print()

    step_count, last_error = run_steps_with_spinner(
        step_fn=session.step,
        save_fn=lambda: storage.save_session(session),
        max_steps=max_steps,
        prefix="    ",
        clear_width=40,
        session=session,
        interactive=True,
    )
    if last_error:
        logging.error("Error during agent step", exc_info=last_error)

    # Final save
    storage.save_session(session)

    # Show result on a new screen
    show_header("Agent Finished", f"Task: {task_name}")
    if last_error:
        print("    ┌─────────────────────────────────────────┐")
        print("    │              Run Error                  │")
        print("    └─────────────────────────────────────────┘")
        print()
        print(f"    Error: {type(last_error).__name__}")
        print(f"    {str(last_error)[:60]}")
        print()
    elif max_steps is not None and step_count >= max_steps:
        print(f"    Reached maximum steps ({max_steps})")
        print("    The agent may not have finished.")
    else:
        print("    ┌─────────────────────────────────────────┐")
        print("    │          Agent Completed!               │")
        print("    └─────────────────────────────────────────┘")
        print()
        print(f"    Completed in {step_count} steps.")
        print_completion_summary(session, prefix="    ")

    print()
    print(f"    Session saved to: {storage_path}")
    if run_monitor:
        print(f"    Monitor running at: http://localhost:{monitor_port}")

    # If monitor is running, wait for Ctrl+C
    if monitor_process:
        print()
        print("    Press Ctrl+C to stop the monitor and exit...")
        try:
            while True:
                import time

                time.sleep(1)
        except KeyboardInterrupt:
            print("\n    Stopping monitor...")
            monitor_process.terminate()
            monitor_process.wait()
            print("    Done.")

    return 0 if not last_error else 1


def main() -> int:
    """Run an agent with a specified task."""
    parser = argparse.ArgumentParser(
        description="Run an agent with a specified task",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode - select task and parameters interactively
  hugin run -p examples/basic_agent

  # Run a specific task
  hugin run -t hello_world -p examples/basic_agent

  # Run multiple agents (multi-agent examples)
  hugin run -p examples/parallel_agents -a count_evens -a count_odds

  # Multiple agents with different configs and shared namespace
  hugin run -p examples/shared_state -n numbers -a produce:producer -a consume:consumer

  # Run with auto-install of any Ollama model
  hugin run -t hello_world -p examples/basic_agent --model ollama:llama3.1:8b

  # Run with parameters
  hugin run -t hello_world -p examples/basic_agent --parameters '{"questions": "What is AI?"}'

  # Run with specific config and more steps
  hugin run -t analyze -p apps/data_analyst --config data_analyst --max-steps 50
        """,
    )

    parser.add_argument(
        "-t",
        "--task",
        help="Name of the task to run (interactive if not provided)",
    )

    parser.add_argument(
        "-a",
        "--agent",
        action="append",
        metavar="TASK[:CONFIG]",
        help="Create agent with TASK and optional CONFIG. Can be repeated.",
    )

    parser.add_argument(
        "-n",
        "--namespace",
        action="append",
        metavar="NAME",
        help="Create shared state namespace before agents. Can be repeated.",
    )

    parser.add_argument(
        "-p",
        "--task-path",
        type=str,
        help="Path to the agent directory (interactive if not provided)",
    )

    parser.add_argument(
        "-c",
        "--config",
        help="Name of the config to use (default: first config)",
    )

    parser.add_argument(
        "--max-steps",
        type=int,
        default=100,
        help="Maximum number of steps to run (default: 100)",
    )

    parser.add_argument(
        "--storage-path",
        type=str,
        default=None,
        help="Path to storage directory (default: ./storage)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="WARNING",
        help="Set the logging level (default: WARNING)",
    )

    parser.add_argument(
        "--parameters",
        type=str,
        default=None,
        help="JSON string of parameters to pass to the task",
    )

    parser.add_argument(
        "--env-vars",
        type=str,
        default=None,
        help="JSON string of environment variables for tools",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override the LLM model. Use 'ollama:MODEL' to auto-install.",
    )

    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Run the monitor dashboard alongside the agent",
    )

    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Disable interactive mode (fail if required args missing)",
    )

    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run the agent inside the interactive TUI",
    )

    args = parser.parse_args()

    # Configure logging
    from gimle.hugin.utils.logging import setup_logging

    setup_logging(level=getattr(logging, args.log_level))

    # Check if we need interactive mode
    has_task_spec = args.task or args.agent
    needs_full_interactive = not has_task_spec and not args.task_path

    # Full interactive mode: no task/agent specified and no path
    if needs_full_interactive and not args.non_interactive:
        return run_interactive(args)

    # If we have -a/--agent but no path, interactively select path only
    if has_task_spec and not args.task_path and not args.non_interactive:
        candidates = find_agent_directories()
        if not candidates:
            print("No agent directories found.")
            print("Enter the path to an agent directory:")
            path_str = prompt_user("Path")
            args.task_path = path_str
        elif len(candidates) == 1:
            args.task_path = str(candidates[0])
            print(f"Using agent directory: {args.task_path}")
        else:
            print("Found multiple agent directories:\n")
            path_strs = [str(p) for p in candidates]
            selected = select_from_list(path_strs, "Select directory")
            args.task_path = selected
        print()

    # Non-interactive mode - validate required args
    if not has_task_spec:
        print("Error: --task or --agent is required in non-interactive mode")
        return 1
    if not args.task_path:
        print("Error: --task-path is required in non-interactive mode")
        return 1

    # Resolve task path
    task_path = Path(args.task_path)
    if not task_path.is_absolute():
        task_path = task_path.resolve()

    if not task_path.exists():
        print(f"Error: Task path '{task_path}' does not exist")
        return 1

    if not task_path.is_dir():
        print(f"Error: Task path '{task_path}' is not a directory")
        return 1

    # Parse environment variables if provided
    env_vars = None
    if args.env_vars:
        try:
            env_vars = json.loads(args.env_vars)
            logging.info(f"Environment variables: {list(env_vars.keys())}")
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in --env-vars: {e}")
            return 1

    # Load the environment
    storage_path = args.storage_path or "./storage"
    storage = LocalStorage(base_path=storage_path)

    try:
        env = Environment.load(
            str(task_path), storage=storage, env_vars=env_vars
        )
    except Exception as e:
        print(f"Error loading environment from {task_path}: {e}")
        if args.log_level == "DEBUG":
            import traceback

            traceback.print_exc()
        return 1

    # Build list of (task_name, config_name) pairs
    agent_specs: List[tuple] = []

    if args.agent:
        # Parse --agent TASK[:CONFIG] specs
        for spec in args.agent:
            if ":" in spec:
                task_name, config_name = spec.split(":", 1)
            else:
                task_name = spec
                config_name = args.config  # Use --config or None for default
            agent_specs.append((task_name, config_name))
    else:
        # Legacy: single --task with optional --config
        agent_specs.append((args.task, args.config))

    # Validate all task and config names
    configs = env.config_registry.registered()
    if not configs:
        print("Error: No configs found in task path")
        return 1
    default_config = list(configs.values())[0]

    # Handle model override for all configs
    model_override = None
    if args.model:
        model_name = args.model
        if model_name.startswith("ollama:"):
            ollama_model = model_name[7:]
            model_name = _ensure_ollama_model(ollama_model)
            if model_name is None:
                return 1
        else:
            from gimle.hugin.llm.models.model_registry import get_model_registry

            registry = get_model_registry()
            if model_name not in registry.models:
                print(f"Warning: Model '{model_name}' not in registry")
                print(f"Available: {list(registry.models.keys())}")
                return 1
        model_override = model_name

    # Parse + validate parameters (apply defaults, enforce required)
    cli_parameters: Dict[str, Any] = {}
    if args.parameters:
        try:
            cli_parameters = json.loads(args.parameters)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in --parameters: {e}")
            return 1

    # If --interactive, launch TUI with auto-launch config
    if args.interactive and args.task and not args.agent:
        from gimle.hugin.cli.interactive import (
            AgentLaunchConfig,
            InteractiveApp,
        )

        launch_config = AgentLaunchConfig(
            task_path=str(task_path),
            task_name=args.task,
            config_name=args.config,
            parameters=cli_parameters,
            max_steps=args.max_steps,
            model=model_override,
        )
        app = InteractiveApp(
            storage_path,
            task_path=str(task_path),
            launch_config=launch_config,
        )
        app.run()
        return 0

    # Start monitor if requested
    monitor_process = None
    monitor_port = 8001
    if args.monitor:
        import subprocess
        import time
        import webbrowser

        monitor_cmd = [
            sys.executable,
            "-m",
            "gimle.hugin.cli.monitor_agents",
            "--storage-path",
            storage_path,
            "--port",
            str(monitor_port),
            "--no-browser",
        ]
        monitor_process = subprocess.Popen(
            monitor_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Give monitor a moment to start, then open browser
        time.sleep(1)
        webbrowser.open(f"http://localhost:{monitor_port}")
        print(f"Monitor started at http://localhost:{monitor_port}")

    # Create session and agents
    session = Session(environment=env)

    # Create namespaces if specified
    if args.namespace:
        for ns_name in args.namespace:
            session.state.create_namespace(ns_name)
            print(f"Created namespace: {ns_name}")

    for task_name, config_name in agent_specs:
        # Get config
        if config_name:
            try:
                config = env.config_registry.get(config_name)
            except ValueError:
                print(f"Error: Config '{config_name}' not found")
                print(f"Available: {list(configs.keys())}")
                return 1
        else:
            config = default_config

        # Apply model override
        if model_override:
            config.llm_model = model_override

        # Get task
        try:
            task_template = env.task_registry.get(task_name)
        except ValueError:
            print(f"Error: Task '{task_name}' not found")
            print(f"Available: {list(env.task_registry.registered().keys())}")
            return 1

        # Set parameters
        try:
            task = task_template.set_input_parameters(cli_parameters)
        except ValueError as e:
            print(f"Error: {e}")
            return 1

        # Create agent
        session.create_agent_from_task(config, task)

    # Show agent info
    if len(session.agents) == 1:
        print(f"Agent ID:  {session.agents[0].id}")
        print(f"Model:     {session.agents[0].config.llm_model}")
    else:
        print(f"Agents:    {len(session.agents)}")
        for i, agent in enumerate(session.agents):
            print(f"  [{i+1}] {agent.id} ({agent.config.name})")
        print(f"Model:     {session.agents[0].config.llm_model}")
    print(f"Storage:   {storage_path}")
    if args.monitor:
        print(f"Monitor:   http://localhost:{monitor_port}")
    else:
        print(f"Monitor:   run `hugin monitor -s {storage_path}`")
    print()

    step_count, last_error = run_steps_with_spinner(
        step_fn=session.step,
        save_fn=lambda: storage.save_session(session),
        max_steps=args.max_steps,
        prefix="",
        clear_width=30,
        session=session,
        interactive=not args.non_interactive,
    )
    if last_error:
        logging.error("Error during agent step", exc_info=last_error)

    # Final save
    storage.save_session(session)

    # Show result
    agent_word = "Agent" if len(session.agents) == 1 else "Agents"
    if last_error:
        print(f"Error: {type(last_error).__name__}: {str(last_error)[:60]}")
    elif step_count >= args.max_steps:
        print(f"Reached maximum steps ({args.max_steps})")
    else:
        print(f"{agent_word} completed in {step_count} steps!")
        print_completion_summary(session, prefix="")

    print(f"Session saved to: {storage_path}")

    # If monitor is running, wait for Ctrl+C
    if monitor_process:
        print()
        print("Press Ctrl+C to stop the monitor and exit...")
        try:
            import time

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping monitor...")
            monitor_process.terminate()
            monitor_process.wait()
            print("Done.")

    return 0 if not last_error else 1


if __name__ == "__main__":
    sys.exit(main())
