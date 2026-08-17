"""Run the agent builder against the golden set and score what it produced.

The builder is driven the way a user drives it -- ``hugin create --yes`` in a
subprocess, with its own storage directory -- so the harness measures the real
path rather than a reimplementation of it.

Scoring reuses what already exists: :func:`validate_files` decides whether the
generated agent is loadable, and :func:`analyze_traces` reads the *builder's
own* traces for turns and tokens. That means a scored run also exercises both
of those on real data, which is a second reason to prefer them over bespoke
counting here.

Costs real money: one full multi-stage build per case. Select a subset.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from gimle.hugin.analysis.traces import analyze_traces
from gimle.hugin.apps.agent_builder.tools.validate_agent import (
    collect_files,
    validate_files,
)
from gimle.hugin.evals.golden_set import EvalCase

# A build that has not finished by now is not going to teach us anything.
DEFAULT_TIMEOUT = 900


def _count(files: Dict[str, str], folder: str, suffix: str = ".yaml") -> int:
    """Count generated files of one kind."""
    return sum(
        1
        for key in files
        if key.startswith(f"{folder}/") and key.endswith(suffix)
    )


def _has_task_sequence(files: Dict[str, str]) -> bool:
    """True when any generated task chains into another.

    A cheap structural proxy for "this is a pipeline", usable before
    architecture selection exists.
    """
    import yaml

    for key, content in files.items():
        if not key.startswith("tasks/") or not key.endswith(".yaml"):
            continue
        try:
            document = yaml.safe_load(content)
        except yaml.YAMLError:
            continue
        if isinstance(document, dict) and (
            document.get("task_sequence") or document.get("next_task")
        ):
            return True
    return False


def score_output(case: EvalCase, output_path: Path) -> Dict[str, Any]:
    """Score a generated agent directory against what the case expected.

    Split out from running so it can be tested without a model, and so a
    directory built earlier can be rescored after the scoring rules change.
    """
    if not output_path.is_dir():
        return {"built": False, "validates": False, "reason": "no directory"}

    files = collect_files(str(output_path))
    if not files:
        return {"built": False, "validates": False, "reason": "empty"}

    report = validate_files(files, str(output_path))
    tools = _count(files, "tools")
    return {
        "built": True,
        "validates": report["ok"],
        "errors": len(report["errors"]),
        "warnings": len(report["warnings"]),
        "tools": tools,
        "meets_tool_expectation": tools >= case.expect_tools,
        "tasks": _count(files, "tasks"),
        "has_task_sequence": _has_task_sequence(files),
        "observed_imports": report.get("observed_imports", []),
        "error_checks": sorted(
            {finding["check"] for finding in report["errors"]}
        ),
    }


def _builder_cost(storage_path: Path) -> Dict[str, Any]:
    """Read turns and tokens out of the builder's own traces."""
    try:
        report = analyze_traces(str(storage_path), limit=20)
    except Exception:  # noqa: BLE001 - cost is reporting, never fatal
        return {}
    if not report.get("runs_analyzed"):
        return {}
    return {
        "builder_runs": report["runs_analyzed"],
        "builder_turns": report["model_turns"]["max"],
        "input_tokens": report["tokens"]["input"],
        "output_tokens": report["tokens"]["output"],
        "builder_unfinished": report["unfinished_rate"],
    }


def run_case(
    case: EvalCase,
    workdir: Path,
    builder_model: Optional[str] = None,
    agent_model: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """Build one case and score it. Returns a row for the report."""
    case_dir = workdir / case.name
    output_path = case_dir / "agent"
    case_dir.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "gimle.hugin.cli.cli",
        "create",
        "--yes",
        "--name",
        case.name,
        "--description",
        case.description,
        "--output",
        str(output_path),
    ]
    if builder_model:
        command += ["--builder-model", builder_model]
    if agent_model:
        command += ["--model", agent_model]

    # The builder writes its traces to a *relative* ./storage/agent_builder,
    # so running each case in its own cwd is what isolates them -- no env var
    # is involved, and inventing one would imply support that does not exist.
    environment = dict(os.environ)

    started = time.monotonic()
    timed_out = False
    returncode = -1
    try:
        completed = subprocess.run(
            command,
            cwd=str(case_dir),
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        returncode = completed.returncode
        tail = (completed.stderr or completed.stdout or "")[-600:]
    except subprocess.TimeoutExpired:
        timed_out = True
        tail = f"timed out after {timeout}s"

    elapsed = time.monotonic() - started
    row: Dict[str, Any] = {
        "case": case.name,
        "expect_architecture": case.expect_architecture,
        "tags": list(case.tags),
        "exit_code": returncode,
        "timed_out": timed_out,
        "elapsed_s": round(elapsed, 1),
    }
    row.update(score_output(case, output_path))
    row.update(_builder_cost(case_dir / "storage" / "agent_builder"))
    if not row.get("validates"):
        row["tail"] = tail.strip()[-400:]
    return row


def summarise(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate scored rows into the numbers worth comparing over time."""
    total = len(rows)
    if not total:
        return {"cases": 0}

    built = [row for row in rows if row.get("built")]
    valid = [row for row in rows if row.get("validates")]
    return {
        "cases": total,
        "built": len(built),
        "validates": len(valid),
        "build_rate": round(len(built) / total, 3),
        "validation_rate": round(len(valid) / total, 3),
        "meets_tool_expectation": sum(
            1 for row in rows if row.get("meets_tool_expectation")
        ),
        "produced_a_pipeline": sum(
            1 for row in rows if row.get("has_task_sequence")
        ),
        "timed_out": sum(1 for row in rows if row.get("timed_out")),
        "output_tokens": sum(row.get("output_tokens", 0) for row in rows),
        "median_elapsed_s": _median(
            [row.get("elapsed_s", 0) for row in rows]
        ),
        "failing_checks": sorted(
            {
                check
                for row in rows
                for check in row.get("error_checks", [])
            }
        ),
    }


def _median(values: List[float]) -> float:
    """Return the median, or 0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[middle], 1)
    return round((ordered[middle - 1] + ordered[middle]) / 2, 1)


def run_suite(
    cases: List[EvalCase],
    workdir: Path,
    builder_model: Optional[str] = None,
    agent_model: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
    on_case: Any = None,
) -> Dict[str, Any]:
    """Run every case and return ``{summary, rows}``."""
    rows = []
    for case in cases:
        row = run_case(
            case,
            workdir,
            builder_model=builder_model,
            agent_model=agent_model,
            timeout=timeout,
        )
        rows.append(row)
        if on_case:
            on_case(row)
    return {"summary": summarise(rows), "rows": rows}


def write_report(report: Dict[str, Any], path: Path) -> None:
    """Persist a report so two runs can be compared."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def compare(before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
    """Describe how two summaries differ, for gating a prompt change.

    A prompt change is meant to be judged on whether generation got better.
    Without this, "it looked fine" is the only available verdict.
    """
    lines = []
    for key in (
        "validation_rate",
        "build_rate",
        "meets_tool_expectation",
        "produced_a_pipeline",
        "output_tokens",
    ):
        old = before.get("summary", {}).get(key)
        new = after.get("summary", {}).get(key)
        if old is None or new is None or old == new:
            continue
        direction = "+" if new > old else ""
        lines.append(f"{key}: {old} -> {new} ({direction}{new - old})")
    return lines or ["no change in the compared metrics"]
