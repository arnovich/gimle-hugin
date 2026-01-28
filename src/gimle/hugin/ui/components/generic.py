"""Generic fallback UI component for unknown artifact types."""

import json
from dataclasses import asdict, fields
from typing import Any, Dict

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.ui.components.base import ArtifactComponent, ComponentRegistry


@ComponentRegistry.set_fallback
class GenericComponent(ArtifactComponent):
    """Fallback UI component for artifacts without a registered component.

    Renders artifacts as JSON for debugging/inspection purposes.
    """

    def render_preview(self, artifact: Artifact) -> str:
        """Render a compact preview of the unknown artifact."""
        artifact_type = artifact.__class__.__name__
        return f"[{artifact_type}]"

    def render_detail(self, artifact: Artifact) -> str:
        """Render the artifact as formatted JSON."""
        artifact_type = artifact.__class__.__name__

        # Build a dictionary of the artifact's fields (excluding interaction)
        data: Dict[str, Any] = {}
        for f in fields(artifact):
            if f.name == "interaction":
                continue
            value = getattr(artifact, f.name)
            if hasattr(value, "__dataclass_fields__"):
                data[f.name] = asdict(value)
            else:
                data[f.name] = value

        # Add metadata
        if hasattr(artifact, "uuid"):
            data["uuid"] = artifact.uuid
        if hasattr(artifact, "created_at"):
            data["created_at"] = artifact.created_at

        try:
            json_str = json.dumps(data, indent=2, default=str)
        except (TypeError, ValueError):
            json_str = str(data)

        escaped = self._escape_html(json_str)

        return f"""
<div class="generic-artifact">
    <div class="artifact-type-badge">{artifact_type}</div>
    <pre><code>{escaped}</code></pre>
</div>
"""

    def get_styles(self) -> str:
        """Return CSS styles for generic components."""
        return """
.generic-artifact {
    padding: 0.5rem;
    border-radius: 4px;
    background: #1e1e1e;
    border: 1px dashed #4a4a4a;
}
.generic-artifact .artifact-type-badge {
    display: inline-block;
    padding: 0.2rem 0.5rem;
    background: #3c3c3c;
    color: #d4d4d4;
    border-radius: 3px;
    font-size: 0.8em;
    margin-bottom: 0.5rem;
    font-family: monospace;
}
.generic-artifact pre {
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
    font-family: 'Monaco', 'Menlo', monospace;
    font-size: 12px;
    color: #9cdcfe;
    max-height: 400px;
    overflow: auto;
}
"""

    def _escape_html(self, content: str) -> str:
        """Escape HTML special characters."""
        return (
            content.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
