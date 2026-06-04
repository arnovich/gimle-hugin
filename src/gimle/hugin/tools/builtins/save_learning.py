"""Save learning builtin tool: persist a consolidated 'dreaming' learning.

Used by the dream worker (``hugin dream``). Mirrors ``save_insight`` but writes
a ``Learning`` artifact, stamps its scope from the dream run context
(``environment.env_vars["dream_scope"]``), and self-rates it via
``ArtifactFeedback`` (``source="agent"``).
"""

import logging
import traceback
from typing import TYPE_CHECKING, List, Optional

from gimle.hugin.artifacts.feedback import ArtifactFeedback
from gimle.hugin.artifacts.learning import Learning
from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

# env_vars keys the dream run uses to communicate with this tool.
DREAM_SCOPE_KEY = "dream_scope"
DREAM_DRY_RUN_KEY = "dream_dry_run"
DREAM_RESULTS_KEY = "dream_results"


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
        "artifact ids it was distilled from, and your confidence (0-1)."
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
    confidence: float = 0.7,
) -> ToolResponse:
    """Save a consolidated learning as a scoped Learning artifact.

    Args:
        content: The lesson, in prose ready for prompt injection.
        stack: The stack (passed automatically).
        source_artifact_ids: Episodic artifact ids the lesson was distilled from.
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
            confidence=float(confidence),
        )
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
            },
        )

    except Exception as e:
        logging.error(f"Error saving learning: {e} {traceback.format_exc()}")
        return ToolResponse(is_error=True, content={"error": str(e)})
