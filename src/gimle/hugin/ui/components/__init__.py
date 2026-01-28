"""UI Components for rendering artifacts in the agent monitor."""

from gimle.hugin.ui.components.base import ArtifactComponent, ComponentRegistry
from gimle.hugin.ui.components.code import CodeComponent
from gimle.hugin.ui.components.file import FileComponent
from gimle.hugin.ui.components.generic import GenericComponent
from gimle.hugin.ui.components.image import ImageComponent
from gimle.hugin.ui.components.text import TextComponent

__all__ = [
    "ArtifactComponent",
    "CodeComponent",
    "ComponentRegistry",
    "FileComponent",
    "GenericComponent",
    "ImageComponent",
    "TextComponent",
]
