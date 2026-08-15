"""Select the ``Learning`` artifacts that apply to a render context.

The keyword ``ArtifactQueryEngine`` filters by type and searches content, not by
metadata predicates, so learning selection is a dedicated scan over the raw
artifact records filtering by ``scope_config`` / ``scope_task`` / ``scope_app``.
Results are ranked by source-aware feedback and truncated to a budget, so
injected prompts cannot grow unboundedly across consolidation cycles. Human
ratings are authoritative once present; agent self-ratings remain the fallback
signal for learnings that have not been independently reviewed.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from gimle.hugin.storage.storage import Storage

logger = logging.getLogger(__name__)

LEARNING_TYPE = "Learning"
# Rating a learning starts at before anyone has rated it: neutral, so a fresh
# learning is neither boosted nor buried relative to rated peers.
NEUTRAL_RATING = 3.0
# Max learnings injected per render (top-N budget). Bounds prompt growth.
DEFAULT_BUDGET = 5


@dataclass
class SelectedLearning:
    """A learning chosen for injection, with its ranking signal."""

    artifact_id: str
    content: str
    scope_config: Optional[str]
    scope_task: Optional[str]
    scope_app: Optional[str]
    average_rating: float
    rating_count: int
    created_at: Optional[str]
    rating_source: Optional[str] = None


def _ratings_map(storage: Storage) -> Dict[str, Dict[str, List[int]]]:
    """Pre-load feedback ratings grouped by artifact id and source."""
    ratings: Dict[str, Dict[str, List[int]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for feedback_uuid in storage.list_feedback():
        try:
            feedback = storage.load_feedback(feedback_uuid)
            ratings[feedback.artifact_id][feedback.source].append(
                feedback.rating
            )
        except (ValueError, OSError) as error:
            logger.warning("Skipping feedback %s: %s", feedback_uuid, error)
    return {
        artifact_id: dict(by_source)
        for artifact_id, by_source in ratings.items()
    }


def _ranking_signal(
    ratings_by_source: Mapping[str, List[int]],
) -> Tuple[float, int, Optional[str]]:
    """Return the authoritative rating average, evidence count, and source.

    Human feedback replaces agent feedback once it exists rather than being
    averaged with the learning's birth confidence. Agent ratings remain useful
    before independent review, and a learning with no feedback is neutral.
    """
    for source in ("human", "agent"):
        ratings = ratings_by_source.get(source, [])
        if ratings:
            return sum(ratings) / len(ratings), len(ratings), source
    return NEUTRAL_RATING, 0, None


def _matches_scope(
    data: Dict,
    config: Optional[str],
    task: Optional[str],
    app: Optional[str],
) -> bool:
    """Whether a learning's scope applies to the given render context.

    Every scope field the learning sets must equal the context value, and the
    learning must actually target this config or app (a fully unscoped learning
    is never injected).
    """
    scope_config = data.get("scope_config")
    scope_task = data.get("scope_task")
    scope_app = data.get("scope_app")
    if scope_config is not None and scope_config != config:
        return False
    if scope_task is not None and scope_task != task:
        return False
    if scope_app is not None and scope_app != app:
        return False
    return (scope_config is not None and scope_config == config) or (
        scope_app is not None and scope_app == app
    )


def _scope_key(
    data: Mapping[str, Any],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return the exact scope used to validate a supersession edge."""
    return (
        data.get("scope_config"),
        data.get("scope_task"),
        data.get("scope_app"),
    )


def _supersession_targets(data: Mapping[str, Any]) -> List[str]:
    """Return well-formed target ids from one raw Learning record."""
    targets = data.get("supersedes", [])
    if not isinstance(targets, list):
        return []
    return [target for target in targets if isinstance(target, str) and target]


def _reaches(
    graph: Mapping[str, List[str]], start: str, destination: str
) -> bool:
    """Return whether ``start`` reaches ``destination`` in the graph."""
    pending = [start]
    seen: Set[str] = set()
    while pending:
        current = pending.pop()
        if current == destination:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(graph.get(current, []))
    return False


