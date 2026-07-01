#!/usr/bin/env python3
"""Run the Financial Newspaper agent."""

import argparse
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.cli.helpers import (
    configure_logging,
    open_in_browser,
    start_monitor_dashboard,
)
from gimle.hugin.llm.router_outcome import report_outcome
from gimle.hugin.storage.local import LocalStorage

# Load environment variables from .env file
load_dotenv()

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


# Use centralized storage (consistent with examples)
SCRIPT_DIR = Path(__file__).parent
SAVE_DIR = Path("./storage/financial_newspaper")
# Layout is saved by update_newspaper_layout tool in storage/newspaper_layouts
LAYOUT_DIR = Path("./storage/newspaper_layouts")

# LocalStorage automatically creates a 'sessions' subdirectory
# So we pass the base directory, not base_directory/sessions


def create_newspaper_session(
    target_symbols: list[str],
    incremental: bool = False,
    number_of_articles: int = 3,
) -> tuple[Session, LocalStorage]:
    """Create a financial newspaper agent session."""
    storage = LocalStorage(base_path=str(SAVE_DIR))

    # Add current date to environment variables
    env_vars = {
        "current_date": datetime.now().strftime("%B %d, %Y"),
        "newspaper_articles": [],  # Will store generated articles
        "target_symbols": target_symbols,
        "articles_written": 0,
        "number_of_articles": number_of_articles,  # Limit for write_article tool
    }

    # Get the path to the financial_newspaper directory
    newspaper_path = Path(__file__).parent

    env = Environment.load(
        str(newspaper_path), storage=storage, env_vars=env_vars
    )
    session = Session(environment=env)

    # Create the financial journalist agent
    config = env.config_registry.get("financial_journalist")

    # Choose task based on mode
    if incremental:
        task_template = env.task_registry.get("write_next_article")
        task = task_template.set_input_parameters(
            {
                "target_symbols": target_symbols,
            }
        )
    else:
        task_template = env.task_registry.get("daily_edition")
        task = task_template.set_input_parameters(
            {
                "number_of_articles": number_of_articles,
                "target_symbols": target_symbols,
            }
        )

    session.create_agent_from_task(config, task)

    return session, storage


def get_most_recent_session() -> str:
    """Find the most recent session ID in the session directory."""
    # LocalStorage stores sessions in base_path/sessions/
    sessions_path = SAVE_DIR / "sessions"

    if not sessions_path.exists():
        raise ValueError(
            f"No session directory found at {sessions_path}. "
            "Run without --resume to create a new session first."
        )

    # Find all session files (they're stored as flat files named by UUID)
    session_files = [
        f
        for f in sessions_path.iterdir()
        if f.is_file() and not f.name.startswith(".")
    ]

    if not session_files:
        raise ValueError(
            f"No saved sessions found in {sessions_path}. "
            "Run without --resume to create a new session first, "
            "then use --resume to continue it."
        )

    # Sort by modification time and get the most recent
    most_recent = max(session_files, key=lambda p: p.stat().st_mtime)
    session_id = most_recent.name  # The filename is the session ID

    return session_id


def load_newspaper_session(
    session_id: str,
    symbols: list[str] = [],
) -> tuple[Session, LocalStorage]:
    """Load an existing newspaper session and continue writing.

    If the agent has finished, adds a new TaskDefinition to continue with
    full context/memory of previous work.
    """
    storage = LocalStorage(base_path=str(SAVE_DIR))

    newspaper_path = Path(__file__).parent

    env_vars = {
        "target_symbols": symbols,
        "current_date": datetime.now().strftime("%B %d, %Y"),
        "newspaper_articles": [],
        "articles_written": 0,
    }

    environment = Environment.load(
        str(newspaper_path), storage=storage, env_vars=env_vars
    )

    # Load existing session
    session = storage.load_session(session_id, environment=environment)

    if session is None:
        raise ValueError(f"Session {session_id} not found")

    # Import interaction types
    from gimle.hugin.interaction.task_definition import TaskDefinition
    from gimle.hugin.interaction.waiting import Waiting

    if not session.agents:
        raise ValueError(f"Session {session_id} has no agents")

    # Find the journalist agent (first agent)
    journalist_agent = session.agents[0]
    last_interaction = journalist_agent.stack.get_last_interaction_for_branch(
        None
    )

    # Check if agent is in terminal state (Waiting with no condition)
    is_finished = (
        isinstance(last_interaction, Waiting) and not last_interaction.condition
    )

    if is_finished:
        # Increase the article limit to allow more articles
        current_articles = session.environment.env_vars.get(
            "newspaper_articles", []
        )
        current_limit = session.environment.env_vars.get(
            "number_of_articles", 3
        )
        new_limit = len(current_articles) + 1
        session.environment.env_vars["number_of_articles"] = new_limit
        print(f"📝 Increased article limit: {current_limit} → {new_limit}")

        # Add a new TaskDefinition to continue the existing agent
        task_template = environment.task_registry.get("write_next_article")
        task = task_template.set_input_parameters(
            {
                "target_symbols": symbols,
            }
        )
        task_def = TaskDefinition.create_from_task(
            task=task, stack=journalist_agent.stack
        )
        journalist_agent.stack.add_interaction(task_def)
        print("✨ Added continuation task (preserving context)")
    else:
        print("♻️  Continuing with existing agent")

    return session, storage


