"""Select the ``Learning`` artifacts that apply to a render context.

The keyword ``ArtifactQueryEngine`` filters by type and searches content, not by
metadata predicates, so learning selection is a dedicated scan over the raw
artifact records filtering by ``scope_config`` / ``scope_task`` / ``scope_app``.
Results are ranked by rating then recency and truncated to a budget, so injected
prompts cannot grow unboundedly across consolidation cycles.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

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


def _ratings_map(storage: Storage) -> Dict[str, List[int]]:
    """Pre-load feedback ratings grouped by artifact id."""
    ratings: Dict[str, List[int]] = defaultdict(list)
    for feedback_uuid in storage.list_feedback():
        try:
            feedback = storage.load_feedback(feedback_uuid)
            ratings[feedback.artifact_id].append(feedback.rating)
        except (ValueError, OSError) as error:
            logger.warning("Skipping feedback %s: %s", feedback_uuid, error)
    return dict(ratings)


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


def select_learnings(
    storage: Storage,
    config: Optional[str] = None,
    task: Optional[str] = None,
    app: Optional[str] = None,
    budget: int = DEFAULT_BUDGET,
) -> List[SelectedLearning]:
    """Return the applicable learnings for a context, ranked and budget-capped.

    Sorted by average rating (neutral when unrated) then recency, then truncated
    to ``budget`` (top-N). Higher-rated, fresher learnings win; low-rated ones
    decay out of selection.
    """
    ratings = _ratings_map(storage)
    selected: List[SelectedLearning] = []
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
        if not _matches_scope(data, config, task, app):
            continue
        artifact_ratings = ratings.get(artifact_id, [])
        count = len(artifact_ratings)
        # Unrated learnings rank neutrally — neither boosted nor buried.
        average = sum(artifact_ratings) / count if count else NEUTRAL_RATING
        selected.append(
            SelectedLearning(
                artifact_id=artifact_id,
                content=data.get("content", ""),
                scope_config=data.get("scope_config"),
                scope_task=data.get("scope_task"),
                scope_app=data.get("scope_app"),
                average_rating=average,
                rating_count=count,
                created_at=data.get("created_at"),
            )
        )

    def sort_key(item: SelectedLearning) -> tuple:
        return (item.average_rating, item.created_at or "")

    selected.sort(key=sort_key, reverse=True)
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
