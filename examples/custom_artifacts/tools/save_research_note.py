"""Save research note tool - Creates ResearchNote artifacts.

This module demonstrates how to create a tool that produces custom artifacts.
The tool:
- Receives parameters from the LLM
- Creates an instance of your custom artifact
- Attaches the artifact to the current interaction
"""

from typing import TYPE_CHECKING, List, Optional

# Import the custom artifact
from custom_artifacts.artifact_types.research_note import ResearchNote

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def save_research_note(
    title: str,
    content: str,
    stack: "Stack",
    branch: Optional[str] = None,
    tags: Optional[List[str]] = None,
    source: Optional[str] = None,
    confidence: str = "medium",
) -> ToolResponse:
    """Save a research note as a ResearchNote artifact.

    Creates a ResearchNote artifact with structured fields and
    attaches it to the current interaction.

    Args:
        title: Title for the research note
        content: Main content (markdown supported)
        stack: The stack (auto-injected)
        branch: Optional branch identifier (auto-injected)
        tags: List of tags for categorization
        source: Source URL or reference
        confidence: Confidence level (low/medium/high)

    Returns:
        ToolResponse with the artifact uuid
    """
    # Create the custom artifact
    artifact = ResearchNote(
        interaction=stack.interactions[-1],
        title=title,
        content=content,
        tags=tags or [],
        source=source,
        confidence=confidence,
    )

    # Attach to the current interaction
    stack.interactions[-1].add_artifact(artifact)

    return ToolResponse(
        is_error=False,
        content={
            "artifact_id": artifact.id,
            "title": title,
            "tags": tags or [],
            "confidence": confidence,
            "message": f"Research note '{title}' saved successfully",
        },
    )
