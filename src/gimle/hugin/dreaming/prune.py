"""Plan and apply conservative physical pruning of retired learnings."""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from gimle.hugin.dreaming.selector import (
    _learning_records,
    _valid_supersession_graph,
)
from gimle.hugin.storage.storage import Storage

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 30


@dataclass(frozen=True)
class LearningPruneCandidate:
    """A structurally superseded learning whose retention window elapsed."""

    artifact_id: str
    superseded_at: str
    superseded_by: Tuple[str, ...]
    scope_config: Optional[str]
    scope_task: Optional[str]
    scope_app: Optional[str]


def _parse_timestamp(value: object, *, artifact_id: str) -> Optional[datetime]:
    """Parse an aware ISO-8601 timestamp, failing closed on bad metadata."""
    if not isinstance(value, str) or not value:
        logger.warning(
            "dream prune: retaining Learning %s with missing created_at",
            artifact_id,
        )
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.warning(
            "dream prune: retaining Learning %s with invalid created_at",
            artifact_id,
        )
        return None
    if parsed.tzinfo is None:
        logger.warning(
            "dream prune: retaining Learning %s with naive created_at",
            artifact_id,
        )
        return None
    return parsed.astimezone(timezone.utc)


def _retirement_events(
    records: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Tuple[str, datetime]]]:
    """Map retired ids to trustworthy structural retirement events."""
    events: Dict[str, List[Tuple[str, datetime]]] = defaultdict(list)
    for source_id, targets in _valid_supersession_graph(records).items():
        if not targets:
            continue
        source_at = _parse_timestamp(
            records[source_id].get("created_at"), artifact_id=source_id
        )
        if source_at is None:
            continue
        for target_id in targets:
            target_at = _parse_timestamp(
                records[target_id].get("created_at"), artifact_id=target_id
            )
            if target_at is None:
                continue
            if source_at < target_at:
                logger.warning(
                    "dream prune: retaining Learning %s because superseding "
                    "Learning %s predates it",
                    target_id,
                    source_id,
                )
                continue
            events[target_id].append((source_id, source_at))
    return events


def plan_learning_prune(
    storage: Storage,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    *,
    now: Optional[datetime] = None,
) -> List[LearningPruneCandidate]:
    """Return safe physical-pruning candidates without modifying storage.

    Only targets of valid, acyclic, exact-scope structural supersession edges
    are eligible. The superseding Learning's creation timestamp records when
    retirement began. Missing, malformed, naive, or inconsistent timestamps
    retain the audit record rather than guessing.
    """
    if retention_days < 0:
        raise ValueError("retention_days must be non-negative")
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("now must include timezone information")
    cutoff = current_time.astimezone(timezone.utc) - timedelta(
        days=retention_days
    )

    records = _learning_records(storage)
    candidates: List[LearningPruneCandidate] = []
    for artifact_id, events in _retirement_events(records).items():
        superseded_at = min(event_at for _, event_at in events)
        if superseded_at > cutoff:
            continue
        data = records[artifact_id]
        candidates.append(
            LearningPruneCandidate(
                artifact_id=artifact_id,
                superseded_at=superseded_at.isoformat(),
                superseded_by=tuple(
                    sorted({source_id for source_id, _ in events})
                ),
                scope_config=data.get("scope_config"),
                scope_task=data.get("scope_task"),
                scope_app=data.get("scope_app"),
            )
        )

    candidates.sort(
        key=lambda candidate: (
            candidate.superseded_at,
            candidate.artifact_id,
        )
    )
    return candidates


def prune_learnings(
    storage: Storage,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    *,
    apply: bool = False,
    now: Optional[datetime] = None,
) -> List[LearningPruneCandidate]:
    """Plan pruning and, only with ``apply=True``, delete the candidates."""
    candidates = plan_learning_prune(
        storage, retention_days=retention_days, now=now
    )
    if apply:
        for candidate in candidates:
            artifact = storage.load_artifact(
                candidate.artifact_id, load_interaction=False
            )
            storage.delete_artifact(artifact)
    return candidates
