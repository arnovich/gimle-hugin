"""ResearchNote UI Component - Custom component for displaying ResearchNote artifacts.

This module demonstrates how to create a custom UI component with:
- Preview rendering for compact views
- Detail rendering for expanded views
- Custom CSS styling
- Dark mode support
"""

from typing import TYPE_CHECKING, cast

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.ui.components.base import ArtifactComponent, ComponentRegistry

if TYPE_CHECKING:
    from custom_artifacts.artifact_types.research_note import ResearchNote


@ComponentRegistry.register("ResearchNote")
class ResearchNoteComponent(ArtifactComponent):
    """UI component for ResearchNote artifacts.

    Renders research notes with:
    - Title and confidence badge in header
    - Tags as colored pills
    - Content with markdown support
    - Source link if provided
    """

    def render_preview(self, artifact: Artifact) -> str:
        """Render a compact preview of the research note.

        Shows the title with a confidence indicator and tag count.
        """
        note = cast("ResearchNote", artifact)

        # Confidence indicator
        confidence_colors = {
            "low": "#f59e0b",  # amber
            "medium": "#3b82f6",  # blue
            "high": "#10b981",  # green
        }
        color = confidence_colors.get(note.confidence, "#6b7280")

        # Tag count badge
        tag_badge = ""
        if note.tags:
            tag_badge = (
                f' <span class="rn-tag-count">{len(note.tags)} tags</span>'
            )

        return (
            f'<span class="rn-preview">'
            f'<span class="rn-confidence-dot" style="background:{color}"></span>'
            f"{self._escape_html(note.title)}"
            f"{tag_badge}"
            f"</span>"
        )

    def render_detail(self, artifact: Artifact) -> str:
        """Render the full detail view of the research note."""
        note = cast("ResearchNote", artifact)

        # Build HTML parts
        html_parts = ['<div class="research-note">']

        # Header with title and confidence
        html_parts.append('<div class="rn-header">')
        html_parts.append(
            f'<h3 class="rn-title">{self._escape_html(note.title)}</h3>'
        )
        html_parts.append(
            f'<span class="rn-confidence rn-confidence-{note.confidence}">'
            f"{note.confidence.upper()}"
            f"</span>"
        )
        html_parts.append("</div>")

        # Tags section
        if note.tags:
            html_parts.append('<div class="rn-tags">')
            for tag in note.tags:
                html_parts.append(
                    f'<span class="rn-tag">{self._escape_html(tag)}</span>'
                )
            html_parts.append("</div>")

        # Source link
        if note.source:
            html_parts.append(
                f'<div class="rn-source">'
                f'<span class="rn-source-label">Source:</span> '
                f'<a href="{self._escape_html(note.source)}" '
                f'target="_blank" rel="noopener">'
                f"{self._escape_html(note.source)}</a>"
                f"</div>"
            )

        # Content
        html_parts.append('<div class="rn-content">')
        html_parts.append(self._render_markdown(note.content))
        html_parts.append("</div>")

        html_parts.append("</div>")

        return "\n".join(html_parts)

    def get_styles(self) -> str:
        """Return CSS styles for the ResearchNote component."""
        return """
/* ResearchNote Component Styles */
.research-note {
    padding: 1rem;
    border-radius: var(--radius-lg, 8px);
    background: var(--bg-primary, #ffffff);
    border: 1px solid var(--border-light, #e5e7eb);
}

.rn-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.75rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--border-light, #e5e7eb);
}

.rn-title {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--text-primary, #111827);
    margin: 0;
    flex: 1;
}

.rn-confidence {
    font-size: 0.6875rem;
    font-weight: 600;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.rn-confidence-low {
    background: #fef3c7;
    color: #92400e;
}

.rn-confidence-medium {
    background: #dbeafe;
    color: #1e40af;
}

.rn-confidence-high {
    background: #d1fae5;
    color: #065f46;
}

.rn-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
}

.rn-tag {
    font-size: 0.75rem;
    padding: 0.25rem 0.625rem;
    background: var(--bg-tertiary, #f3f4f6);
    color: var(--text-secondary, #6b7280);
    border-radius: 999px;
    border: 1px solid var(--border-light, #e5e7eb);
}

.rn-source {
    font-size: 0.8125rem;
    color: var(--text-secondary, #6b7280);
    margin-bottom: 0.75rem;
    padding: 0.5rem 0.75rem;
    background: var(--bg-secondary, #f9fafb);
    border-radius: var(--radius-sm, 4px);
}

.rn-source-label {
    font-weight: 500;
    color: var(--text-tertiary, #9ca3af);
}

.rn-source a {
    color: var(--accent-primary, #3b82f6);
    text-decoration: none;
    word-break: break-all;
}

.rn-source a:hover {
    text-decoration: underline;
}

.rn-content {
    line-height: 1.6;
    color: var(--text-primary, #111827);
}

.rn-content p {
    margin: 0 0 0.75rem 0;
}

.rn-content p:last-child {
    margin-bottom: 0;
}

.rn-content ul, .rn-content ol {
    margin: 0 0 0.75rem 0;
    padding-left: 1.5rem;
}

.rn-content li {
    margin: 0.25rem 0;
}

.rn-content code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.875em;
    background: var(--bg-tertiary, #f3f4f6);
    padding: 0.125rem 0.375rem;
    border-radius: 3px;
}

.rn-content pre {
    background: var(--bg-tertiary, #f3f4f6);
    border: 1px solid var(--border-light, #e5e7eb);
    border-radius: var(--radius-md, 6px);
    padding: 0.75rem;
    overflow-x: auto;
    margin: 0.75rem 0;
}

.rn-content pre code {
    background: transparent;
    padding: 0;
}

/* Preview styles */
.rn-preview {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
}

.rn-confidence-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
}

.rn-tag-count {
    font-size: 0.6875rem;
    color: var(--text-tertiary, #9ca3af);
    background: var(--bg-tertiary, #f3f4f6);
    padding: 2px 6px;
    border-radius: 3px;
}

/* Dark mode */
[data-theme="dark"] .research-note {
    background: var(--bg-secondary, #1f2937);
    border-color: var(--border-light, #374151);
}

[data-theme="dark"] .rn-header {
    border-color: var(--border-light, #374151);
}

[data-theme="dark"] .rn-confidence-low {
    background: #451a03;
    color: #fcd34d;
}

[data-theme="dark"] .rn-confidence-medium {
    background: #1e3a5f;
    color: #93c5fd;
}

[data-theme="dark"] .rn-confidence-high {
    background: #064e3b;
    color: #6ee7b7;
}

[data-theme="dark"] .rn-tag {
    background: var(--bg-tertiary, #374151);
    border-color: var(--border-medium, #4b5563);
}

[data-theme="dark"] .rn-source {
    background: var(--bg-tertiary, #374151);
}

[data-theme="dark"] .rn-content code {
    background: #0d1117;
}

[data-theme="dark"] .rn-content pre {
    background: #0d1117;
    border-color: var(--border-medium, #4b5563);
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

    def _render_markdown(self, content: str) -> str:
        """Convert markdown to HTML with fallback."""
        try:
            import markdown

            # Try with extensions, fall back gracefully
            extensions_to_try = [
                ["extra", "tables", "fenced_code"],
                ["extra"],
                [],
            ]

            for ext_list in extensions_to_try:
                try:
                    return str(markdown.markdown(content, extensions=ext_list))
                except Exception:
                    continue

            return str(markdown.markdown(content))
        except ImportError:
            # No markdown library - return escaped plain text
            escaped = self._escape_html(content)
            return f"<pre>{escaped}</pre>"
