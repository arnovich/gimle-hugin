"""File artifact UI component."""

from typing import cast

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.artifacts.file import File
from gimle.hugin.ui.components.base import ArtifactComponent, ComponentRegistry


@ComponentRegistry.register("File")
class FileComponent(ArtifactComponent):
    """UI component for File artifacts."""

    def render_preview(self, artifact: Artifact) -> str:
        """Render a compact preview of the file artifact."""
        file = cast(File, artifact)
        icon = self._get_file_icon(file.path)
        return f"{icon} {file.path}"

    def render_detail(self, artifact: Artifact) -> str:
        """Render the full file artifact details."""
        file = cast(File, artifact)
        icon = self._get_file_icon(file.path)

        description_html = ""
        if file.description:
            escaped_desc = self._escape_html(file.description)
            description_html = f'<p class="file-description">{escaped_desc}</p>'

        escaped_path = self._escape_html(file.path)

        return f"""
<div class="file-artifact">
    <div class="file-header">
        <span class="file-icon">{icon}</span>
        <span class="file-name">{escaped_path}</span>
    </div>
    {description_html}
</div>
"""

    def get_styles(self) -> str:
        """Return CSS styles for file components."""
        return """
.file-artifact {
    padding: 1rem;
    border-radius: 4px;
    background: #252526;
    border: 1px solid #3c3c3c;
}
.file-artifact .file-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-family: 'Monaco', 'Menlo', monospace;
}
.file-artifact .file-icon {
    font-size: 1.2em;
}
.file-artifact .file-name {
    color: #4ec9b0;
    font-weight: 500;
}
.file-artifact .file-description {
    margin-top: 0.5rem;
    color: #9cdcfe;
    font-size: 0.9em;
}
"""

    def _escape_html(self, content: str) -> str:
        """Escape HTML special characters."""
        return (
            content.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def _get_file_icon(self, path: str) -> str:
        """Get an icon for the file type based on extension."""
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""

        icon_map = {
            # Images
            "png": "IMG",
            "jpg": "IMG",
            "jpeg": "IMG",
            "gif": "IMG",
            "svg": "IMG",
            "webp": "IMG",
            # Documents
            "pdf": "PDF",
            "doc": "DOC",
            "docx": "DOC",
            "txt": "TXT",
            "md": "MD",
            # Code
            "py": "PY",
            "js": "JS",
            "ts": "TS",
            "html": "HTML",
            "css": "CSS",
            "json": "JSON",
            "yaml": "YAML",
            "yml": "YAML",
            # Data
            "csv": "CSV",
            "xlsx": "XLS",
            "xls": "XLS",
        }

        return icon_map.get(ext, "FILE")