def _edition_quality_score(articles: list) -> Optional[float]:
    """Mean editor quality score across the edition's articles.

    A 1-10 mean, or None if none carry a numeric score. Supplements the success
    flag reported to gimle-router with a graded signal.
    """
    scores: list[float] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        value = article.get("quality_score")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            scores.append(float(value))
    if not scores:
        return None
    return sum(scores) / len(scores)


def run_newspaper_generation(session: Session, max_steps: int) -> bool:
    """Run the newspaper generation process."""
    print("📰" + "=" * 58 + "📰")
    print("📰 THE DAILY MARKET HERALD - AGENT JOURNALIST 📰")
    print("📰" + "=" * 58 + "📰")
    print(f"⏰ Session ID: {session.id}")
    print(f"📅 Date: {session.environment.env_vars['current_date']}")
    print(
        f"📊 Target Symbols: {', '.join(session.environment.env_vars['target_symbols'])}"
    )
    print("📰" + "=" * 58 + "📰")
    print()

    def print_step(step: int, agent) -> None:
        """Print step progress in-place."""
        agent_idx = session.agents.index(agent) + 1
        total_agents = len(session.agents)
        print(
            f"\r📍 Agent {agent_idx}/{total_agents} Step {step}...",
            end="",
            flush=True,
        )

    session.run(max_steps=max_steps, step_callback=print_step)
    print()  # New line after in-place updates

    # Get articles from env_vars
    articles = session.environment.env_vars.get("newspaper_articles", [])

    # The edition succeeds iff a final newspaper layout was produced.
    layout_path = Path(LAYOUT_DIR) / "latest.html"
    success = layout_path.exists()

    # Report this edition's result to gimle-router (opt-in, best-effort): the
    # session id is the x-gimle-task the calls were stamped with, so this closes
    # the loop the router's A/B tripwire needs.
    report_outcome(
        session.id,
        success=success,
        score=_edition_quality_score(articles),
    )

    if success:
        print()
        print("🎉 NEWSPAPER GENERATION COMPLETE! 🎉")
        print(f"📰 Articles published: {len(articles)}")
        print(f"📄 Newspaper saved to: {layout_path.absolute()}")

        # Auto-open the newspaper
        try:
            print("🌐 Opening newspaper in browser...")
            webbrowser.open(f"file://{layout_path.absolute()}")
        except Exception as e:
            print(f"⚠️  Could not auto-open browser: {e}")

    return success


