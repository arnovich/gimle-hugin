"""Text artifact renderer."""

from typing import cast

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.artifacts.text import Text
from gimle.hugin.ui.artifacts.base import ArtifactRenderer


@ArtifactRenderer.register("Text")
class TextArtifactRenderer(ArtifactRenderer):
    """Renderer for Text artifacts."""

    def can_render(self, artifact: Artifact) -> bool:
        """Check if this renderer can handle the artifact."""
        return isinstance(artifact, Text)

    def render(self, artifact: Artifact, format: str = "html") -> str:
        """
        Render a Text artifact to the specified format.

        Args:
            artifact: The Text artifact to render
            format: The target format (currently only "html" is supported)

        Returns:
            The rendered artifact as a string
        """
        if not self.can_render(artifact):
            raise ValueError(f"Cannot render artifact: {artifact}")
        if format == "html":
            return self._render_to_html(cast(Text, artifact))
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _render_to_html(self, text_artifact: Text) -> str:
        """
        Render a Text artifact to HTML based on its format.

        Args:
            text_artifact: The Text artifact to render

        Returns:
            The rendered HTML string
        """
        if text_artifact.format == "markdown":
            return self._markdown_to_html(text_artifact.content)
        elif text_artifact.format == "html":
            return text_artifact.content
        elif text_artifact.format == "plain":
            # Escape HTML and wrap in <pre> tags
            escaped = (
                text_artifact.content.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            return f"<pre>{escaped}</pre>"
        elif text_artifact.format == "json":
            # Format JSON with syntax highlighting (basic)
            escaped = (
                text_artifact.content.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            return f'<pre class="json"><code>{escaped}</code></pre>'
        elif text_artifact.format == "xml":
            # Escape HTML and wrap in <pre> tags
            escaped = (
                text_artifact.content.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            return f'<pre class="xml"><code>{escaped}</code></pre>'
        raise ValueError(f"Unsupported format: {text_artifact.format}")

    def _markdown_to_html(self, markdown_text: str) -> str:
        """
        Convert markdown text to HTML.

        Args:
            markdown_text: The markdown content to convert

        Returns:
            The HTML representation of the markdown
        """
        try:
            import markdown
        except ImportError:
            raise ImportError(
                "The 'markdown' package is required for markdown rendering. "
                "Install it with: pip install markdown"
            )

        # Try to use extensions, but fall back gracefully if they're not available
        # Start with basic extensions that are usually available
        extensions_to_try = [
            ["extra", "tables", "fenced_code"],  # Standard extensions
            ["extra", "tables"],  # Without fenced_code
            ["extra"],  # Just extra
            ["tables", "fenced_code"],  # Without extra
            ["tables"],  # Just tables
            [],  # No extensions (basic markdown)
        ]

        html = None
        last_error = None

        for ext_list in extensions_to_try:
            try:
                # Special handling for codehilite (requires Pygments)
                if "codehilite" in ext_list:
                    try:
                        import pygments  # noqa: F401
                    except ImportError:
                        # Skip codehilite if Pygments is not available
                        continue

                # Try to convert with these extensions
                if ext_list:
                    html = markdown.markdown(markdown_text, extensions=ext_list)
                else:
                    html = markdown.markdown(markdown_text)

                # Success! Break out of the loop
                break
            except Exception as e:
                # Try next set of extensions
                last_error = e
                continue

        # If all attempts failed, fall back to escaped plain text
        if html is None:
            import html as html_module

            html = f"<pre>{html_module.escape(markdown_text)}</pre>"
            # Log the error but don't fail completely
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"Markdown conversion failed with all extension combinations: {last_error}, "
                "rendering as plain text"
            )

        return html
