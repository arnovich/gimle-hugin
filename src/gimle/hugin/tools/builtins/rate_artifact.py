"""Rate artifact builtin tool module."""

import logging
from typing import TYPE_CHECKING

from gimle.hugin.artifacts.feedback import ArtifactFeedback
from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

logger = logging.getLogger(__name__)


@Tool.register(
    name="builtins.rate_artifact",
    description=(
        "Rate an artifact on a scale of 1-5. "
        "Use this to provide feedback on how useful or "
        "relevant an artifact was."
    ),
    parameters={
        "artifact_id": {
            "type": "string",
            "description": "UUID of the artifact to rate",
            "required": True,
        },
        "rating": {
            "type": "integer",
            "description": "Rating from 1 (poor) to 5 (excellent)",
            "required": True,
        },
        "comment": {
            "type": "string",
            "description": "Optional comment explaining the rating",
            "required": False,
        },
    },
    is_interactive=False,
)
def rate_artifact(
    artifact_id: str,
    rating: int,
    stack: "Stack",
    comment: str = "",
) -> ToolResponse:
    """Rate an artifact.

    Args:
        artifact_id: UUID of the artifact to rate.
        rating: Rating from 1 to 5.
        stack: The stack.
        comment: Optional comment.

    Returns:
        ToolResponse with the feedback uuid.
    """
    storage = stack.agent.environment.storage
    if storage is None:
        return ToolResponse(
            is_error=True,
            content={"error": "No storage configured"},
        )

    # Verify artifact exists
    try:
        storage.load_artifact(artifact_id)
    except Exception:
        return ToolResponse(
            is_error=True,
            content={"error": f"Artifact {artifact_id} not found"},
        )

    # Create feedback — let the dataclass validate
    try:
        feedback = ArtifactFeedback(
            artifact_id=artifact_id,
            rating=rating,
            comment=comment or None,
            agent_id=stack.agent.id,
        )
    except (ValueError, TypeError) as e:
        return ToolResponse(is_error=True, content={"error": str(e)})

    # Check for existing rating from this agent
    for fb_uuid in storage.list_feedback(artifact_id):
        try:
            existing = storage.load_feedback(fb_uuid)
            if existing.agent_id == stack.agent.id:
                return ToolResponse(
                    is_error=True,
                    content={
                        "error": (f"Already rated artifact {artifact_id}")
                    },
                )
        except (ValueError, OSError):
            continue

    storage.save_feedback(feedback)

    logger.info(
        "Saved feedback %s for artifact %s (rating=%d)",
        feedback.id,
        artifact_id,
        rating,
    )

    return ToolResponse(
        is_error=False,
        content={"feedback_id": feedback.id},
    )