def main() -> int:
    """Run the Financial Newspaper agent."""
    parser = argparse.ArgumentParser(
        description="Run the Daily Market Herald newspaper agent"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        nargs="+",
        default=[
            "AAPL",
            "MSFT",
            "GOOGL",  # Tech stocks
            "BTC-USD",
            "ETH-USD",  # Crypto
            "EURUSD=X",
            "GBPUSD=X",  # Forex
            "GC=F",
            "CL=F",  # Commodities (Gold, Oil)
        ],
        help="Ticker symbols to cover: stocks (AAPL), crypto (BTC-USD), forex (EURUSD=X), commodities (GC=F for gold)",
    )
    parser.add_argument(
        "--number-of-articles",
        type=int,
        default=3,
        help="Number of articles to write (default: 3)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Maximum number of agent steps (default: 100)",
    )
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Run with agent monitor for debugging (default: False)",
    )
    parser.add_argument(
        "--monitor-port",
        type=int,
        default=8081,
        help="Agent monitor port (default: 8081)",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        help="Continue from an existing session ID",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the most recent session (default: False)",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Start in incremental mode: write one article at a time (for new sessions)",
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

    # Validate mutually exclusive options
    if args.session_id and args.resume:
        print("❌ Error: Cannot use both --session-id and --resume")
        return 1

    # Create directories (LocalStorage will create sessions/ subdirectory automatically)
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    LAYOUT_DIR.mkdir(parents=True, exist_ok=True)

    print("📰 Initializing The Daily Market Herald...")

    # Load or create session
    if args.session_id or args.resume:
        # Determine session ID
        if args.resume:
            try:
                session_id = get_most_recent_session()
                print(f"📂 Resuming most recent session: {session_id}")
            except Exception as e:
                print(f"❌ Error finding recent session: {e}")
                return 1
        else:
            session_id = args.session_id
            print(f"📂 Loading session: {session_id}")

        print(f"📊 Covering: {', '.join(args.symbols)}")
        print()
        try:
            session, storage = load_newspaper_session(session_id, args.symbols)
            print("✅ Loaded existing session")
        except Exception as e:
            print(f"❌ Error loading session: {e}")
            raise e
            # return 1
    else:
        print(f"📊 Covering: {', '.join(args.symbols)}")
        print(f"📝 Articles to write: {args.number_of_articles}")
        if args.incremental:
            print("🔄 Mode: Incremental (one article at a time)")
        print()
        session, storage = create_newspaper_session(
            args.symbols, args.incremental, args.number_of_articles
        )
        print("✅ Created journalist agent session")

    print(f"🆔 Session ID: {session.id}")
    print()

    # Initialize optional services
    monitor_process = None

    # Start agent monitor if requested
    if args.monitor:
        print(
            f"🌐 Starting agent monitor at http://localhost:{args.monitor_port}/"
        )
        print(
            "📊 Monitor the agent's reasoning, tool calls, and artifacts in real-time"
        )
        print("📰 The newspaper will be viewable as an artifact in the monitor")

        # Start agent monitor using helper
        print("⏳ Waiting for monitor to start...")
        monitor_process = start_monitor_dashboard(
            storage_path=str(SAVE_DIR),
            config_path=str(Path(__file__).parent),
            port=args.monitor_port,
            no_browser=True,
        )

        # Check if monitor process is still running
        if monitor_process.poll() is not None:
            # Process died, get the error
            stdout, stderr = monitor_process.communicate()
            print("❌ Monitor failed to start!")
            if stderr:
                error_text = stderr.decode()
                print(f"   Error: {error_text[:500]}")  # Truncate long errors
            if stdout:
                output_text = stdout.decode()
                print(f"   Output: {output_text[:500]}")  # Truncate long output
            return 1

        print("✅ Monitor started successfully")
        print("   Note: Monitor may take a few moments to load agent data")

    # Save initial session
    storage.save_session(session)

    # Give services time to discover the session
    if args.monitor:
        time.sleep(1)

    # Open browser for monitor
    if args.monitor:
        print("🌐 Opening monitor in browser...")
        open_in_browser(f"http://localhost:{args.monitor_port}/")

    print()
    print("⚠️  Newspaper generation will run automatically")
    print()

    # Run newspaper generation
    try:
        success = run_newspaper_generation(session, args.max_steps)

        if success:
            print()
            print("✅ Newspaper generation complete!")
            print(
                f"   Generated newspaper: file://{LAYOUT_DIR / 'latest.html'}"
            )
        else:
            print()
            print("⚠️  Newspaper generation incomplete")

        # Keep monitor alive if running (regardless of success/failure)
        if args.monitor:
            print()
            print("🌐 Monitor still running - press Ctrl+C to exit")
            print(f"   Monitor: http://localhost:{args.monitor_port}/")
            print(
                "   View the newspaper artifact by clicking on the "
                "update_newspaper_layout interaction"
            )
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n🛑 Shutting down...")

        return 0 if success else 1

    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
        return 0
    except Exception as e:
        print(f"❌ Error during generation: {e}")
        raise e
    finally:
        # Cleanup
        if monitor_process:
            monitor_process.terminate()
            monitor_process.wait()


if __name__ == "__main__":
    sys.exit(main())
