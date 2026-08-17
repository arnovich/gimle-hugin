#!/usr/bin/env python3
"""Hugin CLI - Main entry point for all Hugin commands."""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from gimle.hugin import __version__
from gimle.hugin.cli.ui import HUGIN_LOGO
from gimle.hugin.sandbox.sandbox import DEFAULT_SANDBOX_ROOT, sandbox_root_for

VERSION = __version__

BANNER = HUGIN_LOGO

APPS_GITHUB_URL = "https://github.com/anthropics/hugin-apps"


def _non_negative_int(value: str) -> int:
    """Parse a non-negative command-line integer."""
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


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

    return create_main(args.extra_args)


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


def cmd_dream(args: argparse.Namespace) -> int:
    """Consolidate episodic memory into scoped Learning artifacts."""
    from pathlib import Path

    import gimle.hugin.dreaming as dreaming_pkg
    from gimle.hugin.agent.environment import Environment
    from gimle.hugin.dreaming.consolidate import run_dream
    from gimle.hugin.storage.local import LocalStorage

    storage_path = args.storage_path or "./storage"
    agent_dir = Path(dreaming_pkg.__file__).resolve().parent / "agent"
    storage = LocalStorage(base_path=storage_path)
    environment = Environment.load(str(agent_dir), storage=storage)

    if args.model:
        environment.config_registry.get("dreamer").llm_model = args.model

    results = run_dream(
        environment,
        config=args.config,
        task=args.task,
        max_steps=args.max_steps or 20,
        dry_run=args.dry_run,
    )

    verb = "would save" if args.dry_run else "saved"
    print(f"Dream complete: {verb} {len(results)} learning(s).")
    for result in results:
        scope = result.get("scope_config") or "?"
        task_scope = result.get("scope_task") or "*"
        print(f"  - {scope}/{task_scope}: {result.get('id')}")
    return 0


def cmd_prune_learnings(args: argparse.Namespace) -> int:
    """Preview or apply conservative pruning of superseded learnings."""
    from gimle.hugin.dreaming.prune import prune_learnings
    from gimle.hugin.storage.local import LocalStorage

    storage_path = args.storage_path or "./storage"
    storage = LocalStorage(base_path=storage_path)
    candidates = prune_learnings(
        storage,
        retention_days=args.retention_days,
        apply=args.apply,
    )

    verb = "Pruned" if args.apply else "Dry run: would prune"
    print(
        f"{verb} {len(candidates)} superseded learning(s) retained for at "
        f"least {args.retention_days} day(s)."
    )
    for candidate in candidates:
        replacements = ", ".join(candidate.superseded_by)
        print(
            f"  - {candidate.artifact_id} (superseded "
            f"{candidate.superseded_at} by {replacements})"
        )
    if not args.apply:
        print("No changes made. Re-run with --apply to delete these learnings.")
    return 0


def cmd_install_models(args: argparse.Namespace) -> int:
    """Install Ollama models."""
    from gimle.hugin.cli.install_ollama_models import main as install_main

    sys.argv = ["hugin install-models"] + args.extra_args
    return install_main()


def cmd_eval(args: argparse.Namespace) -> int:
    """Run the agent builder against the golden set and score the results."""
    from gimle.hugin.evals.golden_set import select
    from gimle.hugin.evals.harness import compare, run_suite, write_report

    if args.list:
        for case in select():
            tags = ",".join(case.tags) or "-"
            print(f"    {case.name:<22} {case.expect_architecture:<12} {tags}")
        return 0

    cases = select(names=args.case, tag=args.tag, limit=args.limit)
    if not cases:
        print("    No cases matched.")
        return 2

    workdir = Path(args.workdir) if args.workdir else None
    if workdir is None:
        workdir = Path("./eval-runs")
    workdir.mkdir(parents=True, exist_ok=True)

    print()
    print(f"    Running {len(cases)} case(s). Each is a full build.")
    print()

    def announce(row: dict) -> None:
        mark = "ok  " if row.get("validates") else "FAIL"
        print(
            f"    {mark} {row['case']:<22} "
            f"{row.get('elapsed_s', 0):>6.0f}s  "
            f"tools={row.get('tools', 0)}  "
            f"out_tokens={row.get('output_tokens', 0)}"
        )

    report = run_suite(
        cases,
        workdir,
        builder_model=args.builder_model,
        agent_model=args.model,
        timeout=args.timeout,
        on_case=announce,
    )

    summary = report["summary"]
    print()
    print(
        f"    validates {summary['validates']}/{summary['cases']}"
        f"   built {summary['built']}/{summary['cases']}"
    )
    print(
        f"    output tokens {summary['output_tokens']}"
        f"   median {summary['median_elapsed_s']}s"
    )
    if summary["failing_checks"]:
        print(f"    failing checks: {', '.join(summary['failing_checks'])}")

    if args.out:
        write_report(report, Path(args.out))
        print(f"    report: {args.out}")

    if args.baseline:
        try:
            baseline = json.loads(Path(args.baseline).read_text())
        except (OSError, json.JSONDecodeError) as error:
            print(f"    could not read baseline: {error}")
            return 1
        print()
        print("    vs baseline:")
        for line in compare(baseline, report):
            print(f"      {line}")

    print()
    return 0 if summary["validates"] == summary["cases"] else 1


