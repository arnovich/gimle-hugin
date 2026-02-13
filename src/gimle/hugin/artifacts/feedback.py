"""Artifact feedback model."""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from gimle.hugin.utils.uuid import with_uuid

VALID_RATINGS = range(1, 6)
VALID_SOURCES = ("agent", "human")


@with_uuid
@dataclass
class ArtifactFeedback:
    """Feedback on an artifact.

    Attributes:
        artifact_id: UUID of the artifact being rated.
        rating: Integer rating from 1 (poor) to 5 (excellent).
        comment: Optional free-text comment.
        agent_id: Optional UUID of the agent giving feedback.
        source: Who submitted the feedback ("agent" or "human").
    """

    artifact_id: str
    rating: int
    comment: Optional[str] = None
    agent_id: Optional[str] = None
    source: str = "agent"

    @property
    def id(self) -> str:
        """Get the uuid of the feedback."""
        return str(self.uuid)

    @id.setter
    def id(self, id: str) -> None:
        """Set the uuid of the feedback."""
        self.uuid = id

    def __post_init__(self) -> None:
        """Validate fields after initialization."""
        # Coerce float to int (LLMs often send 3.0 instead of 3)
        if isinstance(self.rating, float) and self.rating == int(self.rating):
            self.rating = int(self.rating)
        if not isinstance(self.rating, int):
            raise TypeError(
                f"Rating must be an integer, got {type(self.rating).__name__}"
            )
        if self.rating not in VALID_RATINGS:
            raise ValueError(
                f"Rating must be between 1 and 5, got {self.rating}"
            )
        if self.source not in VALID_SOURCES:
            raise ValueError(
                f"Source must be one of {VALID_SOURCES}, "
                f"got {self.source!r}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize feedback to a dictionary."""
        data: Dict[str, Any] = {
            "artifact_id": self.artifact_id,
            "rating": self.rating,
            "uuid": self.uuid,
            "source": self.source,
        }
        if self.comment is not None:
            data["comment"] = self.comment
        if self.agent_id is not None:
            data["agent_id"] = self.agent_id
        created_at = getattr(self, "created_at", None)
        if created_at is not None:
            data["created_at"] = created_at
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactFeedback":
        """Deserialize feedback from a dictionary."""
        return cls(
            artifact_id=data["artifact_id"],
            rating=data["rating"],
            comment=data.get("comment"),
            agent_id=data.get("agent_id"),
            source=data.get("source", "agent"),
            uuid=data.get("uuid"),  # type: ignore[call-arg]
            created_at=data.get("created_at"),
        )
