"""Gimle Artifacts."""

from dataclasses import asdict, dataclass, fields
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Dict, Optional, Type

from gimle.hugin.utils.uuid import with_uuid

if TYPE_CHECKING:
    from gimle.hugin.interaction.interaction import Interaction
    from gimle.hugin.interaction.stack import Stack
    from gimle.hugin.storage.storage import Storage


@with_uuid
@dataclass
class Artifact:
    """An artifact is a collection of interactions.

    Attributes:
        _registry: The registry of artifacts.
        interaction: The interaction that produced the artifact.
    """

    _registry: ClassVar[Dict[str, Type["Artifact"]]] = {}
    interaction: Optional["Interaction"]
    # metadata: Dict[str, Any]
    # feedback: Optional[str] = None # for evaluating artifacts, should be separate object linked to artifact id

    @property
    def id(self) -> str:
        """Get the uuid of the artifact.

        Returns:
            The uuid of the artifact.
        """
        if not hasattr(self, "uuid"):
            raise ValueError("Artifact uuid not set")
        return str(self.uuid)

    @id.setter
    def id(self, id: str) -> None:
        """Set the uuid of the artifact.

        Args:
            id: The uuid to set.
        """
        self.uuid = id

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the artifact to a dictionary.

        Returns:
            A dictionary representation of the artifact.
        """
        # Manually construct dict excluding interaction to avoid recursion
        data: Dict[str, Any] = {}
        for f in fields(self):
            if f.name == "interaction":
                continue
            value = getattr(self, f.name)
            # Use asdict for nested dataclasses, but handle them carefully
            if hasattr(value, "__dataclass_fields__"):
                data[f.name] = asdict(value)
            else:
                data[f.name] = value
        # Handle interaction separately (store only UUID)
        if not hasattr(self.interaction, "uuid"):
            raise ValueError("Interaction must have a uuid")
        if self.interaction is not None:
            data["interaction"] = self.interaction.uuid
        if not hasattr(self, "uuid"):
            raise ValueError("Artifact must have a uuid")
        data["uuid"] = self.uuid
        # Add created_at if present (added by @with_uuid, not a dataclass field)
        if hasattr(self, "created_at"):
            data["created_at"] = getattr(self, "created_at")
        return {"type": self.__class__.__name__, "data": data}

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        storage: "Storage",
        stack: Optional["Stack"] = None,
        load_interaction: bool = True,
    ) -> "Artifact":
        """Deserialize the artifact from a dictionary.

        Args:
            data: Dictionary containing serialized artifact data
            storage: Storage instance to load interaction from
            stack: Optional stack for loading interaction
            load_interaction: Whether to load the interaction from storage.
                Set to False when called from Interaction.from_dict to avoid
                circular references (the caller will set artifact.interaction).
        """
        artifact_type = data.get("type")
        artifact_data = data.get("data", data).copy()

        # Load interaction from storage using its UUID
        interaction_uuid = artifact_data.pop("interaction", None)
        interaction: Optional["Interaction"] = None
        if interaction_uuid and load_interaction:
            if stack is not None:
                loaded = storage.load_interaction(interaction_uuid, stack)
                if loaded is None:
                    raise ValueError(
                        f"Interaction {interaction_uuid} not found in storage"
                    )
                interaction = loaded

        # Extract uuid and created_at if present (they're not dataclass fields)
        uuid_value = artifact_data.pop("uuid", None)
        created_at_value = artifact_data.pop("created_at", None)

        # Add uuid and created_at to kwargs to avoid generating new ones
        if uuid_value is not None:
            artifact_data["uuid"] = uuid_value
        if created_at_value is not None:
            artifact_data["created_at"] = created_at_value

        # Add loaded interaction
        if interaction is not None:
            artifact_data["interaction"] = interaction

        if artifact_type and artifact_type in cls._registry:
            artifact_class = cls._registry[artifact_type]
            instance = artifact_class(**artifact_data)
        else:
            # Default to base Artifact class
            instance = cls(**artifact_data)

        # Inject storage reference for file-based artifacts
        if hasattr(instance, "_storage"):
            instance._storage = storage

        return instance

    @classmethod
    def register(
        cls, name: str
    ) -> Callable[[Type["Artifact"]], Type["Artifact"]]:
        """Register an artifact class with a string name.

        Args:
            name: The name of the artifact to register.

        Returns:
            The registered artifact class.
        """

        def decorator(model_class: Type["Artifact"]) -> Type["Artifact"]:
            cls._registry[name] = model_class
            return model_class

        return decorator

    @classmethod
    def get_type(cls, name: str) -> Type["Artifact"]:
        """Get an artifact class by name from the registry.

        Args:
            name: The name of the artifact to get.

        Returns:
            The artifact class.
        """
        if name not in cls._registry:
            raise ValueError(f"Artifact {name} not found")
        return cls._registry[name]