def cmd_analyze(args: argparse.Namespace) -> int:
    """Report on an agent's historic runs, without an LLM in the loop."""
    from gimle.hugin.analysis.traces import (
        TraceReadError,
        analyze_traces,
        default_storage_path,
    )

    storage_path = args.storage_path
    if not storage_path and args.agent_path:
        storage_path = default_storage_path(args.agent_path)
    if not storage_path:
        print("    Pass --storage-path (the directory the agent ran against).")
        return 2

    try:
        report = analyze_traces(
            storage_path, limit=args.limit, agent_name=args.agent
        )
    except TraceReadError as error:
        print(f"    {error}")
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    _print_analysis(report, storage_path)
    return 0


def _print_analysis(report: dict, storage_path: str) -> None:
    """Render the report for a terminal."""
    if not report.get("runs_analyzed"):
        print(f"    {report.get('note', 'No runs found.')}")
        return

    turns = report["model_turns"]
    tokens = report["tokens"]
    success = report["self_reported_success_rate"]
    print()
    print(f"    {storage_path}: {report['runs_analyzed']} run(s)")
    print()
    print(
        f"    finished           {report['completed']}"
        f"/{report['runs_analyzed']}"
        f"   (unfinished {report['unfinished_rate']:.0%})"
    )
    if success is not None:
        print(f"    self-reported ok   {success:.0%}")
    print(
        f"    model turns        p50 {turns['p50']}  p90 {turns['p90']}"
        f"  max {turns['max']}"
    )
    print(
        f"    output tokens      {tokens['output']}"
        f"   ({tokens['output_per_run']}/run)"
    )
    if report["unresolved_template_turns"]:
        print(
            "    unrendered {{ }}   "
            f"{report['unresolved_template_turns']} turn(s)"
        )

    if report["tools"]:
        print()
        print("    tool                     calls  errors  max result")
        for row in report["tools"][:12]:
            print(
                f"      {row['name'][:22]:<22} {row['calls']:>6}"
                f" {row['errors']:>7} {row['max_result_chars']:>11}"
            )
            for error in row["top_errors"]:
                print(f"          {error['count']}x {error['value'][:60]}")

    for label, key in (
        ("never called", "dead_tools"),
        ("looping", "loops_detected"),
        ("oversized results", "oversized_results"),
    ):
        entries = report.get(key) or []
        if not entries:
            continue
        rendered = ", ".join(
            (
                entry
                if isinstance(entry, str)
                else f"{entry['value']}" f" ({entry['count']})"
            )
            for entry in entries
        )
        print(f"\n    {label}: {rendered}")

    if report.get("caveats"):
        print()
        for note in report["caveats"]:
            print(f"    note: {note}")
    print()


def cmd_validate(args: argparse.Namespace) -> int:
    """Statically validate one or more agent directories."""
    from gimle.hugin.apps.agent_builder.tools.validate_agent import (
        AgentReadError,
        collect_files,
        validate_files,
    )

    paths = [Path(p) for p in args.paths]
    root_failures = 0
    if args.recursive:
        discovered = []
        for parent in paths:
            if not parent.is_dir():
                # An unreadable or absent path used to abort the CI gate with
                # a bare iterdir() traceback that read like a validator crash.
                print(f"    error {parent}: not a directory")
                root_failures += 1
                continue
            try:
                children = sorted(parent.iterdir())
            except OSError as error:
                print(f"    error {parent}: {error}")
                root_failures += 1
                continue
            discovered += [
                child
                for child in children
                if child.is_dir()
                and ((child / "configs").is_dir() or (child / "tasks").is_dir())
            ]
        if not discovered:
            # Exiting 0 here made the CI gate a silent no-op the moment a
            # directory layout changed.
            print("    No agent directories found. Nothing was validated.")
            return 1
        paths = discovered

    failed = 0
    for path in paths:
        try:
            files = collect_files(str(path))
        except AgentReadError as error:
            print(f"    FAIL {path}: {error}")
            failed += 1
            continue
        if not files:
            print(f"    {path}: no agent files found")
            failed += 1
            continue

        report = validate_files(files, str(path))
        status = "OK  " if report["ok"] else "FAIL"
        print(f"    {status} {path}  ({report['summary']})")
        for finding in report["errors"]:
            print(f"           error   {finding['file']}: {finding['message']}")
        if not args.quiet:
            for finding in report["warnings"]:
                print(
                    f"           warning {finding['file']}: "
                    f"{finding['message']}"
                )
        if report["observed_imports"] and not args.quiet:
            joined = ", ".join(report["observed_imports"])
            print(f"           requires: {joined}")
        if not report["ok"]:
            failed += 1

    if len(paths) > 1:
        print()
        print(f"    {len(paths) - failed}/{len(paths)} agents valid")
    return 1 if failed or root_failures else 0


