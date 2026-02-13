#!/usr/bin/env python3
"""Hugin CLI - Main entry point for all Hugin commands."""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from gimle.hugin import __version__
from gimle.hugin.cli.ui import HUGIN_LOGO

VERSION = __version__

BANNER = HUGIN_LOGO

APPS_GITHUB_URL = "https://github.com/anthropics/hugin-apps"


def get_apps_dir() -> Optional[Path]:
    """Get the apps directory path from current working directory."""
    apps_dir = Path.cwd() / "apps"
    if apps_dir.exists():
        return apps_dir
    return None


def list_apps() -> List[str]:
    """List available apps."""
    apps_dir = get_apps_dir()
    if not apps_dir:
        return []

    apps = []
    for item in apps_dir.iterdir():
        if item.is_dir() and not item.name.startswith(("_", ".")):
            # Check if it looks like a valid app (has configs/ or tasks/)
            if (item / "configs").exists() or (item / "tasks").exists():
                apps.append(item.name)
    return sorted(apps)


def cmd_create(args: argparse.Namespace) -> int:
    """Run the create-agent wizard."""
    from gimle.hugin.cli.create_agent import main as create_main

    # Pass through to create_agent's main
    sys.argv = ["hugin create"] + args.extra_args
    return create_main()


def cmd_run(args: argparse.Namespace) -> int:
    """Run an agent."""
    from gimle.hugin.cli.run_agent import main as run_main

    # Build arguments for run_agent
    sys.argv = ["hugin run"]
    # Task and task-path are now optional - run_agent handles interactive mode
    if args.task:
        sys.argv.extend(["--task", args.task])
    if args.agent:
        for agent_spec in args.agent:
            sys.argv.extend(["--agent", agent_spec])
    if args.namespace:
        for ns in args.namespace:
            sys.argv.extend(["--namespace", ns])
    if args.task_path:
        sys.argv.extend(["--task-path", args.task_path])
    if args.config:
        sys.argv.extend(["--config", args.config])
    if args.parameters:
        sys.argv.extend(["--parameters", args.parameters])
    if args.max_steps:
        sys.argv.extend(["--max-steps", str(args.max_steps)])
    if args.storage_path:
        sys.argv.extend(["--storage-path", args.storage_path])
    if args.log_level:
        sys.argv.extend(["--log-level", args.log_level])
    if args.model:
        sys.argv.extend(["--model", args.model])
    if args.monitor:
        sys.argv.append("--monitor")
    if getattr(args, "interactive", False):
        sys.argv.append("--interactive")

    return run_main()


def cmd_interactive(args: argparse.Namespace) -> int:
    """Run the interactive TUI for agent management."""
    from gimle.hugin.cli.interactive import InteractiveApp

    storage_path = getattr(args, "storage_path", None) or "./storage"
    task_path = getattr(args, "task_path", None)
    app = InteractiveApp(storage_path, task_path=task_path)
    app.run()
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    """Run the monitoring dashboard."""
    from gimle.hugin.cli.monitor_agents import main as monitor_main

    sys.argv = ["hugin monitor"]
    if args.storage_path:
        sys.argv.extend(["--storage-path", args.storage_path])
    if args.port:
        sys.argv.extend(["--port", str(args.port)])
    if args.no_browser:
        sys.argv.append("--no-browser")
    if args.log_level:
        sys.argv.extend(["--log-level", args.log_level])

    return monitor_main()


def _show_no_apps_message() -> None:
    """Show message when no apps directory is found."""
    print()
    print("    No apps directory found in the current directory.")
    print()
    print("    Apps are example agents you can run and learn from.")
    print()
    print("    To get started with apps:")
    print()
    print(f"        git clone {APPS_GITHUB_URL} apps")
    print()
    print("    Or download from:")
    print(f"        {APPS_GITHUB_URL}")
    print()


def cmd_apps(args: argparse.Namespace) -> int:
    """List available apps."""
    apps_dir = get_apps_dir()

    if not apps_dir:
        _show_no_apps_message()
        return 1

    apps = list_apps()

    if not apps:
        print()
        print("    Apps directory exists but no valid apps found.")
        print("    Apps should have a 'configs/' or 'tasks/' subdirectory.")
        print()
        return 1

    print("\nAvailable apps:\n")
    for app in apps:
        print(f"    {app}")

    print("\nRun an app with:")
    print("    hugin app <name>")
    print()
    return 0


