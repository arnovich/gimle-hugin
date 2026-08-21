"""Re-run an agent on inputs it actually saw, and compare the outcomes.

`analyze_traces` says what an agent did. It cannot say whether a change to the
agent *helped*, because the rewritten agent has no history: there is nothing to
compare "after" against. Replay is the missing half -- harvest the task
parameters real runs used, run the agent on those same inputs again, and put
the two side by side.

**The harvested inputs are raw user data, and are handled differently from
everything else in this package.** The rest of `analysis` exists to produce
something safe to show a model: arguments are hashed, errors are reduced to
signatures, every string is redacted. A replay needs the opposite -- the actual
values, or it is not replaying anything. So the harvest is a library and CLI
function only, never a builder tool, and the values never enter an agent's
context. Only the *report* travels, and that carries hashes.

Runs are subprocesses rather than in-process sessions on purpose. `Tool.registry`
is a process-global keyed by tool name, so replaying one agent repeatedly in a
single process re-registers the same names against different module objects --
the exact hazard that made an earlier test suite order-dependent. A subprocess
per run has no such state to get wrong.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from gimle.hugin.analysis.provider_errors import is_provider_failure
from gimle.hugin.analysis.traces import TraceReadError, read_runs

# A replay is meant to be a quick regression check, not a second eval suite.
DEFAULT_MAX_INPUTS = 10

# Per run. A replayed agent that has not finished by here is not going to.
DEFAULT_MAX_STEPS = 40
DEFAULT_TIMEOUT_SECONDS = 300

# Not part of what makes an agent that agent: its own run history and
# build artefacts change without the agent changing.
_DIGEST_SKIP = frozenset(
    {"storage", "artifacts", "__pycache__", ".git", ".hugin-manifest.json"}
)


def _parameter_values(task: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the values a run was actually given.

    A task's parameter carries its schema and its value in the same mapping,
    so the declared type and description have to be dropped here -- replaying
    means supplying what the user supplied, not what the schema permits.
    """
    values: Dict[str, Any] = {}
    parameters = task.get("parameters")
    if not isinstance(parameters, dict):
        return values
    for name, spec in parameters.items():
        if isinstance(spec, dict):
            if "value" in spec and spec["value"] is not None:
                values[str(name)] = spec["value"]
        elif spec is not None:
            # The simple format: parameters are plain values.
            values[str(name)] = spec
    return values


