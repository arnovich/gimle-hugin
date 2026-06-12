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

logger = logging.getLogger(__name__)

DREAMER_CONFIG_NAME = "dreamer"
DREAM_SCOPE_KEY = "dream_scope"
DREAM_DRY_RUN_KEY = "dream_dry_run"
DREAM_RESULTS_KEY = "dream_results"


def _episodic_block(
    environment: Environment, provenances: List[ArtifactProvenance]
) -> str:
    """Fetch the episodic artifacts' content as a readable block."""
    engine = environment.query_engine
    lines: List[str] = []
    for provenance in provenances:
        content = engine.get_artifact_content(provenance.artifact_id) or ""
        task_label = provenance.task or "general"
        lines.append(
            f"- [{provenance.artifact_id}] (task: {task_label})\n  {content}"
        )
    return "\n".join(lines)


def _consolidate_prompt(config_name: str, episodic_block: str) -> str:
    """Build the dream worker's task prompt for one scope."""
    return (
        f"You are consolidating the episodic memories produced by the "
        f"'{config_name}' agent configuration into reusable learnings.\n\n"
        f"Episodic memories (insights saved during past runs):\n"
        f"{episodic_block}\n\n"
        f"Find cross-cutting patterns, recurring mistakes, and durable lessons. "
        f"For each distinct lesson, call dreaming.save_learning with the lesson "
        f"as prose ready to drop into a prompt, the source artifact ids it came "
        f"from, and your confidence (0-1). Keep each learning specific and "
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

        worker_task = Task(
            name="consolidate",
            description=f"Consolidate memories for {config_name}",
            parameters={},
            prompt=_consolidate_prompt(
                config_name, _episodic_block(environment, provenances)
            ),
            tools=[],
        )
        agent = Agent.create_from_task(session, dreamer_config, worker_task)
        logger.info(
            "dream: consolidating '%s' (%d episodic artifacts)",
            config_name,
            len(provenances),
        )
        steps = 0
        while steps < max_steps and agent.step():
            steps += 1

    results: List[Dict[str, Any]] = environment.env_vars.get(
        DREAM_RESULTS_KEY, []
    )
    return results