def cmd_app(args: argparse.Namespace) -> int:
    """Run a specific app."""
    app_name = args.name
    apps_dir = get_apps_dir()

    if not apps_dir:
        _show_no_apps_message()
        return 1

    app_path = apps_dir / app_name

    if not app_path.exists():
        print(f"\n    Error: App '{app_name}' not found.")
        apps = list_apps()
        if apps:
            print("\n    Available apps:")
            for app in apps:
                print(f"        {app}")
        else:
            print("\n    No apps available.")
        print()
        return 1

    # Check if app has a run.py
    run_script = app_path / "run.py"
    if run_script.exists():
        import subprocess

        cmd = [sys.executable, str(run_script)] + args.extra_args
        try:
            return subprocess.call(cmd)
        except KeyboardInterrupt:
            return 0

    # Otherwise, try to run it as a standard agent
    # Find the main task
    tasks_dir = app_path / "tasks"
    main_task = None

    if tasks_dir.exists():
        if (tasks_dir / "main.yaml").exists():
            main_task = "main"
        else:
            # Use first task found
            for task_file in tasks_dir.glob("*.yaml"):
                main_task = task_file.stem
                break

    if not main_task:
        print(f"Error: No tasks found in '{app_name}'.")
        return 1

    # Run the agent
    from gimle.hugin.cli.run_agent import main as run_main

    sys.argv = [
        "hugin app",
        "--task",
        main_task,
        "--task-path",
        str(app_path),
    ] + args.extra_args
    return run_main()


def cmd_rate(args: argparse.Namespace) -> int:
    """Rate an artifact as a human reviewer."""
    from gimle.hugin.cli.rate_artifact import rate_artifact_cli

    return rate_artifact_cli(
        storage_path=args.storage_path or "./storage",
        artifact_id=args.artifact_id,
        rating=args.rating,
        comment=args.comment,
        prompt_comment=args.comment is None,
    )


def cmd_install_models(args: argparse.Namespace) -> int:
    """Install Ollama models."""
    from gimle.hugin.cli.install_ollama_models import main as install_main

    sys.argv = ["hugin install-models"] + args.extra_args
    return install_main()


def cmd_version(args: argparse.Namespace) -> int:
    """Show version information."""
    print(BANNER)
    print(f"    Hugin Agent Framework v{VERSION}")
    print()
    return 0


