#!/usr/bin/env python3
"""Run BabyHugin - A Hugin version of BabyAGI."""

import argparse
import logging
import os
import sys
from pathlib import Path

from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.cli.helpers import (
    configure_logging,
    open_in_browser,
    start_monitor_dashboard,
)
from gimle.hugin.cli.ui import clear_screen, run_steps_with_spinner
from gimle.hugin.storage.local import LocalStorage

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(message)s",
)

logger = logging.getLogger(__name__)

# Storage directory
SAVE_DIR = "./storage/baby_hugin"


def main() -> int:
    """Run BabyHugin."""
    parser = argparse.ArgumentParser(
        description="BabyHugin - An autonomous AI assistant inspired by BabyAGI"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="sonnet-latest",
        help="Model to use (default: sonnet-latest)",
    )
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Run with the agent monitor dashboard",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Monitor port (default: 8080)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Maximum steps before stopping (default: None)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="WARNING",
        help="Set the logging level (default: WARNING)",
    )

    args = parser.parse_args()

    # Configure logging
    configure_logging(args.log_level)

    # Create storage directory
    os.makedirs(SAVE_DIR, exist_ok=True)

    print("🐣 Starting BabyHugin...")
    print(f"🤖 Model: {args.model}")
    print()

    # Load environment
    app_path = Path(__file__).parent
    storage = LocalStorage(base_path=SAVE_DIR)
    env = Environment.load(str(app_path), storage=storage)

    # Update model if specified
    config = env.config_registry.get("baby_hugin")
    config.llm_model = args.model

    # Create session
    session = Session(environment=env)

    # Create agent from task
    task = env.task_registry.get("main")
    session.create_agent_from_task(config, task)

    print("✅ Created BabyHugin agent")
    print(f"📁 Storage: {SAVE_DIR}")
    print()

    # Start monitor if requested
    monitor_process = None
    if args.monitor:
        print(f"🌐 Starting monitor at http://localhost:{args.port}/")
        monitor_process = start_monitor_dashboard(SAVE_DIR, args.port)
        open_in_browser(f"http://localhost:{args.port}/")
        print()

    # Clear screen and show clean header for interactive session
    clear_screen()
    print("┌─────────────────────────────────────────────────┐")
    print("│  🐣 BabyHugin - Your AI Assistant               │")
    print("│     Inspired by BabyAGI (babyagi.org)           │")
    print("└─────────────────────────────────────────────────┘")
    print()

    # Run the session with interactive support for AskHuman
    try:
        step_count, last_error = run_steps_with_spinner(
            step_fn=session.step,
            save_fn=lambda: storage.save_session(session),
            max_steps=args.max_steps,
            prefix="🐣 ",
            status_message="Thinking...",
            session=session,
            interactive=True,  # Enable AskHuman prompting
        )

        if last_error:
            print(f"❌ Error during session: {last_error}")

        print()
        print("🐣 BabyHugin session complete!")
        print(f"📊 Total steps: {step_count}")

        if monitor_process:
            print("\n🌐 Monitor still running - press Ctrl+C to exit")
            try:
                while True:
                    import time

                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n🛑 Shutting down...")
                monitor_process.terminate()
                monitor_process.wait()

        return 0

    except KeyboardInterrupt:
        print("\n🛑 Session interrupted by user")
        if monitor_process:
            monitor_process.terminate()
            monitor_process.wait()
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        if monitor_process:
            monitor_process.terminate()
            monitor_process.wait()
        raise e


if __name__ == "__main__":
    sys.exit(main())
