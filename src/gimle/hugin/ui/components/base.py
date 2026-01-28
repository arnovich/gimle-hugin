"""Base classes for artifact UI components."""

from abc import ABC, abstractmethod
from typing import Callable, ClassVar, Dict, List, Optional, Type

from gimle.hugin.artifacts.artifact import Artifact


class ArtifactComponent(ABC):
    """Base class for artifact UI components.

    UI components render artifacts as HTML for display in the agent monitor.
    External applications can register custom components for their artifact types.

    Example usage:
        @ComponentRegistry.register("MyArtifact")
        class MyArtifactComponent(ArtifactComponent):
            def render_preview(self, artifact: MyArtifact) -> str:
                return f"Preview: {artifact.name}"

            def render_detail(self, artifact: MyArtifact) -> str:
                return f"<div class='my-artifact'>{artifact.content}</div>"
    """

    @abstractmethod
    def render_preview(self, artifact: Artifact) -> str:
        """Render a compact preview of the artifact.

        This is shown in artifact lists and badges.

        Args:
            artifact: The artifact to render

        Returns:
            HTML string for the preview (should be short/compact)
        """
        pass

    @abstractmethod
    def render_detail(self, artifact: Artifact) -> str:
        """Render the full detail view of the artifact.

        This is shown when the artifact is clicked/expanded in the monitor.

        Args:
            artifact: The artifact to render

        Returns:
            HTML string for the detail view
        """
        pass

    def get_styles(self) -> str:
        """Return CSS styles for this component.

        Override this to provide custom CSS that will be injected into the page.

        Returns:
            CSS string (without <style> tags)
        """
        return ""

    def get_scripts(self) -> str:
        """Return JavaScript for this component.

        Override this to provide custom JS that will be injected into the page.

        Returns:
            JavaScript string (without <script> tags)
        """
        return ""


class ComponentRegistry:
    """Registry for artifact UI components.

    Components are registered by artifact type name and can be looked up
    when rendering artifacts in the agent monitor.
    """

    _registry: ClassVar[Dict[str, Type[ArtifactComponent]]] = {}
    _fallback: ClassVar[Optional[Type[ArtifactComponent]]] = None

    @classmethod
    def register(
        cls, artifact_type: str
    ) -> Callable[[Type[ArtifactComponent]], Type[ArtifactComponent]]:
        """Register a component for an artifact type.

        Args:
            artifact_type: The name of the artifact type (e.g., "Text", "File")

        Returns:
            Decorator function that registers the component class

        Example:
            @ComponentRegistry.register("Text")
            class TextComponent(ArtifactComponent):
                ...
        """

        def decorator(
            component_class: Type[ArtifactComponent],
        ) -> Type[ArtifactComponent]:
            cls._registry[artifact_type] = component_class
            return component_class

        return decorator

    @classmethod
    def set_fallback(
        cls, component_class: Type[ArtifactComponent]
    ) -> Type[ArtifactComponent]:
        """Set the fallback component for unknown artifact types.

        Args:
            component_class: The component class to use as fallback

        Returns:
            The component class (allows use as decorator)
        """
        cls._fallback = component_class
        return component_class

    @classmethod
    def get_component(cls, artifact: Artifact) -> ArtifactComponent:
        """Get the appropriate component for an artifact.

        Args:
            artifact: The artifact to get a component for

        Returns:
            An instance of the appropriate component

        Raises:
            ValueError: If no component is found and no fallback is set
        """
        artifact_type = artifact.__class__.__name__

        if artifact_type in cls._registry:
            return cls._registry[artifact_type]()

        if cls._fallback is not None:
            return cls._fallback()

        raise ValueError(
            f"No component registered for artifact type: {artifact_type}"
        )

    @classmethod
    def get_component_by_type(cls, artifact_type: str) -> ArtifactComponent:
        """Get a component by artifact type name.

        Args:
            artifact_type: The artifact type name

        Returns:
            An instance of the appropriate component

        Raises:
            ValueError: If no component is found and no fallback is set
        """
        if artifact_type in cls._registry:
            return cls._registry[artifact_type]()

        if cls._fallback is not None:
            return cls._fallback()

        raise ValueError(
            f"No component registered for artifact type: {artifact_type}"
        )

    @classmethod
    def list_registered_types(cls) -> List[str]:
        """List all registered artifact types.

        Returns:
            List of artifact type names that have registered components
        """
        return list(cls._registry.keys())

    @classmethod
    def get_all_styles(cls) -> str:
        """Collect CSS from all registered components.

        Returns:
            Combined CSS string from all components
        """
        styles = []
        seen_classes: set = set()

        for component_class in cls._registry.values():
            if component_class not in seen_classes:
                seen_classes.add(component_class)
                component = component_class()
                css = component.get_styles()
                if css:
                    styles.append(css)

        if cls._fallback and cls._fallback not in seen_classes:
            component = cls._fallback()
            css = component.get_styles()
            if css:
                styles.append(css)

        return "\n".join(styles)

    @classmethod
    def get_all_scripts(cls) -> str:
        """Collect JavaScript from all registered components.

        Returns:
            Combined JavaScript string from all components
        """
        scripts = []
        seen_classes: set = set()

        for component_class in cls._registry.values():
            if component_class not in seen_classes:
                seen_classes.add(component_class)
                component = component_class()
                js = component.get_scripts()
                if js:
                    scripts.append(js)

        if cls._fallback and cls._fallback not in seen_classes:
            component = cls._fallback()
            js = component.get_scripts()
            if js:
                scripts.append(js)

        return "\n".join(scripts)
