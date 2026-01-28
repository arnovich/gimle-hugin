"""Base classes for artifact renderers."""

from abc import ABC, abstractmethod
from typing import Callable, ClassVar, Dict, Type, TypeVar

from gimle.hugin.artifacts.artifact import Artifact

T = TypeVar("T", bound=Artifact)


class ArtifactRenderer(ABC):
    """Base class for artifact renderers."""

    _registry: ClassVar[Dict[str, Type["ArtifactRenderer"]]] = {}

    @abstractmethod
    def can_render(self, artifact: Artifact) -> bool:
        """
        Check if this renderer can handle the given artifact.

        Args:
            artifact: The artifact to check

        Returns:
            True if this renderer can render the artifact, False otherwise
        """
        pass

    @abstractmethod
    def render(self, artifact: Artifact, format: str = "html") -> str:
        """
        Render an artifact to the specified format.

        Args:
            artifact: The artifact to render
            format: The target format (e.g., "html", "text", etc.)

        Returns:
            The rendered artifact as a string

        Raises:
            ValueError: If the format is not supported
        """
        pass

    @classmethod
    def register(
        cls, artifact_type: str
    ) -> Callable[[Type["ArtifactRenderer"]], Type["ArtifactRenderer"]]:
        """
        Register an artifact renderer class.

        Args:
            artifact_type: The name of the artifact type this renderer handles

        Returns:
            A decorator function that registers the renderer class
        """

        def decorator(
            renderer_class: Type["ArtifactRenderer"],
        ) -> Type["ArtifactRenderer"]:
            cls._registry[artifact_type] = renderer_class
            return renderer_class

        return decorator

    @classmethod
    def get_renderer(cls, artifact: Artifact) -> "ArtifactRenderer":
        """
        Get the appropriate renderer for an artifact.

        Args:
            artifact: The artifact to get a renderer for

        Returns:
            An instance of the appropriate renderer

        Raises:
            ValueError: If no renderer is found for the artifact
        """
        artifact_type = artifact.__class__.__name__

        if artifact_type in cls._registry:
            renderer_class = cls._registry[artifact_type]
            renderer = renderer_class()
            if renderer.can_render(artifact):
                return renderer

        # Try to find a renderer by checking all registered renderers
        for renderer_class in cls._registry.values():
            renderer = renderer_class()
            if renderer.can_render(artifact):
                return renderer

        raise ValueError(
            f"No renderer found for artifact type: {artifact_type}"
        )
