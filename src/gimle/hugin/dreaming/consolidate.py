"""Run the offline dream: consolidate episodic artifacts into Learnings.

Drives one dream-worker agent per config scope. For each scope the episodic
artifacts (provenance-grouped) are fetched and embedded into the worker's task
prompt; the worker synthesises patterns and calls ``dreaming.save_learning``,
which stamps the scope and self-rates the result.
"""

import logging
from typing import Any, Dict, List, Optional

from gimle.hugin.agent.agent import Agent
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.agent.task import Task
from gimle.hugin.dreaming.provenance import (
    ArtifactProvenance,
    group_by_config,
    scan_provenance,
)
from gimle.hugin.dreaming.selector import select_learnings
from gimle.hugin.storage.storage import Storage

logger = logging.getLogger(__name__)

DREAMER_CONFIG_NAME = "dreamer"
#: Character budget for one scope's episodic corpus in a single dream prompt.
#: ~30k tokens: comfortably inside any current context alongside the system
#: prompt and the worker's own reasoning, while still spanning weeks of a
#: short-form scope. Raise it when models grow; do not remove it — unbounded was
#: the bug.
DEFAULT_CORPUS_CHARS = 120_000
DREAM_SCOPE_KEY = "dream_scope"
DREAM_DRY_RUN_KEY = "dream_dry_run"
DREAM_RESULTS_KEY = "dream_results"


def _episodic_block(
    environment: Environment,
    provenances: List[ArtifactProvenance],
    max_chars: int = DEFAULT_CORPUS_CHARS,
) -> str:
    """Fetch episodic content as a readable block, newest-first within a budget.

    The budget is the point. This replayed a config's ENTIRE history every night,
    so the prompt grew without bound as the corpus accumulated, and a scope whose
    artifacts are large crossed the model's usable limit and started consolidating
    nothing — silently, since a dream that saves zero learnings still succeeds.

    Bounded on SIZE rather than count because artifact sizes differ by an order of
    magnitude between scopes writing to the same store. In the case that exposed
    this, three personas each had 53 artifacts: the one writing short pieces still
    worked, while the two writing long ones had been dead for weeks. A count cap
    ("last 30") would have left both of those broken and needlessly starved the
    third; a character budget self-balances with no per-scope tuning.

    Newest-first selection, then presented oldest-first so the corpus still reads
    chronologically. Anything dropped is LOGGED — a silently trimmed corpus reads
    as "it considered everything", which is how this went unnoticed in the first
    place.
    """
    engine = environment.query_engine
    # Newest first, so the budget keeps recent memory. A missing created_at sorts
    # oldest and is therefore dropped first — the conservative direction.
    ordered = sorted(
        provenances, key=lambda p: p.created_at or "", reverse=True
    )

    chosen: List[tuple[ArtifactProvenance, str]] = []
    used = 0
    for provenance in ordered:
        content = engine.get_artifact_content(provenance.artifact_id) or ""
        entry = f"- [{provenance.artifact_id}] (task: {provenance.task or 'general'})\n  {content}"
        # Always take at least one, or a single oversized artifact yields an empty
        # corpus and the dream silently does nothing — the failure this fixes.
        if chosen and used + len(entry) > max_chars:
            continue
        chosen.append((provenance, entry))
        used += len(entry)

    dropped = len(ordered) - len(chosen)
    if dropped:
        logger.info(
            "dream: corpus trimmed to %d of %d artifacts (%d chars, budget %d) — "
            "oldest dropped first",
            len(chosen),
            len(ordered),
            used,
            max_chars,
        )
    # Back to chronological for the reader.
    return "\n".join(entry for _, entry in reversed(chosen))


#: Shown when a scope has no learnings in effect yet — stated explicitly rather
#: than left blank, so the worker can tell "nothing learned yet" (write the first
#: ones) from "the block failed to load" (say nothing confidently).
NO_PRIOR_LEARNINGS = "(none yet — this scope has no learnings in effect)"


#: How many prior learnings the worker is shown when judging "do I already know
#: this?". Deliberately NOT ``selector.DEFAULT_BUDGET``: that one caps how many
#: learnings are INJECTED into a persona's prompt at render time, which is a
#: prompt-economy limit. Deduplication is a different question and needs the whole
#: body of knowledge — shown only the render-time top 5, the worker restated a
#: learning it had written itself thirteen minutes earlier, because that learning
#: had already dropped below the cut. Cheap to be generous: a scope's entire set
#: is a few KB.
DEDUP_BUDGET = 100


