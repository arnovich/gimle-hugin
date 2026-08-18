"""Run the golden-set eval and print a report.

A script rather than a ``hugin`` subcommand, and under ``tests/`` rather than
in the package, because this measures *the builder* -- a maintainer's question,
not a user's. Shipping it would put fifteen hardcoded descriptions and a
subprocess driver into every install of Hugin for no one's benefit.

    uv run python -m tests.evals.run --list
    uv run python -m tests.evals.run --tag cheap
    uv run python -m tests.evals.run --out before.json
    uv run python -m tests.evals.run --out after.json --baseline before.json

Each case is one full multi-stage build, so it costs real money. Select a
subset unless you mean it.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from tests.evals.golden_set import select
from tests.evals.harness import compare, run_suite, write_report


def _announce(row: Dict[str, Any]) -> None:
    """Print one case's outcome as it completes."""
    if row.get("infrastructure_failure"):
        mark = "SKIP"  # the provider, not the builder
    elif row.get("validates"):
        mark = "ok  "
    else:
        mark = "FAIL"
    print(
        f"    {mark} {row['case']:<22} "
        f"{row.get('elapsed_s', 0):>6.0f}s  "
        f"tools={row.get('tools', 0)}  "
        f"out_tokens={row.get('output_tokens', 0)}"
    )


def main() -> int:
    """Parse arguments, run the selected cases, and report."""
    parser = argparse.ArgumentParser(
        description="Score the agent builder against a golden set."
    )
    parser.add_argument("--case", action="append", help="Run only this case")
    parser.add_argument("--tag", help="Run only cases with this tag")
    parser.add_argument("--limit", type=int, default=0, help="Cap the count")
    parser.add_argument("--list", action="store_true", help="List and exit")
    parser.add_argument("--model", help="Model for the generated agents")
    parser.add_argument("--builder-model", help="Model that does the building")
    parser.add_argument("--workdir", default="./eval-runs", help="Build here")
    parser.add_argument("--timeout", type=int, default=900, help="Per case")
    parser.add_argument("--out", help="Write the JSON report here")
    parser.add_argument("--baseline", help="Compare against a previous report")
    args = parser.parse_args()

    if args.list:
        for case in select():
            tags = ",".join(case.tags) or "-"
            print(f"    {case.name:<22} {case.expect_architecture:<12} {tags}")
        return 0

    cases = select(names=args.case, tag=args.tag, limit=args.limit)
    if not cases:
        print("    No cases matched.")
        return 2

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    print()
    print(f"    Running {len(cases)} case(s). Each is a full build.")
    print()

    report = run_suite(
        cases,
        workdir,
        builder_model=args.builder_model,
        agent_model=args.model,
        timeout=args.timeout,
        on_case=_announce,
    )

    summary = report["summary"]
    print()
    print(
        f"    validates {summary['validates']}/{summary['scored']}"
        f"   built {summary['built']}/{summary['scored']}"
    )
    if summary["infrastructure_failures"]:
        print(
            f"    {summary['infrastructure_failures']} case(s) excluded: the "
            "provider failed, so the builder was never measured"
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


if __name__ == "__main__":
    sys.exit(main())
