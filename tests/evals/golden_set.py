"""Descriptions the agent builder is measured against.

Every test in this repo so far pins *mechanics*: that a check fires, that a
file lands, that a gate refuses. None of them measure the thing the builder
actually is -- a model following a prompt. So a prompt change (PR 2.2 rewrites
the builder's system prompt outright) currently cannot be shown to have helped
or hurt.

These cases are that measurement. They are ordinary requests a user would
plausibly type, chosen to span the shapes an agent can take, and each records
what a good answer would look like so a run can be scored rather than eyeballed.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class EvalCase:
    """One description, and what a good agent built from it would contain.

    ``expect_tools`` and ``expect_tasks`` are counted separately because the
    same work can live in either. A chained agent puts a stage in a task; a flat
    one puts it in a tool. Judging a pipeline by its tool count alone penalises
    exactly the shape a pipeline description asks for -- which is what happened
    the first time the builder learned to chain: it produced correct three-stage
    agents and the golden set scored them as regressions.

    ``expect_architecture`` is recorded but **not scored**: nothing yet asks the
    builder for a named shape. ``has_task_sequence`` is the proxy meanwhile.
    """

    name: str
    description: str
    expect_tools: int = 1
    expect_tasks: int = 1
    expect_parameters: bool = True
    expect_architecture: str = "single_shot"
    tags: Tuple[str, ...] = field(default_factory=tuple)


GOLDEN_SET: List[EvalCase] = [
    EvalCase(
        name="weather_advisor",
        description=(
            "Look up the current weather and a five-day forecast for any "
            "city, then advise on what to wear and whether to take an "
            "umbrella."
        ),
        expect_tools=2,
        tags=("api", "simple"),
    ),
    EvalCase(
        name="csv_summariser",
        description=(
            "Read a CSV file of sales rows, compute totals and averages per "
            "region, and write a short plain-text summary of the findings."
        ),
        expect_tools=2,
        tags=("files", "data"),
    ),
    EvalCase(
        name="link_checker",
        description=(
            "Given a URL, fetch the page, find every outbound link, check "
            "which ones are broken, and report the broken ones with their "
            "status codes."
        ),
        expect_tools=2,
        tags=("api", "network"),
    ),
    EvalCase(
        name="release_notes",
        description=(
            "Take a list of merged pull request titles and produce release "
            "notes grouped into features, fixes and breaking changes."
        ),
        expect_tools=1,
        tags=("text",),
    ),
    EvalCase(
        name="expense_categoriser",
        description=(
            "Given a bank transaction description and amount, categorise the "
            "expense, flag anything that looks unusual for its category, and "
            "keep a running total per category."
        ),
        expect_tools=2,
        tags=("stateful",),
    ),
    EvalCase(
        name="recipe_scaler",
        description=(
            "Take a recipe and a target number of servings, rescale every "
            "ingredient quantity, and convert between metric and imperial "
            "units on request."
        ),
        expect_tools=2,
        tags=("simple",),
    ),
    EvalCase(
        name="log_triage",
        description=(
            "Read an application log file, group the errors by their root "
            "cause, count how often each occurs, and rank them by how many "
            "distinct users they affected."
        ),
        expect_tools=2,
        tags=("files", "data"),
    ),
    EvalCase(
        name="meeting_notes",
        description=(
            "Turn a raw meeting transcript into structured notes: decisions "
            "taken, action items with owners, and questions left open."
        ),
        expect_tools=1,
        tags=("text",),
    ),
    EvalCase(
        name="research_pipeline",
        description=(
            "Research a topic in three stages: gather sources, then "
            "summarise each one, then write a single briefing that cites "
            "them. Each stage should hand its result to the next."
        ),
        expect_tools=1,
        expect_tasks=3,
        expect_architecture="pipeline",
        tags=("pipeline", "multi_stage"),
    ),
    EvalCase(
        name="invoice_pipeline",
        description=(
            "Process an invoice in stages: extract the line items, validate "
            "them against a purchase order, then produce an approval "
            "summary. Later stages need the earlier stages' output."
        ),
        expect_tools=1,
        expect_tasks=3,
        expect_architecture="pipeline",
        tags=("pipeline", "multi_stage"),
    ),
    EvalCase(
        name="code_reviewer",
        description=(
            "Review a Python file for bugs. For each issue found, delegate a "
            "deeper investigation to a sub-agent that examines just that "
            "issue, then collect the findings into one report."
        ),
        expect_tools=2,
        expect_architecture="delegating",
        tags=("delegating", "sub_agent"),
    ),
    EvalCase(
        name="refund_approver",
        description=(
            "Decide whether to approve a customer refund. Anything over 100 "
            "euros must be confirmed by a human before it is approved."
        ),
        expect_tools=2,
        expect_architecture="interactive",
        tags=("human_in_loop",),
    ),
    EvalCase(
        name="repo_stats",
        description=(
            "Given a local git repository path, run shell commands to count "
            "commits per author, find the largest files, and report which "
            "files changed most often."
        ),
        expect_tools=2,
        expect_architecture="shell",
        tags=("shell",),
    ),
    EvalCase(
        name="reading_list",
        description=(
            "Keep a reading list. Add articles with a title and URL, mark "
            "them as read, and recall what was learned from articles read "
            "earlier when recommending the next one."
        ),
        expect_tools=3,
        expect_architecture="stateful",
        tags=("artifacts", "memory"),
    ),
    EvalCase(
        name="unit_converter",
        description=(
            "Convert between units of length, weight and temperature, "
            "showing the conversion factor used."
        ),
        expect_tools=1,
        tags=("simple", "cheap"),
    ),
]


def by_name(name: str) -> EvalCase:
    """Return one case by name, or raise with the available names."""
    for case in GOLDEN_SET:
        if case.name == name:
            return case
    available = ", ".join(case.name for case in GOLDEN_SET)
    raise KeyError(f"No eval case '{name}'. Available: {available}")


def select(
    names: Optional[List[str]] = None,
    tag: Optional[str] = None,
    limit: int = 0,
) -> List[EvalCase]:
    """Return the cases matching ``names``/``tag``, capped by ``limit``.

    Running the whole set means running the full builder once per case, which
    is real money. Selecting a subset is the normal way to use this.
    """
    cases = list(GOLDEN_SET)
    if names:
        cases = [by_name(name) for name in names]
    if tag:
        cases = [case for case in cases if tag in case.tags]
    if limit:
        cases = cases[:limit]
    return cases