def _prior_learnings_block(
    storage: Storage, config_name: str, budget: int = DEDUP_BUDGET
) -> str:
    """Return the learnings ALREADY in effect for a scope, as worker context.

    Everything the scope has concluded, not the render-time top-N. The worker is
    being asked "what do these memories add that I do not already know?", and it
    cannot answer that about learnings it is not shown — it re-derives them, and
    the duplicate then competes for the very top-N slots that hid the original.

    Note these stay OUT of the corpus (``scan_provenance`` excludes them, rightly
    — consolidating learnings into learnings compounds drift). They are context,
    not material.
    """
    try:
        prior = select_learnings(storage, config=config_name, budget=budget)
    except (
        Exception
    ) as error:  # a store that cannot be read must not kill the dream
        logger.warning(
            "dream: could not load prior learnings for '%s': %s — consolidating "
            "without them, so it may restate what it already knows",
            config_name,
            error,
        )
        return NO_PRIOR_LEARNINGS
    if not prior:
        return NO_PRIOR_LEARNINGS
    return "\n\n".join(
        f"- [{item.artifact_id}] {item.content}" for item in prior
    )


def _consolidate_prompt(
    config_name: str, episodic_block: str, prior_learnings_block: str
) -> str:
    """Build the dream worker's task prompt for one scope.

    The ask is a DIFF against what is already known, not an open "find patterns".
    Asked the open question the worker re-answers the same judgement call over a
    near-identical corpus every night, holding a standing licence to save nothing
    — so identical runs minutes apart produced ten learnings and zero. It could
    not do better: prior learnings are excluded from the corpus, so it had no way
    to know the answer was already on disk, nor to supersede a stale one.
    """
    return (
        f"You are consolidating the episodic memories produced by the "
        f"'{config_name}' agent configuration into reusable learnings.\n\n"
        f"Learnings ALREADY in effect for '{config_name}' — these are injected "
        f"into its prompts today:\n"
        f"{prior_learnings_block}\n\n"
        f"Episodic memories (insights saved during past runs):\n"
        f"{episodic_block}\n\n"
        f"Your question is not 'is there a pattern here?' but what these memories "
        f"show that the learnings above do NOT already say. Save a learning when "
        f"the memories support a durable lesson missing from them, or when one of "
        f"them has been overtaken by what the memories now show — in that case say "
        f"so explicitly in the new learning's prose. Do not restate a lesson that "
        f"is already in effect. For each one, call dreaming.save_learning with the "
        f"lesson as prose ready to drop into a prompt, the source artifact ids it "
        f"came from, and your confidence (0-1). Keep each learning specific and "
        f"actionable. When done, call finish."
    )


def run_dream(
    environment: Environment,
    config: Optional[str] = None,
    task: Optional[str] = None,
    max_steps: int = 20,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """Consolidate episodic memory into Learnings for one or all config scopes.

    Args:
        environment: Environment whose storage holds the corpus and whose
            config registry provides the ``dreamer`` worker config.
        config: Restrict to a single config scope (default: all scopes found).
        task: Restrict to a single task within the scope (default: all).
        max_steps: Per-scope step budget for the worker agent.
        dry_run: Produce learnings but persist nothing.

    Returns:
        A list of result records (one per saved learning), as collected by
        ``dreaming.save_learning``.
    """
    storage = environment.storage
    if storage is None:
        raise ValueError("run_dream requires an environment with storage")

    dreamer_config = environment.config_registry.get(DREAMER_CONFIG_NAME)

    session = Session(environment=environment)
    grouped = group_by_config(scan_provenance(storage, session))
    target_configs = [config] if config is not None else sorted(grouped)

    environment.env_vars[DREAM_RESULTS_KEY] = []

    for config_name in target_configs:
        provenances = grouped.get(config_name, [])
        if task is not None:
            provenances = [p for p in provenances if p.task == task]
        if not provenances:
            logger.info(
                "dream: no episodic artifacts for config '%s'", config_name
            )
            continue

        environment.env_vars[DREAM_SCOPE_KEY] = {
            "config": config_name,
            "task": task,
            "app": None,
        }
        environment.env_vars[DREAM_DRY_RUN_KEY] = dry_run

        prior_block = _prior_learnings_block(storage, config_name)
        worker_task = Task(
            name="consolidate",
            description=f"Consolidate memories for {config_name}",
            parameters={},
            prompt=_consolidate_prompt(
                config_name,
                _episodic_block(environment, provenances),
                prior_block,
            ),
            tools=[],
        )
        agent = Agent.create_from_task(session, dreamer_config, worker_task)
        logger.info(
            "dream: consolidating '%s' (%d episodic artifacts, %d learnings "
            "already in effect)",
            config_name,
            len(provenances),
            (
                0
                if prior_block == NO_PRIOR_LEARNINGS
                else prior_block.count("\n\n") + 1
            ),
        )
        steps = 0
        while steps < max_steps and agent.step():
            steps += 1

    results: List[Dict[str, Any]] = environment.env_vars.get(
        DREAM_RESULTS_KEY, []
    )
    return results
