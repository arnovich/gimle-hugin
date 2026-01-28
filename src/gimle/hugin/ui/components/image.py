"""Image artifact UI component."""

from typing import cast

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.artifacts.image import Image
from gimle.hugin.ui.components.base import ArtifactComponent, ComponentRegistry


@ComponentRegistry.register("Image")
class ImageComponent(ArtifactComponent):
    """UI component for Image artifacts."""

    def render_preview(self, artifact: Artifact) -> str:
        """Render a compact preview of the image artifact."""
        image = cast(Image, artifact)
        name = image.name or "Image"
        return f"IMG {self._escape_html(name)}"

    def render_detail(self, artifact: Artifact) -> str:
        """Render the full image artifact with the image displayed."""
        image = cast(Image, artifact)

        name_html = ""
        if image.name:
            escaped_name = self._escape_html(image.name)
            name_html = f'<div class="image-name">{escaped_name}</div>'

        description_html = ""
        if image.description:
            escaped_desc = self._escape_html(image.description)
            description_html = (
                f'<p class="image-description">{escaped_desc}</p>'
            )

        # Create data URL for the image (lazy load from storage)
        try:
            content_base64 = image.get_content_base64()
            data_url = f"data:{image.content_type};base64,{content_base64}"
        except Exception as e:
            return f"""
<div class="image-artifact error">
    {name_html}
    <p class="error-message">Error loading image: {self._escape_html(str(e))}</p>
</div>
"""

        return f"""
<div class="image-artifact">
    {name_html}
    {description_html}
    <div class="image-container">
        <img src="{data_url}" alt="{self._escape_html(image.name or 'Image')}" class="artifact-image" />
    </div>
</div>
"""

    def get_styles(self) -> str:
        """Return CSS styles for image components."""
        return """
.image-artifact {
    padding: 1rem;
    border-radius: 4px;
    background: #252526;
    border: 1px solid #3c3c3c;
}
.image-artifact .image-name {
    font-weight: 600;
    color: #4ec9b0;
    margin-bottom: 0.5rem;
    font-family: 'Monaco', 'Menlo', monospace;
}
.image-artifact .image-description {
    color: #9cdcfe;
    font-size: 0.9em;
    margin-bottom: 0.75rem;
}
.image-artifact .image-container {
    display: flex;
    justify-content: center;
    background: #1e1e1e;
    border-radius: 4px;
    padding: 0.5rem;
}
.image-artifact .artifact-image {
    max-width: 100%;
    max-height: 600px;
    height: auto;
    border-radius: 2px;
}
"""

    def _escape_html(self, content: str) -> str:
        """Escape HTML special characters."""
        return (
            content.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
