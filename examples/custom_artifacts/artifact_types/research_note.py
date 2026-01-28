"""ResearchNote Artifact - A custom artifact type for structured research notes.

This module demonstrates how to create a custom artifact type with:
- Custom fields specific to your domain
- Validation in __post_init__
- Registration with the Artifact registry
"""

from dataclasses import dataclass, field
from typing import List, Optional

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.utils.uuid import with_uuid


@with_uuid
@Artifact.register("ResearchNote")
@dataclass
class ResearchNote(Artifact):
    """A structured research note artifact.

    This artifact demonstrates a custom type with multiple fields,
    validation, and domain-specific structure.

    Attributes:
        title: The title of the research note
        content: The main content/body of the note (markdown supported)
        tags: List of tags for categorization
        source: Optional source URL or reference
        confidence: Confidence level in the findings (low/medium/high)
    """

    title: str
    content: str
    tags: List[str] = field(default_factory=list)
    source: Optional[str] = None
    confidence: str = "medium"
