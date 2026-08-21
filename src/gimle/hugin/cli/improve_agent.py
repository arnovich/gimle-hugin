"""`hugin improve` -- read an agent's run history and propose changes.

Propose-only, deliberately and for now completely: the task it runs has no
write tool at all, so "it did not apply anything" is a property of the wiring
rather than of the model having behaved. Applying a proposal is a separate
step the user starts, having read what is proposed.

The reason for that split is in the metrics. The most available measure of an
agent -- whether it declared success -- is chosen by the agent being measured,
so a loop that optimises it has an obvious cheap win: declare success sooner.
Until a before/after replay on identical inputs exists to contradict that,
nothing here should be able to write.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.cli.ui import run_steps_with_spinner, show_header
from gimle.hugin.storage.local import LocalStorage

# Matches the build wizard's default; an improve run is a single stage and
# should need far fewer, but a wedged run should stop rather than spin.
DEFAULT_MAX_STEPS = 80


def _builder_path() -> Optional[Path]:
    """Locate the agent_builder app, installed or in a source tree."""
    try:
        from gimle.hugin.apps import get_apps_path

        candidate = get_apps_path() / "agent_builder"
        if candidate.exists():
            return candidate
    except ImportError:
        pass
    root = Path(__file__).parent.parent.parent.parent.parent
    candidate = root / "apps" / "agent_builder"
    return candidate if candidate.exists() else None


def _print_proposals(proposals: List[Dict[str, Any]], agent_path: str) -> None:
    """Render the proposals, evidence first.

    The metric leads each entry because it is the part that was checked. The
    rationale is the model's prose and is the part a reader should weigh.
    """
    print()
    print(f"    {len(proposals)} proposal(s) for {agent_path}:")
    print()
    for index, proposal in enumerate(proposals, start=1):
        print(f"    {index}. {proposal['file']}  [{proposal['change_type']}]")
        print(
            f"       evidence: {proposal['metric']} = "
            f"{proposal['observed_value']}"
        )
        for line in str(proposal["rationale"]).splitlines():
            print(f"       {line}")
        print()


def main(argv: Optional[List[str]] = None) -> int:
    """Run the propose-only improvement pass."""
    parser = argparse.ArgumentParser(
        prog="hugin improve",
        description="Read an agent's historic runs and propose changes. "
        "Proposes only -- nothing is written.",
    )
    parser.add_argument("agent_path", help="Directory of the agent to improve")
    parser.add_argument(
        "-s",
        "--storage-path",
        help="Storage directory the agent ran against",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Most recent runs to read (default: 50)",
    )
    parser.add_argument(
        "--builder-model",
        default="sonnet-latest",
        help="Model that does the analysis (default: sonnet-latest)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=DEFAULT_MAX_STEPS,
        help=f"Maximum steps (default: {DEFAULT_MAX_STEPS})",
    )
    args = parser.parse_args(argv)

    agent_path = Path(args.agent_path).expanduser()
    if not agent_path.is_dir():
        print(f"    No such agent directory: {agent_path}")
        return 2

    storage_path = args.storage_path
    if not storage_path:
        from gimle.hugin.analysis.traces import default_storage_path

        storage_path = default_storage_path(str(agent_path))
    if not storage_path or not Path(storage_path).expanduser().is_dir():
        print("    Pass --storage-path (the directory the agent ran against).")
        return 2

    builder_path = _builder_path()
    if not builder_path:
        print("    Could not find the agent_builder app.")
        return 1

    show_header(
        "Improving Your Agent", "Reading its run history and proposing changes"
    )
    print(f"    Agent:   {agent_path}")
    print(f"    Storage: {storage_path}")
    print()

    storage = LocalStorage(base_path="./storage/agent_builder")
    session: Optional[Session] = None
    try:
        env = Environment.load(str(builder_path), storage=storage)
        config = env.config_registry.get("agent_builder")
        config.llm_model = args.builder_model
        task = env.task_registry.get("improve_agent").set_input_parameters(
            {
                "agent_path": str(agent_path),
                "storage_path": str(storage_path),
                "limit": args.limit,
            }
        )

        session = Session(environment=env)
        session.create_agent_from_task(config, task)
        agent = session.agents[0]

        _, last_error = run_steps_with_spinner(
            step_fn=agent.step,
            save_fn=lambda: storage.save_session(session),
            max_steps=args.max_steps,
            prefix="    ",
            clear_width=40,
            session=session,
        )
        storage.save_session(session)
        if last_error:
            logging.error("Error during improve run", exc_info=last_error)
            print(f"    Error: {type(last_error).__name__}: {last_error}")
            return 1

        proposals = env.env_vars.get("proposed_changes") or []
    finally:
        if session is not None:
            session.close()

    if not proposals:
        print()
        print("    No changes proposed.")
        print()
        print("    That is a real answer, not a failure: every proposal has")
        print("    to cite a metric from the run history, and uncited ones")
        print("    are rejected rather than recorded.")
        print()
        return 0

    _print_proposals(proposals, str(agent_path))
    print("    Nothing has been written. To act on one of these:")
    print()
    print(
        f"        uv run hugin create --edit {agent_path} "
        '--instruction "..." --only <file>'
    )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