def agent_digest(agent_path: str) -> str:
    """Return a hash of every file in an agent directory.

    A before/after comparison is only meaningful if the two sides measured
    different agents. Recording which version produced each report makes
    "nothing was applied" detectable instead of arriving as the reassuring
    "no input changed outcome".
    """
    root = Path(agent_path).expanduser()
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part in _DIGEST_SKIP for part in relative.parts):
            continue
        digest.update(str(relative).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def fingerprint(values: Dict[str, Any]) -> str:
    """Return a stable short hash of a parameter set.

    Reports quote this instead of the values, so a replay summary can be
    pasted into a terminal, a PR or a model's context without carrying
    whatever the user typed.
    """
    encoded = json.dumps(values, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:12]


def harvest_inputs(
    storage_path: str,
    limit: int = 50,
    agent_name: Optional[str] = None,
    max_inputs: int = DEFAULT_MAX_INPUTS,
) -> List[Dict[str, Any]]:
    """Return the distinct task inputs found in an agent's run history.

    **The returned values are unredacted user input.** Callers must treat the
    result as sensitive: write it where the user controls it, and never put it
    in a model's context.

    Args:
        storage_path: A Hugin storage directory.
        limit: Most recent runs to read.
        agent_name: Only runs whose config has this name.
        max_inputs: Cap on distinct inputs returned.

    Returns:
        Newest first, deduplicated by (task, parameter values). A run whose
        task took no parameters still counts as one input -- the prompt alone
        is a valid thing to replay.
    """
    root = Path(storage_path).expanduser()
    runs = read_runs(str(root), limit=limit, agent_name=agent_name)

    seen = set()
    harvested: List[Dict[str, Any]] = []
    for run in runs:
        task = run.get("task")
        if not isinstance(task, dict) or not task.get("name"):
            continue
        values = _parameter_values(task)
        key = (task["name"], fingerprint(values))
        if key in seen:
            continue
        seen.add(key)
        harvested.append(
            {
                "task": str(task["name"]),
                "parameters": values,
                "fingerprint": fingerprint(values),
                "observed_finish_type": run.get("finish_type"),
            }
        )
        if len(harvested) >= max_inputs:
            break
    return harvested


def replay_inputs(
    agent_path: str,
    inputs: List[Dict[str, Any]],
    workdir: str,
    max_steps: int = DEFAULT_MAX_STEPS,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Run ``agent_path`` once per harvested input and report each outcome.

    Each run gets its own storage directory so the outcomes can be read back
    with the same code that reads real history -- a replay is scored exactly
    the way production runs are, rather than by a second, divergent rule.

    Returns:
        A report keyed by input fingerprint. Parameter *values* are not in it.
    """
    agent = Path(agent_path).expanduser()
    if not agent.is_dir():
        raise TraceReadError(f"no such agent directory: {agent}")

    root = Path(workdir).expanduser()
    root.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    for index, item in enumerate(inputs):
        storage = root / f"run-{index:02d}"
        command = [
            sys.executable,
            "-m",
            "gimle.hugin.cli.cli",
            "run",
            "--task",
            item["task"],
            "--task-path",
            str(agent),
            "--storage-path",
            str(storage),
            "--max-steps",
            str(max_steps),
        ]
        if item["parameters"]:
            command += ["--parameters", json.dumps(item["parameters"])]
        if model:
            command += ["--model", model]

        timed_out = False
        returncode = -1
        output = ""
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout
            )
            returncode = completed.returncode
            output = (completed.stderr or "") + (completed.stdout or "")
        except subprocess.TimeoutExpired:
            timed_out = True

        scored = _score_run(storage)
        # A provider outage is not the agent failing. Scored as an outcome it
        # reads as a regression, and in an apply loop would revert a change
        # that was fine.
        provider_failed = not scored["finished"] and is_provider_failure(output)
        results.append(
            {
                **scored,
                "task": item["task"],
                "fingerprint": item["fingerprint"],
                "exit_code": returncode,
                "timed_out": timed_out,
                "provider_failure": provider_failed,
            }
        )

    scorable = [r for r in results if not r["provider_failure"]]
    return {
        "agent_path": str(agent),
        "agent_digest": agent_digest(str(agent)),
        "inputs": len(inputs),
        # Rates are over what was actually asked of the agent: an outage is
        # excluded from the denominator, never counted as a failure.
        "scored": len(scorable),
        "provider_failures": len(results) - len(scorable),
        "finished": sum(1 for r in scorable if r["finished"]),
        "succeeded": sum(1 for r in scorable if r["finish_type"] == "success"),
        "results": results,
    }


def _score_run(storage: Path) -> Dict[str, Any]:
    """Read one replayed run's outcome back out of its storage."""
    blank = {
        "finished": False,
        "finish_type": None,
        "model_turns": 0,
        "output_tokens": 0,
    }
    try:
        runs = read_runs(str(storage), limit=1)
    except TraceReadError:
        return blank
    if not runs:
        return blank
    run = runs[0]
    return {
        "finished": bool(run.get("completed")),
        "finish_type": run.get("finish_type"),
        "model_turns": run.get("model_turns", 0),
        "output_tokens": run.get("output_tokens", 0),
    }


def compare_replays(
    before: Dict[str, Any], after: Dict[str, Any]
) -> Dict[str, Any]:
    """Put two replay reports side by side, per input.

    Matched on fingerprint, so a comparison across different input sets
    reports what it could not match rather than silently comparing totals of
    different things.
    """

    def usable(results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Drop inputs whose run never reached the agent."""
        return {
            r["fingerprint"]: r
            for r in results
            if not r.get("provider_failure")
        }

    before_by_id = usable(before.get("results", []))
    after_by_id = usable(after.get("results", []))
    shared = sorted(set(before_by_id) & set(after_by_id))

    rows = []
    for key in shared:
        was, now = before_by_id[key], after_by_id[key]
        rows.append(
            {
                "fingerprint": key,
                "task": now.get("task"),
                "before": was.get("finish_type"),
                "after": now.get("finish_type"),
                "turns_delta": now.get("model_turns", 0)
                - was.get("model_turns", 0),
                "verdict": _verdict(was, now),
            }
        )

    before_digest = before.get("agent_digest")
    after_digest = after.get("agent_digest")
    return {
        "compared": len(rows),
        "before_digest": before_digest,
        "after_digest": after_digest,
        # Two replays of the *same* files cannot show a change. Without this
        # a failed apply reports "no input changed outcome", which reads as
        # "the change was safe" rather than "there was no change".
        "same_agent": bool(before_digest) and before_digest == after_digest,
        "unmatched_before": sorted(set(before_by_id) - set(after_by_id)),
        "unmatched_after": sorted(set(after_by_id) - set(before_by_id)),
        "regressions": [r for r in rows if r["verdict"] == "regressed"],
        "improvements": [r for r in rows if r["verdict"] == "improved"],
        "rows": rows,
    }


def _verdict(before: Dict[str, Any], after: Dict[str, Any]) -> str:
    """Classify one input's before/after outcome.

    Deliberately coarse. It reports whether the run *finished*, not whether it
    finished well: `finish_type` is the agent's own verdict on itself, so a
    finer reading of it would be reading a self-grade. Turn counts are carried
    alongside for a human to weigh, and are not part of the verdict.
    """
    was, now = bool(before.get("finished")), bool(after.get("finished"))
    if was == now:
        return "unchanged"
    return "improved" if now else "regressed"
