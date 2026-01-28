"""Gimle Image Artifact."""

import base64
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.artifacts.file import File
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.utils.uuid import with_uuid

if TYPE_CHECKING:
    from gimle.hugin.storage.storage import Storage


@Artifact.register("Image")
@with_uuid
@dataclass
class Image(File):
    """An image artifact with lazy-loaded content stored in storage.

    Inherits path, name, content_type, description from File.
    """

    @classmethod
    def create_from_base64(
        cls,
        interaction: Interaction,
        content: str,
        storage: "Storage",
        content_type: str = "image/png",
        name: str = "",
        description: str = "",
    ) -> "Image":
        """Create an image artifact from base64-encoded content.

        Args:
            interaction: The interaction this artifact belongs to
            content: Base64-encoded image data
            storage: Storage instance to save the file to
            content_type: MIME type (e.g., "image/png", "image/jpeg")
            name: Optional name for the image
            description: Optional description

        Returns:
            Image artifact
        """
        # Decode base64 to bytes
        image_bytes = base64.b64decode(content)

        # Determine extension from content type
        ext_map = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/gif": "gif",
            "image/webp": "webp",
            "image/svg+xml": "svg",
        }
        extension = ext_map.get(content_type, "png")

        # Create the artifact
        image = cls(
            interaction=interaction,
            name=name,
            content_type=content_type,
            description=description,
            _storage=storage,
        )

        # Save to storage and set path
        storage_path = storage.save_file(image.uuid, image_bytes, extension)
        image.path = storage_path

        return image

    @classmethod
    def create_from_file(
        cls,
        interaction: Interaction,
        filepath: str,
        storage: "Storage",
        name: Optional[str] = None,
        description: str = "",
    ) -> "Image":
        """Create an image artifact from a file path.

        Args:
            interaction: The interaction this artifact belongs to
            filepath: Path to the image file
            storage: Storage instance to save the file to
            name: Optional name (defaults to filename)
            description: Optional description

        Returns:
            Image artifact
        """
        # Determine content type from extension
        ext = filepath.rsplit(".", 1)[-1].lower() if "." in filepath else "png"
        content_type_map = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
            "svg": "image/svg+xml",
        }
        content_type = content_type_map.get(ext, "image/png")

        # Read the file
        with open(filepath, "rb") as f:
            image_bytes = f.read()

        # Create the artifact
        image = cls(
            interaction=interaction,
            name=name or os.path.basename(filepath),
            content_type=content_type,
            description=description,
            _storage=storage,
        )

        # Save to storage and set path
        storage_path = storage.save_file(image.uuid, image_bytes, ext)
        image.path = storage_path

        return image
