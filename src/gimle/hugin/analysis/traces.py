"""Read historic agent runs from a storage directory and summarise them.

Deliberately **read-only and LLM-free**. It answers "what is wrong with this
agent" from runs that already happened, which is useful on day one, on agents
nobody generated, and at zero token cost.

Scoped to :class:`LocalStorage` on purpose. ``load_interaction_metadata`` --
the cheap reader this needs -- exists only there, and no second backend exists
to generalise against; inventing a ``Storage`` interface for one implementation
would be a guess. Widening it later is a smaller change than unpicking the
wrong abstraction.

It also does not use ``Storage.load_interaction(uuid, stack)``: that requires a
``Stack``, which does not exist for a foreign agent's historic run, and caches
every result forever. This follows what ``hugin monitor`` already does --
read the agent JSON for its interaction list, then the raw interaction JSON.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from gimle.hugin.analysis.redaction import (
    error_signature,
    redact,
    top_counts,
)

# A tool result far past this is a design problem: every byte is re-sent to the
# model on every subsequent turn of a stack that is never truncated.
OVERSIZED_RESULT_CHARS = 8_000

# A tool called with identical arguments this many times in one run is looping
# rather than working.
LOOP_THRESHOLD = 3


class TraceReadError(Exception):
    """The storage directory could not be read as Hugin runs."""


def _agent_dir(storage_path: Path) -> Path:
    """Return the agents directory, or raise a legible error."""
    agents = storage_path / "agents"
    if not agents.is_dir():
        raise TraceReadError(
            f"{storage_path} does not look like a Hugin storage directory "
            "(no agents/ inside it)"
        )
    return agents


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load one JSON file, returning None rather than raising."""
    try:
        with open(path, "r") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _interactions(
    storage_path: Path, agent: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Return an agent's interactions, in order, as ``{type, data}`` dicts."""
    uuids = (agent.get("stack") or {}).get("interactions") or []
    found = []
    for uuid in uuids:
        raw = _load_json(storage_path / "interactions" / str(uuid))
        if raw:
            found.append(raw)
    return found


def _config_tools(agent: Dict[str, Any]) -> List[str]:
    """Return the tool names the agent's config granted."""
    entries = (agent.get("config") or {}).get("tools") or []
    return [str(entry).split(":")[0] for entry in entries if entry]


def _args_fingerprint(args: Any) -> str:
    """Hash tool arguments so repeats are countable without storing values.

    Loop detection needs to know two calls were identical; it does not need to
    know what they contained, and the contents are user data.
    """
    try:
        blob = json.dumps(args, sort_keys=True, default=str)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        blob = str(args)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def _result_text(result: Any) -> str:
    """Render a tool result to text for size accounting."""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return str(result)


def _summarise_run(
    agent: Dict[str, Any], interactions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Reduce one agent's interaction list to per-run facts."""
    run: Dict[str, Any] = {
        "agent_id": agent.get("uuid"),
        "config": (agent.get("config") or {}).get("name"),
        "model_turns": 0,
        "finish_type": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "tool_calls": [],
        "unresolved_template_turns": 0,
    }

    # ToolResult carries neither the tool name nor (reliably) a tool_call_id --
    # verified against real storage, where both are null on the finish path. A
    # result is therefore attributed to the most recent ToolCall before it,
    # which is the order the stack is written in.
    pending: Optional[Dict[str, Any]] = None

    for entry in interactions:
        kind = entry.get("type")
        data = entry.get("data") or {}

        if kind == "OracleResponse":
            run["model_turns"] += 1
            response = data.get("response") or {}
            run["input_tokens"] += int(response.get("input_tokens") or 0)
            run["output_tokens"] += int(response.get("output_tokens") or 0)
            rendered = data.get("rendered_user_message")
            system = data.get("rendered_system_prompt")
            if _has_unrendered_placeholder(rendered) or (
                _has_unrendered_placeholder(system)
            ):
                run["unresolved_template_turns"] += 1

        elif kind == "ToolCall":
            pending = {
                "tool": data.get("tool") or "<unnamed>",
                "args": _args_fingerprint(data.get("args")),
                "is_error": None,
                "result_chars": 0,
                "error": None,
            }
            run["tool_calls"].append(pending)

        elif kind == "ToolResult":
            if pending is None:
                continue
            text = _result_text(data.get("result"))
            pending["result_chars"] = len(text)
            pending["is_error"] = bool(data.get("is_error"))
            if pending["is_error"]:
                pending["error"] = error_signature(
                    _error_text(data.get("result"))
                )
            pending = None

        elif kind == "TaskResult":
            run["finish_type"] = data.get("finish_type")

    run["completed"] = run["finish_type"] is not None
    return run


def _error_text(result: Any) -> str:
    """Pull the most error-like string out of a tool result."""
    if isinstance(result, dict):
        for key in ("error", "message", "detail", "traceback"):
            value = result.get(key)
            if isinstance(value, str):
                return value
    return _result_text(result)


def _has_unrendered_placeholder(value: Any) -> bool:
    """Return True when a rendered prompt still contains Jinja syntax.

    Only meaningful when HUGIN_CAPTURE_RENDERED_PROMPTS was on for the run;
    otherwise these fields are absent and this is simply never true.
    """
    if value is None:
        return False
    return "{{" in _result_text(value)


def read_runs(storage_path: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Return per-run summaries, newest first, capped at ``limit``."""
    root = Path(storage_path).expanduser()
    agents = _agent_dir(root)

    files = [path for path in agents.iterdir() if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)

    runs = []
    for path in files[:limit]:
        agent = _load_json(path)
        if not agent:
            continue
        summary = _summarise_run(agent, _interactions(root, agent))
        summary["config_tools"] = _config_tools(agent)
        runs.append(summary)
    return runs


def analyze_traces(
    storage_path: str,
    limit: int = 50,
    agent_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Summarise historic runs found under ``storage_path``.

    Args:
        storage_path: A Hugin storage directory (the one an agent ran against).
        limit: Most recent runs to read.
        agent_name: Only consider runs whose config has this name.

    Returns:
        A compact, redacted report. Every list is truncated; no raw tool
        arguments and no raw error text are included.
    """
    runs = read_runs(storage_path, limit=limit)
    if agent_name:
        runs = [run for run in runs if run["config"] == agent_name]

    if not runs:
        return {
            "runs_analyzed": 0,
            "note": "No runs found. Point --storage-path at the directory the "
            "agent actually ran against.",
        }

    completed = [run for run in runs if run["completed"]]
    successes = [run for run in completed if run["finish_type"] == "success"]
    steps = sorted(run["model_turns"] for run in runs)

    tools: Dict[str, Dict[str, Any]] = {}
    loops: Dict[str, int] = {}
    oversized: Dict[str, int] = {}

    for run in runs:
        seen: Dict[str, int] = {}
        for call in run["tool_calls"]:
            name = call["tool"]
            record = tools.setdefault(
                name,
                {"calls": 0, "errors": 0, "max_result_chars": 0, "errs": {}},
            )
            record["calls"] += 1
            if call["is_error"]:
                record["errors"] += 1
                if call["error"]:
                    record["errs"][call["error"]] = (
                        record["errs"].get(call["error"], 0) + 1
                    )
            record["max_result_chars"] = max(
                record["max_result_chars"], call["result_chars"]
            )
            if call["result_chars"] > OVERSIZED_RESULT_CHARS:
                oversized[name] = max(
                    oversized.get(name, 0), call["result_chars"]
                )
            key = f"{name}:{call['args']}"
            seen[key] = seen.get(key, 0) + 1
        for key, count in seen.items():
            if count >= LOOP_THRESHOLD:
                name = key.split(":", 1)[0]
                loops[name] = max(loops.get(name, 0), count)

    granted = {tool for run in runs for tool in run["config_tools"]}
    called = set(tools)
    dead = sorted(
        name
        for name in granted - called
        if not name.startswith("builtins.finish")
    )

    return {
        "runs_analyzed": len(runs),
        "completed": len(completed),
        "self_reported_success_rate": (
            round(len(successes) / len(completed), 3) if completed else None
        ),
        "unfinished_rate": round(1 - len(completed) / len(runs), 3),
        "model_turns": {
            "p50": _percentile(steps, 50),
            "p90": _percentile(steps, 90),
            "max": steps[-1] if steps else 0,
        },
        "tokens": {
            "input": sum(run["input_tokens"] for run in runs),
            "output": sum(run["output_tokens"] for run in runs),
            "output_per_run": round(
                sum(run["output_tokens"] for run in runs) / len(runs), 1
            ),
        },
        "unresolved_template_turns": sum(
            run["unresolved_template_turns"] for run in runs
        ),
        "tools": _tool_rows(tools),
        "dead_tools": dead,
        "loops_detected": top_counts(loops),
        "oversized_results": top_counts(oversized),
        "caveats": _caveats(runs, completed),
    }


def _tool_rows(tools: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Render per-tool stats, worst error rate first."""
    rows = []
    for name, record in tools.items():
        rows.append(
            {
                "name": redact(name),
                "calls": record["calls"],
                "errors": record["errors"],
                "error_rate": round(record["errors"] / record["calls"], 3),
                "max_result_chars": record["max_result_chars"],
                "top_errors": top_counts(record["errs"], limit=3),
            }
        )
    rows.sort(key=lambda row: (-row["error_rate"], -row["calls"], row["name"]))
    return rows


def _caveats(
    runs: List[Dict[str, Any]], completed: List[Dict[str, Any]]
) -> List[str]:
    """State what the numbers do not mean.

    The success rate is the measured agent's own verdict, so anything that
    optimises it can win by declaring success more readily or finishing sooner.
    Saying so next to the number is cheaper than discovering it later.
    """
    notes = [
        "success_rate is self-reported: it comes from the agent's own "
        "finish_type, not from any independent check of its output.",
    ]
    if len(runs) < 10:
        notes.append(
            f"Only {len(runs)} run(s) analysed -- too few to conclude much, "
            "and far too few to call an uncalled tool dead."
        )
    if not completed:
        notes.append("No run reached a TaskResult, so no run finished.")
    if not any(run["input_tokens"] for run in runs):
        notes.append(
            "No token counts recorded; cost figures are unavailable for "
            "these runs."
        )
    return notes


def _percentile(ordered: List[int], percentile: int) -> int:
    """Return a percentile from an already-sorted list."""
    if not ordered:
        return 0
    if len(ordered) == 1:
        return ordered[0]
    index = min(
        len(ordered) - 1,
        max(0, int(round((percentile / 100) * (len(ordered) - 1)))),
    )
    return ordered[index]


def default_storage_path(agent_path: str) -> Optional[str]:
    """Guess the storage directory an agent at ``agent_path`` ran against."""
    candidate = Path("storage") / Path(agent_path).name
    if (candidate / "agents").is_dir():
        return str(candidate)
    if (Path("storage") / "agents").is_dir():
        return "storage"
    return None