def main() -> int:
    """Run the Hugin CLI."""
    parser = argparse.ArgumentParser(
        prog="hugin",
        description="Hugin Agent Framework - Build and run intelligent agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    hugin create              Interactive agent builder
    hugin run -t hello        Run an agent task
    hugin monitor             Launch monitoring dashboard
    hugin apps                List available apps
    hugin app rap-machine     Run the rap-machine app
    hugin --env run -t hello  Run with .env file loaded
        """,
    )
    parser.add_argument(
        "-v", "--version", action="store_true", help="Show version"
    )
    parser.add_argument(
        "--env",
        action="store_true",
        help="Load .env file from current directory",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # create command
    create_parser = subparsers.add_parser(
        "create",
        help="Create a new agent interactively",
        description="Interactive wizard for creating new Hugin agents",
    )
    create_parser.add_argument(
        "extra_args", nargs="*", help="Additional arguments"
    )
    create_parser.set_defaults(func=cmd_create)

    # run command
    run_parser = subparsers.add_parser(
        "run",
        help="Run an agent with a task",
        description="Run an agent with a specified task (interactive if args missing)",
    )
    run_parser.add_argument(
        "-t", "--task", help="Task name (interactive if not provided)"
    )
    run_parser.add_argument(
        "-a",
        "--agent",
        action="append",
        metavar="TASK[:CONFIG]",
        help="Create agent with TASK and optional CONFIG. Can be repeated.",
    )
    run_parser.add_argument(
        "-n",
        "--namespace",
        action="append",
        metavar="NAME",
        help="Create shared state namespace before agents. Can be repeated.",
    )
    run_parser.add_argument(
        "-p",
        "--task-path",
        help="Path to agent directory (interactive if not provided)",
    )
    run_parser.add_argument("-c", "--config", help="Config name to use")
    run_parser.add_argument("--parameters", help="JSON parameters for task")
    run_parser.add_argument(
        "--max-steps", type=int, help="Maximum steps (default: 100)"
    )
    run_parser.add_argument("--storage-path", help="Path for agent storage")
    run_parser.add_argument(
        "-l",
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    run_parser.add_argument("--model", help="Override LLM model")
    run_parser.add_argument(
        "--monitor",
        action="store_true",
        help="Run monitor dashboard alongside agent",
    )
    run_parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Run in interactive TUI mode for browsing sessions/agents",
    )
    run_parser.set_defaults(func=cmd_run)

    # interactive command
    interactive_parser = subparsers.add_parser(
        "interactive",
        help="Open the interactive TUI for browsing sessions and agents",
        description="Launch the interactive TUI without running an agent",
    )
    interactive_parser.add_argument(
        "-p", "--task-path", help="Path to agent directory"
    )
    interactive_parser.add_argument(
        "-s", "--storage-path", help="Path to agent storage"
    )
    interactive_parser.set_defaults(func=cmd_interactive)

    # monitor command
    monitor_parser = subparsers.add_parser(
        "monitor",
        help="Launch the monitoring dashboard",
        description="Web dashboard for monitoring agent execution",
    )
    monitor_parser.add_argument(
        "-s", "--storage-path", help="Path to agent storage"
    )
    monitor_parser.add_argument(
        "-p", "--port", type=int, default=8000, help="Server port"
    )
    monitor_parser.add_argument(
        "--no-browser", action="store_true", help="Don't open browser"
    )
    monitor_parser.add_argument(
        "-l",
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    monitor_parser.set_defaults(func=cmd_monitor)

    # rate command
    rate_parser = subparsers.add_parser(
        "rate",
        help="Rate an artifact as a human reviewer",
        description="Rate an artifact from storage with 1-5 stars",
    )
    rate_parser.add_argument(
        "-s", "--storage-path", help="Path to agent storage"
    )
    rate_parser.add_argument(
        "--artifact-id", help="UUID of the artifact to rate"
    )
    rate_parser.add_argument(
        "--rating",
        type=int,
        choices=[1, 2, 3, 4, 5],
        help="Rating from 1 (poor) to 5 (excellent)",
    )
    rate_parser.add_argument(
        "--comment", help="Optional comment explaining the rating"
    )
    rate_parser.set_defaults(func=cmd_rate)

    # apps command (list apps)
    apps_parser = subparsers.add_parser(
        "apps",
        help="List available apps",
        description="Show all available apps in the apps directory",
    )
    apps_parser.set_defaults(func=cmd_apps)

    # app command (run specific app)
    app_parser = subparsers.add_parser(
        "app",
        help="Run a specific app",
        description="Run an app from the apps directory",
    )
    app_parser.add_argument("name", help="App name to run")
    app_parser.add_argument(
        "extra_args", nargs="*", help="Additional arguments for the app"
    )
    app_parser.set_defaults(func=cmd_app)

    # install-models command
    install_parser = subparsers.add_parser(
        "install-models",
        help="Install Ollama models",
        description="Install recommended Ollama models for local inference",
    )
    install_parser.add_argument(
        "extra_args", nargs="*", help="Additional arguments"
    )
    install_parser.set_defaults(func=cmd_install_models)

    # version command
    version_parser = subparsers.add_parser(
        "version", help="Show version information"
    )
    version_parser.set_defaults(func=cmd_version)

    # Parse arguments
    args = parser.parse_args()

    # Load .env file if --env flag is set
    if args.env:
        from dotenv import load_dotenv

        env_path = Path.cwd() / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            print(f"Loaded environment from {env_path}")
        else:
            print(f"Warning: .env file not found at {env_path}")

    # Handle -v flag
    if args.version:
        return cmd_version(args)

    # No command given - show help
    if not args.command:
        print(BANNER)
        print(f"    Hugin Agent Framework v{VERSION}")
        print("    Build and run intelligent agents with ease")
        print()
        parser.print_help()
        return 0

    # Run the command
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
