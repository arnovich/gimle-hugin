#!/usr/bin/env python3
"""Run the Data Analyst agent."""

import argparse
import json
import sys
import time
from pathlib import Path

from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.cli.helpers import (
    configure_logging,
    open_in_browser,
    start_monitor_dashboard,
)
from gimle.hugin.storage.local import LocalStorage

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Use centralized storage (consistent with examples)
APP_DIR = Path(__file__).parent
SAVE_DIR = Path("./storage/data_analyst")


def run_analysis(session: Session, max_steps: int = 50) -> bool:
    """Run the data analysis."""
    print("=" * 60)
    print("Data Analyst Agent")
    print("=" * 60)
    print(f"Session ID: {session.id}")
    print("=" * 60)
    print()

    def print_step(step: int, agent) -> None:
        """Print step progress in-place."""
        agent_idx = session.agents.index(agent) + 1
        total_agents = len(session.agents)
        print(
            f"\rAgent {agent_idx}/{total_agents} Step {step}...",
            end="",
            flush=True,
        )

    step_count = session.run(max_steps=max_steps, step_callback=print_step)
    print(f"\rAnalysis complete! Completed in {step_count} steps.          ")
    return True


def main() -> int:
    """Run the Data Analyst agent."""
    parser = argparse.ArgumentParser(description="Run the Data Analyst agent")
    parser.add_argument(
        "file",
        type=str,
        nargs="?",
        default=None,
        help="Path to data file (CSV or SQLite) to analyze",
    )
    parser.add_argument(
        "--focus",
        type=str,
        default=None,
        help="Specific focus or instruction for the analysis (e.g., 'trends by region')",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Maximum number of agent steps (default: 50)",
    )
    parser.add_argument(
        "--parameters",
        type=str,
        default=None,
        help="JSON string of additional task parameters",
    )
    parser.add_argument(
        "--no-monitor",
        action="store_true",
        help="Disable the agent monitor (enabled by default)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Agent monitor port (default: 8080)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="WARNING",
        help="Set the logging level (default: WARNING)",
    )
    args = parser.parse_args()

    # Configure logging based on command line argument
    configure_logging(args.log_level)

    # Create storage directory
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    print("Initializing Data Analyst...")

    # Create storage and environment
    storage = LocalStorage(base_path=str(SAVE_DIR))
    env = Environment.load(str(APP_DIR), storage=storage)

    # Create session
    session = Session(environment=env)

    # Get config and task
    config = env.config_registry.get("data_analyst")
    task_template = env.task_registry.get("analyze")

    # Build parameters
    params = {}
    if args.parameters:
        params = json.loads(args.parameters)
    if args.file:
        params["data_source"] = args.file
    if args.focus:
        params["focus"] = args.focus

    # Set parameters on task
    task = task_template.set_input_parameters(params)

    # Create agent
    session.create_agent_from_task(config, task)

    print(f"Created agent for task: {task.name}")
    if params:
        print(f"Parameters: {params}")
    print()

    # Save initial session
    storage.save_session(session)

    # Start agent monitor by default
    monitor_process = None
    if not args.no_monitor:
        print(f"Starting agent monitor at http://localhost:{args.port}/")
        print("(Use --no-monitor to disable)")
        print()
        monitor_process = start_monitor_dashboard(str(SAVE_DIR), args.port)
        open_in_browser(f"http://localhost:{args.port}/")

    # Run analysis
    try:
        run_analysis(session, args.max_steps)

        # Check if HTML report was generated and open it
        report_path = SAVE_DIR / "reports" / "latest.html"
        if report_path.exists():
            print()
            print(f"Opening report: {report_path.absolute()}")
            open_in_browser(f"file://{report_path.absolute()}")

        if monitor_process:
            print()
            print(
                f"Agent monitor still running at http://localhost:{args.port}/"
            )
            print("Press Ctrl+C to exit")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

        return 0
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 0
    except Exception as e:
        print(f"Error during analysis: {e}")
        raise
    finally:
        if monitor_process:
            monitor_process.terminate()
            monitor_process.wait()


if __name__ == "__main__":
    sys.exit(main())
