"""Registry class for maintaining a registry of instances."""

import logging
from typing import Dict, Generic, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Registry(Generic[T]):
    """A registry that maintains a dictionary of instances by name."""

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._items: Dict[str, T] = {}

    def register(
        self,
        instance: T,
        name: Optional[str] = None,
        replace: bool = True,
    ) -> T:
        """Register an instance in the registry.

        Args:
            instance: The instance to register.
            name: Registry key; defaults to ``instance.name``.
            replace: When False, refuse to shadow an existing entry.

        Raises:
            ValueError: If ``replace`` is False and ``name`` is already taken.

        This used to be a bare ``self._items[name] = instance``, which silently
        shadowed whatever was already registered. Because ``Tool.registry`` is
        a process-global shared by every loaded agent, a generated tool that
        happened to be called ``finish`` replaced the real one for the rest of
        the run, with nothing said. The default stays permissive so reloading
        an environment still works; callers that know a collision is a bug --
        anything loading generated code -- pass ``replace=False``.
        """
        # Get the name attribute - assumes all registered classes have a 'name' attribute
        if name is None:
            name = getattr(instance, "name")
        existing = self._items.get(name)
        if existing is not None and existing is not instance:
            if not replace:
                raise ValueError(
                    f"'{name}' is already registered; refusing to shadow it"
                )
            logger.debug("Replacing already-registered '%s'", name)
        self._items[name] = instance
        return instance

    def get(self, name: str) -> T:
        """Get an instance from the registry by name."""
        if name not in self._items:
            raise ValueError(f"Item {name} not found in registry")
        return self._items[name]

    def unregister(self, name: str, instance: Optional[T] = None) -> bool:
        """Remove ``name`` when it still refers to ``instance``.

        The optional identity check lets scoped loaders clean up objects they
        own without deleting a replacement registered by another caller.
        """
        current = self._items.get(name)
        if current is None or (
            instance is not None and current is not instance
        ):
            return False
        del self._items[name]
        return True

    def registered(self) -> Dict[str, T]:
        """Get all registered instances."""
        return self._items.copy()

    def clear(self) -> None:
        """Clear all registered instances."""
        self._items.clear()

    def remove(self, name: str) -> None:
        """Remove an instance from the registry by name."""
        if name not in self._items:
            raise ValueError(f"Item {name} not found in registry")
        del self._items[name]