def _superseded_ids(records: Mapping[str, Dict[str, Any]]) -> Set[str]:
    """Return monotonically retired ids from valid, acyclic same-scope edges.

    An edge remains effective even when its source is later superseded. This
    makes a chain ``C -> B -> A`` retire both B and A rather than resurrecting
    A. Invalid cross-scope, dangling, self-referential, or cyclic edges are
    ignored so corrupt historical data cannot hide an entire scope.
    """
    graph: Dict[str, List[str]] = {}
    for source_id, source in records.items():
        targets = []
        for target_id in _supersession_targets(source):
            target = records.get(target_id)
            if target is None or _scope_key(target) != _scope_key(source):
                continue
            targets.append(target_id)
        graph[source_id] = targets

    cyclic_sources = {
        source_id
        for source_id, targets in graph.items()
        if any(
            source_id == target_id or _reaches(graph, target_id, source_id)
            for target_id in targets
        )
    }

    retired: Set[str] = set()
    for source_id, targets in graph.items():
        if source_id in cyclic_sources:
            logger.warning(
                "dream: ignoring links from cyclic supersession Learning %s",
                source_id,
            )
            continue
        for target_id in targets:
            retired.add(target_id)
    return retired


def select_learnings(
    storage: Storage,
    config: Optional[str] = None,
    task: Optional[str] = None,
    app: Optional[str] = None,
    budget: int = DEFAULT_BUDGET,
) -> List[SelectedLearning]:
    """Return the applicable learnings for a context, ranked and budget-capped.

    Human ratings are authoritative once present; otherwise agent ratings are
    used, with unrated learnings neutral. Equal scores prefer human-reviewed
    evidence, then a larger evidence count, then artifact id for a stable final
    tie-break. Creation time deliberately does not affect selection.
    """
    records: Dict[str, Dict[str, Any]] = {}
    for artifact_id in storage.list_artifacts():
        try:
            record = storage.load_artifact_record(artifact_id)
        except Exception as error:
            logger.warning(
                "dream: skipping artifact %s: %s", artifact_id, error
            )
            continue
        if record.get("type") != LEARNING_TYPE:
            continue
        data = record.get("data", {})
        if not isinstance(data, dict):
            logger.warning("dream: skipping malformed Learning %s", artifact_id)
            continue
        records[artifact_id] = data

    retired = _superseded_ids(records)
    ratings = _ratings_map(storage)
    selected: List[SelectedLearning] = []
    for artifact_id, data in records.items():
        if artifact_id in retired:
            continue
        if not _matches_scope(data, config, task, app):
            continue
        average, count, source = _ranking_signal(ratings.get(artifact_id, {}))
        selected.append(
            SelectedLearning(
                artifact_id=artifact_id,
                content=data.get("content", ""),
                scope_config=data.get("scope_config"),
                scope_task=data.get("scope_task"),
                scope_app=data.get("scope_app"),
                average_rating=average,
                rating_count=count,
                rating_source=source,
                created_at=data.get("created_at"),
            )
        )

    # Establish a stable ascending final tie-break first. Python's sort is
    # stable, so the source-aware descending ranking below preserves it when
    # every quality signal is equal.
    selected.sort(key=lambda item: item.artifact_id)

    selected.sort(
        key=lambda item: (
            item.average_rating,
            item.rating_source == "human",
            item.rating_count,
        ),
        reverse=True,
    )
    if budget >= 0:
        selected = selected[:budget]
    return selected


def render_learnings_block(learnings: List[SelectedLearning]) -> str:
    """Format selected learnings as a plain-text block for prompt injection.

    Returns "" when there are none, so a ``{{ learnings }}`` cold start renders
    cleanly empty.
    """
    if not learnings:
        return ""
    return "\n".join(f"- {item.content}" for item in learnings)
