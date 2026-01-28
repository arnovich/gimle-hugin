"""Registry class for maintaining a registry of instances."""

from typing import Dict, Generic, Optional, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """A registry that maintains a dictionary of instances by name."""

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._items: Dict[str, T] = {}

    def register(self, instance: T, name: Optional[str] = None) -> T:
        """Register an instance in the registry."""
        # Get the name attribute - assumes all registered classes have a 'name' attribute
        if name is None:
            name = getattr(instance, "name")
        self._items[name] = instance
        return instance

    def get(self, name: str) -> T:
        """Get an instance from the registry by name."""
        if name not in self._items:
            raise ValueError(f"Item {name} not found in registry")
        return self._items[name]

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
