"""UUID utilities module."""

import uuid
from dataclasses import _MISSING_TYPE, fields, is_dataclass
from datetime import datetime, timezone
from typing import Any, Type, TypeVar

T = TypeVar("T")


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


def with_uuid(cls: Type[T]) -> Type[T]:
    """Return a decorator to automatically set a `uuid` and `created_at` property on instances.

    If `uuid` is passed as a keyword argument to `__init__`, it will be extracted
    and set. Otherwise, a UUID will be generated automatically.

    If `created_at` is passed as a keyword argument to `__init__`, it will be extracted
    and set. Otherwise, a UTC timestamp will be generated automatically.

    Works with both regular classes and dataclasses.

    Usage:
        @with_uuid
        class MyClass:
            def __init__(self, name):
                self.name = name
                # uuid can be passed: MyClass("test", uuid="custom-uuid")
                # created_at can be passed: MyClass("test", created_at="2024-01-01T00:00:00Z")
                # Or both will be auto-generated if not provided
                # No need to handle uuid or created_at parameters in __init__

        # Works with or without uuid/created_at arguments:
        obj1 = MyClass("test")  # uuid and created_at auto-generated
        obj2 = MyClass("test", uuid="custom-uuid")  # uses provided uuid, generates created_at
        obj3 = MyClass("test", uuid="custom-uuid", created_at="2024-01-01T00:00:00Z")  # uses both
    """
    # Check if this is a dataclass (including after @dataclass decorator is applied)
    is_dataclass_cls = is_dataclass(cls)
    original_init = cls.__init__

    if is_dataclass_cls:
        # For dataclasses, we need to manually set all fields since the parent's
        # @with_uuid wrapper might interfere. We'll set fields directly from kwargs.
        # IMPORTANT: Get fields from the actual instance's class, not the decorator's class
        # This ensures we get all fields including those defined in subclasses

        def __init__(self: Any, *args: Any, **kwargs: Any) -> None:
            # Extract uuid and created_at from kwargs if provided
            provided_uuid = kwargs.pop("uuid", None)
            provided_created_at = kwargs.pop("created_at", None)

            # Get fields from the actual instance's class (self.__class__)
            # This is important for subclasses where fields() might not return all fields
            instance_fields = fields(self.__class__)

            # For dataclass subclasses, we need to manually set ALL fields
            # because the parent's @with_uuid wrapper might interfere with the dataclass __init__
            # IMPORTANT: Set fields directly into __dict__ to bypass any __setattr__ overrides
            # First, set all fields from kwargs
            for field in instance_fields:
                field_name = field.name
                if field_name in kwargs:
                    value = kwargs[field_name]
                    # Directly set in __dict__ to ensure it's set
                    self.__dict__[field_name] = value
                    # Also remove from kwargs so we don't process it again
                    del kwargs[field_name]

            # Set defaults for any fields that weren't provided
            for field in instance_fields:
                field_name = field.name
                if field_name not in self.__dict__:
                    # Field not set, set default
                    # Check for default_factory first (when present, default is _MISSING_TYPE)
                    # default_factory is callable when it's a factory, _MISSING_TYPE instance when it's not
                    if (
                        hasattr(field, "default_factory")
                        and field.default_factory is not _MISSING_TYPE
                        and callable(field.default_factory)
                    ):
                        self.__dict__[field_name] = field.default_factory()
                    elif field.default is not _MISSING_TYPE:
                        self.__dict__[field_name] = field.default

            # Set uuid: use provided one, or existing one, or generate new one
            if not hasattr(self, "uuid"):
                self.uuid = (
                    provided_uuid
                    if provided_uuid is not None
                    else generate_uuid()
                )

            # Set created_at: use provided one, or existing one, or generate new one
            if not hasattr(self, "created_at"):
                self.created_at = (
                    provided_created_at
                    if provided_created_at is not None
                    else datetime.now(timezone.utc).isoformat()
                )

            # Call __post_init__ if it exists (dataclass feature)
            if hasattr(self, "__post_init__"):
                self.__post_init__()

        cls.__init__ = __init__  # type: ignore
    else:
        # For regular classes, wrap the original __init__
        original_init = cls.__init__

        def __init__(self: Any, *args: Any, **kwargs: Any) -> None:
            # Extract uuid and created_at from kwargs if provided, but don't pass to original __init__
            provided_uuid = kwargs.pop("uuid", None)
            provided_created_at = kwargs.pop("created_at", None)

            # Call the original __init__ without uuid/created_at in kwargs
            original_init(self, *args, **kwargs)

            # Set uuid: use provided one, or existing one, or generate new one
            if not hasattr(self, "uuid"):
                self.uuid = (
                    provided_uuid
                    if provided_uuid is not None
                    else generate_uuid()
                )
            # If uuid was already set by the class, keep it (provided_uuid is ignored)

            # Set created_at: use provided one, or existing one, or generate new one
            if not hasattr(self, "created_at"):
                self.created_at = (
                    provided_created_at
                    if provided_created_at is not None
                    else datetime.now(timezone.utc).isoformat()
                )
            # If created_at was already set by the class, keep it (provided_created_at is ignored)

        cls.__init__ = __init__  # type: ignore

    return cls
