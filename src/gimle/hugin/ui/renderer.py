"""Main renderer module for dispatching to appropriate renderers."""

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.ui.artifacts.base import ArtifactRenderer


def render_artifact(artifact: Artifact, format: str = "html") -> str:
    """
    Render an artifact to a specified format.

    This function automatically selects the appropriate renderer based on
    the artifact type using the registry.

    Args:
        artifact: The artifact to render
        format: The target format (currently only "html" is supported)

    Returns:
        The rendered artifact as a string

    Raises:
        ValueError: If the format is not supported or no renderer is found
    """
    renderer = ArtifactRenderer.get_renderer(artifact)
    return renderer.render(artifact, format=format)


def render_artifact_to_html(artifact: Artifact) -> str:
    """
    Render an artifact to HTML.

    Convenience function that calls render_artifact with format="html".

    Args:
        artifact: The artifact to render

    Returns:
        The artifact rendered as HTML string
    """
    return render_artifact(artifact, format="html")
