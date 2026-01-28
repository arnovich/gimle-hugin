"""Gimle File Artifact."""

import base64
import mimetypes
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.utils.uuid import with_uuid

if TYPE_CHECKING:
    from gimle.hugin.storage.storage import Storage


@Artifact.register("File")
@with_uuid
@dataclass
class File(Artifact):
    """A file artifact with lazy-loaded content stored in storage.

    Attributes:
        path: The path to the file.
        name: The name of the file.
        content_type: The content type of the file.
        description: The description of the file.
        _storage: The storage to use for the file.
    """

    path: str = ""
    name: str = ""
    content_type: str = ""
    description: str = ""
    _storage: Optional["Storage"] = field(
        default=None, repr=False, compare=False
    )

    def get_content(self) -> bytes:
        """Load and return the file content as bytes.

        Returns:
            The content of the file as bytes.
        """
        if not self.path:
            raise ValueError("File has no path set")
        if self._storage is None:
            raise ValueError("Storage not set - cannot load file")
        return self._storage.load_file(self.path)

    def get_content_base64(self) -> str:
        """Load and return the file content as base64-encoded string.

        Returns:
            The content of the file as a base64-encoded string.
        """
        return base64.b64encode(self.get_content()).decode("utf-8")

    @classmethod
    def create_from_path(
        cls,
        interaction: Interaction,
        source_path: str,
        storage: "Storage",
        name: Optional[str] = None,
        description: str = "",
    ) -> "File":
        """Create a file artifact by copying a file to storage.

        Args:
            interaction: The interaction this artifact belongs to
            source_path: Path to the source file to copy
            storage: Storage instance to save the file to
            name: Optional name (defaults to filename)
            description: Optional description

        Returns:
            The created file artifact.
        """
        # Read the file content
        with open(source_path, "rb") as f:
            content = f.read()

        # Determine name and content type
        file_name = name or os.path.basename(source_path)
        mime_type, _ = mimetypes.guess_type(source_path)
        content_type = mime_type or "application/octet-stream"

        # Get extension from source path
        _, ext = os.path.splitext(source_path)
        extension = ext.lstrip(".") if ext else ""

        # Create the artifact first to get uuid
        file_artifact = cls(
            interaction=interaction,
            name=file_name,
            content_type=content_type,
            description=description,
            _storage=storage,
        )

        # Save file to storage and get the relative path
        storage_path = storage.save_file(file_artifact.uuid, content, extension)
        file_artifact.path = storage_path

        return file_artifact

    @classmethod
    def create_from_bytes(
        cls,
        interaction: Interaction,
        content: bytes,
        storage: "Storage",
        name: str,
        content_type: str = "application/octet-stream",
        extension: str = "",
        description: str = "",
    ) -> "File":
        """Create a file artifact from raw bytes.

        Args:
            interaction: The interaction this artifact belongs to
            content: Raw bytes to store
            storage: Storage instance to save the file to
            name: Name for the file
            content_type: MIME type
            extension: File extension (without dot)
            description: Optional description

        Returns:
            The created file artifact.
        """
        file_artifact = cls(
            interaction=interaction,
            name=name,
            content_type=content_type,
            description=description,
            _storage=storage,
        )

        # Save file to storage and get the relative path
        storage_path = storage.save_file(file_artifact.uuid, content, extension)
        file_artifact.path = storage_path

        return file_artifact

    def to_dict(self) -> dict:
        """Serialize the artifact, excluding _storage.

        Returns:
            A dictionary representation of the artifact.
        """
        data = super().to_dict()
        # Remove _storage from serialization (it's not serializable)
        if "_storage" in data.get("data", {}):
            del data["data"]["_storage"]
        return data