def cmd_version(args: argparse.Namespace) -> int:
    """Show version information."""
    print(BANNER)
    print(f"    Hugin Agent Framework v{VERSION}")
    print()
    return 0


def reap_sandboxes_quietly(root: str = DEFAULT_SANDBOX_ROOT) -> None:
    """Best-effort reap of abandoned local sandbox workspaces at startup.

    The primary teardown mechanism: it runs on every ``hugin`` invocation so an
    abrupt exit (SIGKILL, sleep) that skipped ``Session.close`` still self-heals
    within one invocation. Never raises — cleanup must not break the command.
    """
    try:
        import time

        from gimle.hugin.sandbox.reaper import (
            reap_abandoned_containers,
            reap_abandoned_networks,
            reap_local_workspaces,
        )

        now = time.time()
        reap_local_workspaces(root, now=now)
        # Container reaping is daemon-optional: a no-op without the docker SDK
        # or a running daemon, so local/ssh-only users pay nothing here.
        reap_abandoned_containers(now=now)
        # Then any egress network the (now-gone) proxy container was on. After
        # the container sweep so the network is detachable and removable.
        reap_abandoned_networks(now=now)
    except Exception:  # cleanup is best-effort and must never break a command
        pass


def cmd_sandbox(args: argparse.Namespace) -> int:
    """List or prune local sandbox workspaces."""
    import time

    from gimle.hugin.sandbox.reaper import (
        list_local_workspaces,
        reap_abandoned_containers,
        reap_abandoned_networks,
        reap_local_workspaces,
    )

    root = args.root or sandbox_root_for(getattr(args, "storage_path", None))
    now = time.time()

    if args.action == "prune":
        reaped = reap_local_workspaces(root, now=now)
        containers = reap_abandoned_containers(now=now)
        networks = reap_abandoned_networks(now=now)  # after the containers
        if reaped:
            print(f"Reaped {len(reaped)} abandoned workspace(s):")
            for name in reaped:
                print(f"  {name}")
        else:
            print("No abandoned workspaces to reap.")
        if containers:
            print(f"Reaped {len(containers)} abandoned container(s):")
            for name in containers:
                print(f"  {name}")
        if networks:
            print(f"Reaped {len(networks)} abandoned egress network(s):")
            for name in networks:
                print(f"  {name}")
        return 0

    # default: list
    infos = list_local_workspaces(root, now=now)
    if not infos:
        print(f"No sandbox workspaces under {root}")
        return 0
    print(f"{'SESSION':<40} {'PID':>8}  {'OWNER':<7} {'AGE':>8}")
    for info in infos:
        owner = "alive" if info.alive else "dead"
        pid = str(info.pid) if info.pid is not None else "-"
        print(f"{info.name:<40} {pid:>8}  {owner:<7} {int(info.age_s):>7}s")
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
        add_help=False,
    )
    create_parser.add_argument(
        "extra_args", nargs=argparse.REMAINDER, help="Additional arguments"
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

    # dream command (offline memory consolidation)
    dream_parser = subparsers.add_parser(
        "dream",
        help="Consolidate episodic memory into learnings",
        description=(
            "Replay saved insights and distil them into scoped Learning "
            "artifacts that are injected into future prompts."
        ),
    )
    dream_parser.add_argument(
        "-s", "--storage-path", help="Path to agent storage"
    )
    dream_parser.add_argument(
        "--config", help="Consolidate a single config scope (default: all)"
    )
    dream_parser.add_argument(
        "--task", help="Restrict to a single task within the scope"
    )
    dream_parser.add_argument(
        "--max-steps",
        type=int,
        default=20,
        help="Per-scope step budget for the dream worker",
    )
    dream_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Produce learnings but persist nothing",
    )
    dream_parser.add_argument(
        "--model", help="Override the dream worker's llm_model"
    )
    dream_parser.set_defaults(func=cmd_dream)

    # prune-learnings command (conservative semantic-memory lifecycle)
    prune_learnings_parser = subparsers.add_parser(
        "prune-learnings",
        help="Preview or delete retained superseded learnings",
        description=(
            "Find structurally superseded Learning artifacts whose retention "
            "window elapsed. The command is a dry run unless --apply is set."
        ),
    )
    prune_learnings_parser.add_argument(
        "-s", "--storage-path", help="Path to agent storage"
    )
    prune_learnings_parser.add_argument(
        "--retention-days",
        type=_non_negative_int,
        default=30,
        help="Days to retain a learning after supersession (default: 30)",
    )
    prune_learnings_parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete the reported candidates; without this flag, preview only",
    )
    prune_learnings_parser.set_defaults(func=cmd_prune_learnings)

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

    # eval command
    eval_parser = subparsers.add_parser(
        "eval",
        help="Score the agent builder against a golden set of descriptions",
        description="Run the builder end to end for each description and "
        "score what it produced. Costs one full build per case, so select a "
        "subset. Use --out and --baseline to compare two runs.",
    )
    eval_parser.add_argument(
        "--case", action="append", help="Run only this case (repeatable)"
    )
    eval_parser.add_argument("--tag", help="Run only cases with this tag")
    eval_parser.add_argument(
        "--limit", type=int, default=0, help="Cap the number of cases"
    )
    eval_parser.add_argument(
        "--list", action="store_true", help="List the cases and exit"
    )
    eval_parser.add_argument("--model", help="Model for the generated agents")
    eval_parser.add_argument(
        "--builder-model", help="Model that does the building"
    )
    eval_parser.add_argument(
        "--workdir", help="Where to build (default ./eval-runs)"
    )
    eval_parser.add_argument(
        "--timeout", type=int, default=900, help="Per-case timeout in seconds"
    )
    eval_parser.add_argument("--out", help="Write the JSON report here")
    eval_parser.add_argument(
        "--baseline", help="Compare against a previous report"
    )
    eval_parser.set_defaults(func=cmd_eval)

    # analyze command
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Report on an agent's historic runs",
        description="Summarise persisted runs: success and completion rates, "
        "model turns, tokens, per-tool error rates, tools that were never "
        "called, loops, and oversized tool results. Reads storage only -- no "
        "model is called.",
    )
    analyze_parser.add_argument(
        "agent_path",
        nargs="?",
        help="Agent directory, used to guess --storage-path",
    )
    analyze_parser.add_argument(
        "-s", "--storage-path", help="Storage directory the agent ran against"
    )
    analyze_parser.add_argument(
        "--agent", help="Only runs whose config has this name"
    )
    analyze_parser.add_argument(
        "--limit",
        type=_non_negative_int,
        default=50,
        help="Most recent matching runs to read",
    )
    analyze_parser.add_argument(
        "--json", action="store_true", help="Emit the raw report as JSON"
    )
    analyze_parser.set_defaults(func=cmd_analyze)

    # validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Statically validate an agent directory",
        description="Check an agent's structure, template and tool "
        "references, prompt variables and tool contracts. Parses files "
        "without importing or running them.",
    )
    validate_parser.add_argument(
        "paths", nargs="+", help="Agent directories to validate"
    )
    validate_parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Treat each path as a parent of agent directories",
    )
    validate_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Show errors only, suppressing warnings and dependencies",
    )
    validate_parser.set_defaults(func=cmd_validate)

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

    # sandbox command
    sandbox_parser = subparsers.add_parser(
        "sandbox",
        help="Inspect or clean up local sandbox workspaces",
        description="List or prune the per-session workspaces the bash tool "
        "creates on the local backend.",
    )
    sandbox_parser.add_argument(
        "action",
        nargs="?",
        choices=["list", "prune"],
        default="list",
        help="'list' shows workspaces; 'prune' removes abandoned ones",
    )
    sandbox_parser.add_argument(
        "--root",
        default=None,
        help=f"Sandbox root (default: {DEFAULT_SANDBOX_ROOT})",
    )
    sandbox_parser.set_defaults(func=cmd_sandbox)

    # The creator owns its command-line interface. Split at the subcommand so
    # option-style arguments such as ``--name`` are forwarded verbatim instead
    # of being rejected by this outer parser.
    raw_args = sys.argv[1:]
    create_args: List[str] = []
    create_index = next(
        (
            index
            for index, value in enumerate(raw_args)
            if value == "create"
            and all(arg in {"-v", "--env"} for arg in raw_args[:index])
        ),
        None,
    )
    if create_index is not None:
        create_args = raw_args[create_index + 1 :]
        raw_args = raw_args[: create_index + 1]

    # Parse arguments
    args = parser.parse_args(raw_args)
    if args.command == "create":
        args.extra_args = create_args

    # Self-heal: reap abandoned local sandbox workspaces on every invocation,
    # resolving the root from --storage-path so it matches where the tool wrote.
    reap_sandboxes_quietly(
        sandbox_root_for(getattr(args, "storage_path", None))
    )

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
