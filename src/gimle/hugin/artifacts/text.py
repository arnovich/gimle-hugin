"""Text Artifact for storing text content in various formats."""

from dataclasses import dataclass
from typing import Literal

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.utils.uuid import with_uuid

TextFormat = Literal["markdown", "xml", "plain", "html", "json"]


@with_uuid
@Artifact.register("Text")
@dataclass
class Text(Artifact):
    """An artifact that stores text content in a specific format.

    Attributes:
        content: The content of the text.
        format: The format of the text.
    """

    content: str
    format: TextFormat = "plain"

    def __post_init__(self) -> None:
        """Validate format after initialization.

        Returns:
            The format of the text.
        """
        valid_formats = ["markdown", "xml", "plain", "html", "json"]
        if self.format not in valid_formats:
            raise ValueError(
                f"Invalid format '{self.format}'. Must be one of: {', '.join(valid_formats)}"
            )
