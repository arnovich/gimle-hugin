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
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.cli.ui import run_steps_with_spinner, show_header
from gimle.hugin.storage.local import LocalStorage

# Matches the build wizard's default; an improve run is a single stage and
# should need far fewer, but a wedged run should stop rather than spin.
DEFAULT_MAX_STEPS = 80


def _snapshot(agent: Path, files: List[str]) -> Path:
    """Copy the files an apply will touch, so a regression can be undone.

    Not a substitute for version control -- it covers exactly the files being
    changed, and only for the length of this run. It exists because the revert
    has to work for an unversioned agent too, and because a revert nobody
    prepared is a revert that does not happen.
    """
    backup = Path(tempfile.mkdtemp(prefix="hugin-improve-"))
    for key in files:
        source = agent / key
        if not source.is_file():
            continue
        destination = backup / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return backup


def _restore(agent: Path, backup: Path, files: List[str]) -> List[str]:
    """Put the snapshotted files back. Returns what was restored."""
    restored = []
    for key in files:
        source = backup / key
        if not source.is_file():
            continue
        shutil.copy2(source, agent / key)
        restored.append(key)
    return restored


def _instruction_for(proposal: Dict[str, Any]) -> str:
    """Turn one proposal into an edit instruction.

    The rationale is the model's own prose, and it was written while reading
    trace text an outside party may have influenced. It therefore reaches a
    code change only through `hugin create --edit` *without* --yes, so the
    diff is shown and a human agrees before anything is written. That is the
    whole reason apply is not unattended.
    """
    return (
        f"{proposal['rationale']}\n\n"
        f"Evidence from the agent's run history: "
        f"{proposal['metric']} = {proposal['observed_value']}."
    )


def _apply_one(
    agent: Path, proposal: Dict[str, Any], model: Optional[str]
) -> bool:
    """Run one proposal through the edit path. Returns True if it wrote."""
    command = [
        sys.executable,
        "-m",
        "gimle.hugin.cli.cli",
        "create",
        "--edit",
        str(agent),
        "--instruction",
        _instruction_for(proposal),
        "--only",
        proposal["file"],
        "--allow-dirty",
    ]
    if model:
        command += ["--builder-model", model]
    print()
    print(f"    Editing {proposal['file']} ...")
    print()
    completed = subprocess.run(command)
    return completed.returncode == 0


def _replay(
    agent: Path, storage: str, workdir: Path, limit: int, max_inputs: int
) -> Optional[Dict[str, Any]]:
    """Replay the agent on harvested inputs, or None when none exist."""
    from gimle.hugin.analysis.replay import harvest_inputs, replay_inputs
    from gimle.hugin.analysis.traces import TraceReadError

    try:
        inputs = harvest_inputs(storage, limit=limit, max_inputs=max_inputs)
    except TraceReadError:
        return None
    if not inputs:
        return None
    return replay_inputs(str(agent), inputs, workdir=str(workdir))


def _guarded_apply(
    agent: Path,
    proposals: List[Dict[str, Any]],
    storage: str,
    args: argparse.Namespace,
) -> int:
    """Apply proposals, then prove on replay that nothing got worse.

    The order matters and is the point: measure first, change second, measure
    again, and undo if the second measurement is worse. An apply that changed
    code and then reported its own opinion of the result would be the failure
    this whole phase is built to avoid.
    """
    from gimle.hugin.analysis.replay import compare_replays

    workroot = Path(args.workdir).expanduser()
    files = sorted({p["file"] for p in proposals})

    print()
    print("    Recording how the agent behaves now, before changing it ...")
    before = _replay(
        agent, storage, workroot / "before", args.limit, args.max_inputs
    )
    if before is None:
        print()
        print("    No replayable inputs in that storage directory, so there")
        print("    is no way to tell whether a change made things worse.")
        print("    Refusing to apply. Run the agent a few times first, or")
        print("    apply by hand with: hugin create --edit")
        return 2
    if not before["scored"]:
        print()
        print("    Every baseline run failed before reaching the agent")
        print("    (provider outage). Refusing to apply against a baseline")
        print("    that measures nothing.")
        return 2

    backup = _snapshot(agent, files)
    applied = [p for p in proposals if _apply_one(agent, p, args.builder_model)]
    if not applied:
        print()
        print("    Nothing was applied.")
        shutil.rmtree(backup, ignore_errors=True)
        return 0

    print()
    print("    Replaying the edited agent on the same inputs ...")
    after = _replay(
        agent, storage, workroot / "after", args.limit, args.max_inputs
    )
    if after is None:
        print("    Could not replay the edited agent.")
        return _revert(
            agent, backup, files, "the edited agent could not be replayed"
        )

    comparison = compare_replays(before, after)
    if comparison["same_agent"]:
        # The edits ran but changed no bytes. Reporting "no regression" here
        # would be true and useless -- there was nothing to regress.
        print()
        print("    The agent is byte-identical to before: nothing changed.")
        shutil.rmtree(backup, ignore_errors=True)
        return 0

    if comparison["regressions"]:
        for row in comparison["regressions"]:
            print(
                f"    REGRESSED {row['fingerprint']}  "
                f"{row['before']} -> {row['after']}"
            )
        return _revert(
            agent,
            backup,
            files,
            f"{len(comparison['regressions'])} input(s) stopped finishing",
        )

    print()
    print(f"    Applied {len(applied)} change(s). No input regressed.")
    print(f"    Compared {comparison['compared']} input(s) before and after.")
    print()
    print(f"    To undo: restore from {backup}")
    print("    or, if the agent is in git:  git checkout -- <agent dir>")
    print()
    return 0


def _revert(agent: Path, backup: Path, files: List[str], reason: str) -> int:
    """Undo an applied change and say why."""
    restored = _restore(agent, backup, files)
    print()
    print(f"    Reverted: {reason}.")
    for key in restored:
        print(f"        restored {key}")
    print()
    print("    The agent is back to how it was. The proposals above may still")
    print("    be worth acting on by hand -- the replay only says this")
    print("    particular edit made things worse.")
    print()
    shutil.rmtree(backup, ignore_errors=True)
    return 1


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


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser.

    Split out from ``main`` so the defaults can be asserted directly --
    "apply is opt-in" is a safety property, and a test that cannot read the
    default cannot check it.
    """
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
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the proposals, showing a diff for each, and revert them "
        "if a replay shows any input stopped finishing",
    )
    parser.add_argument(
        "--max-inputs",
        type=int,
        default=5,
        help="Inputs to replay when checking an apply (default: 5)",
    )
    parser.add_argument(
        "--workdir",
        default="./storage/improve",
        help="Where before/after replay runs write their traces",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Run the improvement pass, applying only when asked to."""
    args = build_parser().parse_args(argv)

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

    if args.apply:
        return _guarded_apply(agent_path, proposals, str(storage_path), args)

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
