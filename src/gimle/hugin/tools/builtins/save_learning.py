"""Save learning builtin tool: persist a consolidated 'dreaming' learning.

Used by the dream worker (``hugin dream``). Mirrors ``save_insight`` but writes
a ``Learning`` artifact, stamps its scope from the dream run context
(``environment.env_vars["dream_scope"]``), and self-rates it via
``ArtifactFeedback`` (``source="agent"``).
"""

import logging
import traceback
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple

from gimle.hugin.artifacts.feedback import ArtifactFeedback
from gimle.hugin.artifacts.learning import Learning
from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack
    from gimle.hugin.storage.storage import Storage

# env_vars keys the dream run uses to communicate with this tool.
DREAM_SCOPE_KEY = "dream_scope"
DREAM_DRY_RUN_KEY = "dream_dry_run"
DREAM_RESULTS_KEY = "dream_results"
MAX_SUPERSESSION_LINKS = 100


def _scope_key(
    data: Mapping[str, Any],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return the exact scope a learning occupies."""
    return (
        data.get("scope_config"),
        data.get("scope_task"),
        data.get("scope_app"),
    )


def _record(storage: "Storage", artifact_id: str) -> Dict[str, Any]:
    """Load one existing Learning record or raise a model-facing error."""
    try:
        record = storage.load_artifact_record(artifact_id)
    except Exception as error:
        raise ValueError(
            f"supersedes target '{artifact_id}' does not exist"
        ) from error
    if record.get("type") != "Learning" or not isinstance(
        record.get("data"), dict
    ):
        raise ValueError(
            f"supersedes target '{artifact_id}' is not a Learning artifact"
        )
    return record


def _stored_targets(record: Mapping[str, Any]) -> List[str]:
    """Return well-formed supersession ids from a raw Learning record."""
    data = record.get("data", {})
    if not isinstance(data, dict):
        return []
    targets = data.get("supersedes", [])
    if not isinstance(targets, list):
        return []
    return [target for target in targets if isinstance(target, str) and target]


def _would_create_cycle(
    storage: "Storage", learning_id: str, targets: List[str]
) -> bool:
    """Return whether an existing target chain points back to the new id."""
    pending = list(targets)
    seen = set()
    while pending:
        artifact_id = pending.pop()
        if artifact_id == learning_id:
            return True
        if artifact_id in seen:
            continue
        seen.add(artifact_id)
        try:
            record = storage.load_artifact_record(artifact_id)
        except Exception:
            continue
        if record.get("type") == "Learning":
            pending.extend(_stored_targets(record))
    return False


def _validate_supersedes(
    storage: Optional["Storage"], learning: Learning
) -> None:
    """Validate targets before the new learning or its feedback is persisted."""
    if not learning.supersedes:
        return
    if storage is None:
        raise ValueError("supersedes requires persistent learning storage")
    if len(learning.supersedes) > MAX_SUPERSESSION_LINKS:
        raise ValueError(
            f"supersedes accepts at most {MAX_SUPERSESSION_LINKS} learning ids"
        )

    learning_scope = (
        learning.scope_config,
        learning.scope_task,
        learning.scope_app,
    )
    for artifact_id in learning.supersedes:
        target = _record(storage, artifact_id)
        if _scope_key(target["data"]) != learning_scope:
            raise ValueError(
                f"supersedes target '{artifact_id}' has a different scope"
            )

    if _would_create_cycle(storage, learning.id, learning.supersedes):
        raise ValueError("supersedes would create a cycle")


def _confidence_to_rating(confidence: float) -> int:
    """Map a [0, 1] confidence to a 1-5 ArtifactFeedback rating."""
    clamped = max(0.0, min(1.0, confidence))
    return max(1, min(5, round(1 + clamped * 4)))


@Tool.register(
    name="dreaming.save_learning",
    description=(
        "Save a consolidated learning distilled from episodic artifacts. "
        "The scope (config/task) is taken from the dream run automatically. "
        "Provide the lesson as prose ready to drop into a prompt, the source "
        "artifact ids it was distilled from, optional same-scope Learning ids "
        "it supersedes, and your confidence (0-1)."
    ),
    parameters={
        "content": {
            "type": "string",
            "description": "The lesson, in prose ready to drop into a prompt",
            "required": True,
        },
        "source_artifact_ids": {
            "type": "array",
            "description": "Artifact ids this learning was distilled from",
            "required": False,
        },
        "supersedes": {
            "type": "array",
            "description": (
                "Existing same-scope Learning ids this lesson replaces"
            ),
            "required": False,
        },
        "confidence": {
            "type": "number",
            "description": "Self-assessed confidence in the learning, 0-1",
            "required": False,
            "default": 0.7,
        },
    },
    is_interactive=False,
)
def save_learning(
    content: str,
    stack: "Stack",
    source_artifact_ids: Optional[List[str]] = None,
    supersedes: Optional[List[str]] = None,
    confidence: float = 0.7,
) -> ToolResponse:
    """Save a consolidated learning as a scoped Learning artifact.

    Args:
        content: The lesson, in prose ready for prompt injection.
        stack: The stack (passed automatically).
        source_artifact_ids: Episodic artifact ids the lesson was distilled from.
        supersedes: Existing same-scope Learning ids this lesson replaces.
        confidence: Self-assessed confidence in [0, 1].

    Returns:
        ToolResponse with the new learning's id and its stamped scope.
    """
    try:
        environment = stack.agent.environment
        env_vars = getattr(environment, "env_vars", None) or {}
        scope = env_vars.get(DREAM_SCOPE_KEY) or {}

        interaction = stack.interactions[-1]
        learning = Learning(
            interaction=interaction,
            content=content,
            scope_config=scope.get("config"),
            scope_task=scope.get("task"),
            scope_app=scope.get("app"),
            source_artifact_ids=list(source_artifact_ids or []),
            supersedes=[] if supersedes is None else supersedes,
            confidence=float(confidence),
        )
        _validate_supersedes(environment.storage, learning)
        interaction.add_artifact(learning)

        # Persist immediately and self-rate (autonomy keeps the quality gate;
        # source="agent" so human ratings remain distinguishable). --dry-run
        # produces the learning but writes nothing.
        dry_run = bool(env_vars.get(DREAM_DRY_RUN_KEY))
        if not dry_run and environment.storage is not None:
            environment.storage.save_artifact(learning)
            environment.storage.save_feedback(
                ArtifactFeedback(
                    artifact_id=learning.id,
                    rating=_confidence_to_rating(float(confidence)),
                    source="agent",
                    agent_id=stack.agent.id,
                )
            )

        # Report back to the dream orchestrator (works for dry runs too).
        if isinstance(env_vars, dict):
            env_vars.setdefault(DREAM_RESULTS_KEY, []).append(
                {
                    "id": learning.id,
                    "scope_config": learning.scope_config,
                    "scope_task": learning.scope_task,
                    "supersedes": learning.supersedes,
                    "dry_run": dry_run,
                }
            )

        return ToolResponse(
            is_error=False,
            content={
                "learning": learning.id,
                "scope_config": learning.scope_config,
                "scope_task": learning.scope_task,
                "scope_app": learning.scope_app,
                "supersedes": learning.supersedes,
            },
        )

    except Exception as e:
        logging.error(f"Error saving learning: {e} {traceback.format_exc()}")
        return ToolResponse(is_error=True, content={"error": str(e)})
