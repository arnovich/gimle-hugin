"""Propose one change to an agent, and make it prove the number it cites.

"Every change must cite a metric" is a prompt norm, and prompt norms produce
*cited* metrics -- including invented ones. By the time a proposal is written
the trace report is far back in a long single-stack context, which is exactly
the condition under which a model reconstructs a plausible number instead of
recalling the real one.

So the citation is checked rather than requested. The report is kept in
``env_vars``; this tool resolves the cited metric against it and rejects the
call when the metric does not exist or the value does not match. A proposal
that cannot name a real number is not recorded, so it cannot be applied.
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

REPORT_KEY = "trace_report"
PROPOSALS_KEY = "proposed_changes"

# The agent's own verdict on itself. Optimising it has one cheap win --
# declare success sooner -- so it is admissible as a symptom and never as
# evidence that a change is an improvement. See spec 5.1c.
SELF_REPORTED_METRICS = frozenset(
    {"self_reported_success_rate", "unfinished_rate"}
)

# Removing a tool needs more evidence than changing one. Zero calls across a
# handful of runs is not proof a tool is dead -- it may serve a branch those
# runs never reached, and deleting it breaks the branch silently, in a way no
# metric here would ever show.
MIN_RUNS_FOR_REMOVAL = 20

CHANGE_TYPES = frozenset(
    {"edit_tool", "edit_template", "edit_task", "edit_config", "remove_tool"}
)

# Floats in the report are rounded to 3 places, so an exact match would fail
# on a value the model read correctly off the report.
TOLERANCE = 0.001


def _resolve(report: Dict[str, Any], metric: str) -> Tuple[bool, Any]:
    """Resolve a dotted metric path in the report.

    Understands three shapes, because the report has three:
    a scalar (``self_reported_success_rate``), a nested dict
    (``model_turns.p90``), and a list of named rows
    (``tools.read_example.error_rate``).

    Returns:
        ``(found, value)``. ``found`` is False when the path names nothing,
        which is the case that matters -- an invented metric.
    """
    current: Any = report
    for part in metric.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        if isinstance(current, list):
            row = next(
                (
                    item
                    for item in current
                    if isinstance(item, dict) and item.get("name") == part
                ),
                None,
            )
            if row is not None:
                current = row
                continue
        return False, None
    return True, current


def _matches(observed: Any, actual: Any) -> bool:
    """Return True when the cited value is the one in the report.

    Tool arguments arrive as whatever the model emitted, so "0.25" and 0.25
    are the same citation and both are accepted. A list metric such as
    ``dead_tools`` is cited by naming a member.
    """
    if isinstance(actual, list):
        return _matches_list(observed, actual)
    try:
        return abs(float(observed) - float(actual)) <= TOLERANCE
    except (TypeError, ValueError):
        return str(observed).strip() == str(actual).strip()


def _matches_list(observed: Any, actual: List[Any]) -> bool:
    """Accept any faithful way of citing a list metric.

    The report holds three list shapes -- plain strings (``dead_tools``) and
    ``{"value": ..., "count": ...}`` rows (``loops_detected``,
    ``oversized_results``) -- and a model may cite one by naming a member or
    by quoting the whole list back. All of those are truthful citations.

    Being strict here is not the safe direction. A guard that rejects a
    correct citation teaches the model to abandon real evidence: on a real
    run, ``loops_detected`` was cited accurately and refused three times
    because each row was being compared against the whole stringified list.
    """
    wanted = str(observed).strip()
    if wanted == str(actual).strip():
        return True
    for item in actual:
        if str(item).strip() == wanted:
            return True
        if isinstance(item, dict):
            for key in ("value", "name"):
                if key in item and str(item[key]).strip() == wanted:
                    return True
    return False


def _known_metrics(report: Dict[str, Any]) -> List[str]:
    """List the metric paths a proposal may cite, for the rejection message.

    A rejection that does not say what *would* have been valid just produces
    another guess.
    """
    paths: List[str] = []
    for key, value in report.items():
        if isinstance(value, dict):
            paths.extend(f"{key}.{inner}" for inner in value)
        elif isinstance(value, list):
            named = [
                item["name"]
                for item in value
                if isinstance(item, dict) and "name" in item
            ]
            if named:
                paths.extend(f"{key}.{name}" for name in named)
            else:
                # A plain list (dead_tools) is cited by naming a member.
                paths.append(key)
        else:
            paths.append(key)
    return sorted(paths)


def propose_change(
    stack: "Stack",
    file: str,
    change_type: str,
    metric: str,
    observed_value: str,
    rationale: str,
    replacement_for: Optional[str] = None,
) -> ToolResponse:
    """Record one evidence-backed proposal, or reject it.

    Args:
        stack: Agent stack (auto-injected)
        file: The generated-file key the change would touch
        change_type: One of edit_tool, edit_template, edit_task, edit_config,
            remove_tool
        metric: Dotted path into the trace report, e.g. ``tools.fetch.errors``
        observed_value: The value that metric has in the report
        rationale: Why that number implies this change
        replacement_for: Optional prior proposal this supersedes

    Returns:
        ToolResponse confirming the proposal, or an error saying why not.
    """
    env_vars = stack.agent.environment.env_vars
    report = env_vars.get(REPORT_KEY)
    if not isinstance(report, dict) or not report:
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    "No trace report is loaded. Call analyze_traces before "
                    "proposing changes -- a proposal with nothing to cite "
                    "cannot be checked."
                )
            },
        )

    if change_type not in CHANGE_TYPES:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"unknown change_type {change_type!r}",
                "allowed": sorted(CHANGE_TYPES),
            },
        )

    if metric in SELF_REPORTED_METRICS:
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    f"{metric!r} is the agent's own verdict on itself, so it "
                    "cannot be evidence that a change is an improvement -- "
                    "the cheapest way to raise it is to declare success "
                    "sooner. Cite something the agent does not choose: a "
                    "tool error rate, a loop, an oversized result, step "
                    "count."
                ),
                "self_reported": sorted(SELF_REPORTED_METRICS),
            },
        )

    if change_type == "remove_tool":
        runs = report.get("runs_analyzed")
        if not isinstance(runs, int) or runs < MIN_RUNS_FOR_REMOVAL:
            return ToolResponse(
                is_error=True,
                content={
                    "error": (
                        f"{runs} run(s) is not enough to remove a tool. A "
                        "tool with no calls may serve a branch these runs "
                        f"never reached; {MIN_RUNS_FOR_REMOVAL} or more are "
                        "needed before absence is evidence. Propose an edit, "
                        "or say so in your summary instead."
                    ),
                    "runs_analyzed": runs,
                    "required": MIN_RUNS_FOR_REMOVAL,
                },
            )

    found, actual = _resolve(report, metric)
    if not found:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"{metric!r} is not a metric in the trace report",
                "known_metrics": _known_metrics(report),
            },
        )

    if not _matches(observed_value, actual):
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    f"{metric!r} is {actual!r} in the report, not "
                    f"{observed_value!r}. Cite the report, do not recall it."
                ),
                "metric": metric,
                "actual_value": actual,
            },
        )

    proposal = {
        "file": file,
        "change_type": change_type,
        "metric": metric,
        "observed_value": actual,
        "rationale": rationale,
    }
    proposals = env_vars.get(PROPOSALS_KEY)
    if not isinstance(proposals, list):
        proposals = []
    if replacement_for:
        proposals = [
            item for item in proposals if item.get("file") != replacement_for
        ]
    proposals.append(proposal)
    env_vars[PROPOSALS_KEY] = proposals

    return ToolResponse(
        is_error=False,
        content={
            "accepted": proposal,
            "proposals_so_far": len(proposals),
        },
    )
