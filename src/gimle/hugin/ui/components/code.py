"""Code artifact UI component with syntax highlighting."""

from typing import cast

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.artifacts.code import Code
from gimle.hugin.ui.components.base import ArtifactComponent, ComponentRegistry


@ComponentRegistry.register("Code")
class CodeComponent(ArtifactComponent):
    """UI component for Code artifacts with syntax highlighting."""

    def render_preview(self, artifact: Artifact) -> str:
        """Render a compact preview of the code artifact."""
        code = cast(Code, artifact)
        # Show language badge and filename or first line
        lang_badge = f'<span class="lang-badge">{code.language.upper()}</span>'

        if code.filename:
            preview_text = code.filename
        else:
            # Show first line of code, truncated
            first_line = code.content.split("\n")[0][:40]
            if len(code.content.split("\n")[0]) > 40:
                first_line += "..."
            preview_text = first_line

        return f'{lang_badge} <span class="code-preview">{self._escape_html(preview_text)}</span>'

    def render_detail(self, artifact: Artifact) -> str:
        """Render the full code artifact with syntax highlighting."""
        code = cast(Code, artifact)

        # Build header with filename and language
        header_parts = []
        if code.filename:
            header_parts.append(
                f'<span class="filename">{self._escape_html(code.filename)}</span>'
            )
        header_parts.append(
            f'<span class="lang-badge">{code.language.upper()}</span>'
        )
        header = " ".join(header_parts)

        # Description if available
        desc_html = ""
        if code.description:
            desc_html = f'<div class="code-description">{self._escape_html(code.description)}</div>'

        # Render code with line numbers
        lines = code.content.split("\n")
        line_numbers = (
            '<div class="line-numbers">'
            + "<br>".join(str(i) for i in range(1, len(lines) + 1))
            + "</div>"
        )
        code_content = (
            f'<pre class="code-content language-{code.language}">'
            f"<code>{self._escape_html(code.content)}</code></pre>"
        )

        return f"""
<div class="code-artifact">
    <div class="code-header">{header}</div>
    {desc_html}
    <div class="code-body">
        {line_numbers}
        {code_content}
    </div>
</div>
"""

    def get_styles(self) -> str:
        """Return CSS styles for code components."""
        return """
.code-artifact {
    border-radius: 6px;
    background: #1e1e1e;
    overflow: hidden;
    margin: 0.5rem 0;
}
.code-artifact .code-header {
    background: #2d2d2d;
    padding: 0.5rem 1rem;
    border-bottom: 1px solid #404040;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.code-artifact .filename {
    color: #d4d4d4;
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 13px;
}
.code-artifact .lang-badge {
    background: #4a5568;
    color: #e2e8f0;
    padding: 0.15rem 0.5rem;
    border-radius: 3px;
    font-size: 11px;
    font-weight: 600;
}
.code-artifact .code-description {
    padding: 0.5rem 1rem;
    background: #252526;
    color: #9cdcfe;
    font-size: 13px;
    border-bottom: 1px solid #404040;
}
.code-artifact .code-body {
    display: flex;
    overflow: auto;
    max-height: 500px;
}
.code-artifact .line-numbers {
    padding: 1rem 0.75rem;
    text-align: right;
    color: #6e7681;
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 13px;
    line-height: 1.5;
    user-select: none;
    background: #1a1a1a;
    border-right: 1px solid #404040;
}
.code-artifact .code-content {
    flex: 1;
    margin: 0;
    padding: 1rem;
    background: transparent;
    overflow-x: auto;
}
.code-artifact .code-content code {
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 13px;
    line-height: 1.5;
    color: #d4d4d4;
}
/* Language-specific colors */
.code-artifact .language-python code { color: #9cdcfe; }
.code-artifact .language-javascript code { color: #dcdcaa; }
.code-artifact .language-typescript code { color: #4ec9b0; }
.code-artifact .language-yaml code { color: #ce9178; }
.code-artifact .language-json code { color: #9cdcfe; }
.code-artifact .language-shell code { color: #6a9955; }
.code-artifact .language-bash code { color: #6a9955; }
.code-artifact .language-sql code { color: #c586c0; }
/* Preview styling */
.code-preview {
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 12px;
    color: #9cdcfe;
}
.lang-badge {
    background: #4a5568;
    color: #e2e8f0;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 600;
    margin-right: 0.5rem;
}
"""

    def _escape_html(self, content: str) -> str:
        """Escape HTML special characters."""
        return (
            content.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
