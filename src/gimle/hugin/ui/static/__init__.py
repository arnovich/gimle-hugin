"""Static file utilities for the UI module."""

from pathlib import Path
from typing import Dict, Optional

# Path to the static directory
STATIC_DIR = Path(__file__).parent


def get_static_path() -> Path:
    """Get the path to the static directory.

    Returns:
        Path to the static directory containing css/, js/, templates/
    """
    return STATIC_DIR


def load_template(name: str) -> str:
    """Load an HTML template from the templates directory.

    Args:
        name: Template filename (e.g., 'monitor.html', 'agent.html')

    Returns:
        Template content as string

    Raises:
        FileNotFoundError: If the template doesn't exist
    """
    template_path = STATIC_DIR / "templates" / name
    return template_path.read_text(encoding="utf-8")


def load_css(name: str) -> str:
    """Load a CSS file from the css directory.

    Args:
        name: CSS filename (e.g., 'monitor.css', 'agent.css')

    Returns:
        CSS content as string

    Raises:
        FileNotFoundError: If the file doesn't exist
    """
    css_path = STATIC_DIR / "css" / name
    return css_path.read_text(encoding="utf-8")


def load_js(name: str) -> str:
    """Load a JavaScript file from the js directory.

    Args:
        name: JavaScript filename (e.g., 'monitor.js', 'agent.js')

    Returns:
        JavaScript content as string

    Raises:
        FileNotFoundError: If the file doesn't exist
    """
    js_path = STATIC_DIR / "js" / name
    return js_path.read_text(encoding="utf-8")


def render_template(name: str, **context: str) -> str:
    """Load and render a template with the given context.

    Uses simple string formatting with {key} placeholders.

    Args:
        name: Template filename
        **context: Key-value pairs to substitute in the template

    Returns:
        Rendered template as string

    Example:
        html = render_template('agent.html',
            title='My Agent',
            agent_id='123',
            num_interactions='5'
        )
    """
    template = load_template(name)
    return template.format(**context)


def get_mime_type(path: str) -> str:
    """Get the MIME type for a file based on its extension.

    Args:
        path: File path or name

    Returns:
        MIME type string
    """
    mime_types: Dict[str, str] = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
    }

    suffix = Path(path).suffix.lower()
    return mime_types.get(suffix, "application/octet-stream")


def serve_static_file(path: str) -> Optional[bytes]:
    """Load a static file by its relative path.

    Args:
        path: Relative path from static directory (e.g., 'css/monitor.css')

    Returns:
        File contents as bytes, or None if not found
    """
    # Prevent directory traversal attacks
    try:
        full_path = (STATIC_DIR / path).resolve()
        if not str(full_path).startswith(str(STATIC_DIR.resolve())):
            return None

        if full_path.is_file():
            return full_path.read_bytes()
    except Exception:
        pass

    return None
