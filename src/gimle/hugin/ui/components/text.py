"""Text artifact UI component."""

from typing import cast

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.artifacts.text import Text
from gimle.hugin.ui.components.base import ArtifactComponent, ComponentRegistry


@ComponentRegistry.register("Text")
class TextComponent(ArtifactComponent):
    """UI component for Text artifacts."""

    def render_preview(self, artifact: Artifact) -> str:
        """Render a compact preview of the text artifact."""
        text = cast(Text, artifact)
        # Show format icon and truncated content
        icon = self._get_format_icon(text.format)
        preview = text.content[:50].replace("\n", " ")
        if len(text.content) > 50:
            preview += "..."
        return f"{icon} {preview}"

    def render_detail(self, artifact: Artifact) -> str:
        """Render the full text artifact."""
        text = cast(Text, artifact)
        return self._render_content(text)

    def get_styles(self) -> str:
        """Return CSS styles for text components."""
        return """
.text-artifact {
    padding: 1rem;
    border-radius: var(--radius-md, 6px);
    background: var(--bg-secondary, #f9fafb);
    border: 1px solid var(--border-light, #e5e7eb);
    overflow: auto;
    max-height: 500px;
    color: var(--text-primary, #111827);
}
.text-artifact pre {
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
    font-family: 'JetBrains Mono', 'Monaco', 'Menlo', monospace;
    font-size: 0.8125rem;
    line-height: 1.6;
    background: var(--bg-tertiary, #f3f4f6);
    padding: 0.75rem;
    border-radius: var(--radius-sm, 4px);
    border: 1px solid var(--border-light, #e5e7eb);
}
.text-artifact code {
    font-family: 'JetBrains Mono', 'Monaco', 'Menlo', monospace;
}
.text-artifact.json,
.text-artifact.xml {
    background: var(--bg-tertiary, #f3f4f6);
}
.text-artifact.json pre,
.text-artifact.xml pre {
    background: transparent;
    border: none;
    padding: 0;
}
[data-theme="dark"] .text-artifact.json,
[data-theme="dark"] .text-artifact.xml {
    background: #0d1117;
}

/* Markdown styling */
.text-artifact.markdown {
    background: var(--bg-primary, #ffffff);
    line-height: 1.7;
}
.text-artifact.markdown h1 {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--text-primary, #111827);
    margin: 1.5rem 0 0.75rem 0;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-light, #e5e7eb);
}
.text-artifact.markdown h2 {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-primary, #111827);
    margin: 1.25rem 0 0.5rem 0;
}
.text-artifact.markdown h3 {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--text-primary, #111827);
    margin: 1rem 0 0.5rem 0;
}
.text-artifact.markdown h4,
.text-artifact.markdown h5,
.text-artifact.markdown h6 {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary, #111827);
    margin: 0.75rem 0 0.5rem 0;
}
.text-artifact.markdown p {
    margin: 0 0 1rem 0;
    color: var(--text-primary, #111827);
}
.text-artifact.markdown a {
    color: var(--accent-primary, #3b82f6);
    text-decoration: none;
}
.text-artifact.markdown a:hover {
    text-decoration: underline;
}
.text-artifact.markdown code {
    background: var(--bg-tertiary, #f3f4f6);
    padding: 0.2em 0.4em;
    border-radius: var(--radius-sm, 4px);
    font-size: 0.875em;
    color: var(--text-primary, #111827);
}
.text-artifact.markdown pre {
    background: var(--bg-tertiary, #f3f4f6);
    margin: 1rem 0;
}
.text-artifact.markdown pre code {
    background: transparent;
    padding: 0;
}
.text-artifact.markdown ul,
.text-artifact.markdown ol {
    margin: 0 0 1rem 0;
    padding-left: 1.5rem;
}
.text-artifact.markdown li {
    margin: 0.25rem 0;
}
.text-artifact.markdown blockquote {
    margin: 1rem 0;
    padding: 0.5rem 1rem;
    border-left: 3px solid var(--accent-primary, #3b82f6);
    background: var(--bg-secondary, #f9fafb);
    color: var(--text-secondary, #6b7280);
}
.text-artifact.markdown table {
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
}
.text-artifact.markdown th,
.text-artifact.markdown td {
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border-light, #e5e7eb);
    text-align: left;
}
.text-artifact.markdown th {
    background: var(--bg-secondary, #f9fafb);
    font-weight: 600;
}
.text-artifact.markdown hr {
    border: none;
    border-top: 1px solid var(--border-light, #e5e7eb);
    margin: 1.5rem 0;
}

/* Dark mode adjustments */
[data-theme="dark"] .text-artifact {
    background: var(--bg-secondary, #1f2937);
    border-color: var(--border-light, #374151);
}
[data-theme="dark"] .text-artifact pre {
    background: #0d1117;
    border-color: var(--border-medium, #4b5563);
}
[data-theme="dark"] .text-artifact.markdown {
    background: var(--bg-primary, #111827);
}
[data-theme="dark"] .text-artifact.markdown code {
    background: #0d1117;
}
[data-theme="dark"] .text-artifact.markdown blockquote {
    background: var(--bg-tertiary, #374151);
}
[data-theme="dark"] .text-artifact.markdown th {
    background: var(--bg-tertiary, #374151);
}
"""

    def _get_format_icon(self, format: str) -> str:
        """Get an icon for the text format."""
        icons = {
            "markdown": "MD",
            "html": "HTML",
            "json": "JSON",
            "xml": "XML",
            "plain": "TXT",
        }
        return icons.get(format, "TXT")

    def _render_content(self, text: Text) -> str:
        """Render text content based on its format."""
        if text.format == "markdown":
            return self._render_markdown(text.content)
        elif text.format == "html":
            return f'<div class="text-artifact html">{text.content}</div>'
        elif text.format == "json":
            escaped = self._escape_html(text.content)
            return f'<div class="text-artifact json"><pre><code>{escaped}</code></pre></div>'
        elif text.format == "xml":
            escaped = self._escape_html(text.content)
            return f'<div class="text-artifact xml"><pre><code>{escaped}</code></pre></div>'
        else:  # plain
            escaped = self._escape_html(text.content)
            return (
                f'<div class="text-artifact plain"><pre>{escaped}</pre></div>'
            )

    def _escape_html(self, content: str) -> str:
        """Escape HTML special characters."""
        return (
            content.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def _render_markdown(self, content: str) -> str:
        """Convert markdown to HTML."""
        try:
            import markdown
        except ImportError:
            escaped = self._escape_html(content)
            return f'<div class="text-artifact markdown"><pre>{escaped}</pre></div>'

        extensions_to_try = [
            ["extra", "tables", "fenced_code"],
            ["extra", "tables"],
            ["extra"],
            ["tables", "fenced_code"],
            ["tables"],
            [],
        ]

        html = None
        for ext_list in extensions_to_try:
            try:
                if ext_list:
                    html = markdown.markdown(content, extensions=ext_list)
                else:
                    html = markdown.markdown(content)
                break
            except Exception:
                continue

        if html is None:
            escaped = self._escape_html(content)
            html = f"<pre>{escaped}</pre>"

        return f'<div class="text-artifact markdown">{html}</div>'
