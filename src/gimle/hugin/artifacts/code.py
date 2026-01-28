"""Code Artifact for storing source code with language metadata."""

from dataclasses import dataclass
from typing import Literal, Optional

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.utils.uuid import with_uuid

# Common programming languages for syntax highlighting
CodeLanguage = Literal[
    "python",
    "javascript",
    "typescript",
    "java",
    "c",
    "cpp",
    "csharp",
    "go",
    "rust",
    "ruby",
    "php",
    "swift",
    "kotlin",
    "scala",
    "shell",
    "bash",
    "sql",
    "html",
    "css",
    "yaml",
    "json",
    "xml",
    "markdown",
    "text",
]


@with_uuid
@Artifact.register("Code")
@dataclass
class Code(Artifact):
    """An artifact that stores source code with language metadata.

    This artifact is designed for storing generated code, scripts, and
    configuration files with proper syntax highlighting support in the UI.

    Attributes:
        content: The content of the code.
        language: The language of the code.
        filename: The filename of the code.
        description: The description of the code.
    """

    content: str
    language: str = "text"
    filename: Optional[str] = None
    description: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate language after initialization."""
        # Normalize common language aliases
        language_aliases = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "yml": "yaml",
            "sh": "shell",
            "c++": "cpp",
            "c#": "csharp",
        }
        if self.language.lower() in language_aliases:
            self.language = language_aliases[self.language.lower()]

    def get_file_extension(self) -> str:
        """Get the typical file extension for this language.

        Returns:
            The file extension for the language.
        """
        extensions = {
            "python": ".py",
            "javascript": ".js",
            "typescript": ".ts",
            "java": ".java",
            "c": ".c",
            "cpp": ".cpp",
            "csharp": ".cs",
            "go": ".go",
            "rust": ".rs",
            "ruby": ".rb",
            "php": ".php",
            "swift": ".swift",
            "kotlin": ".kt",
            "scala": ".scala",
            "shell": ".sh",
            "bash": ".sh",
            "sql": ".sql",
            "html": ".html",
            "css": ".css",
            "yaml": ".yaml",
            "json": ".json",
            "xml": ".xml",
            "markdown": ".md",
            "text": ".txt",
        }
        return extensions.get(self.language.lower(), ".txt")
