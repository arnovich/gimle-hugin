"""Gimle Interaction."""

from abc import abstractmethod
from dataclasses import asdict, dataclass, field, fields
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Optional,
    Type,
    TypeVar,
)

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.utils.uuid import with_uuid

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

T = TypeVar("T", bound="Interaction")


@dataclass
@with_uuid
class Interaction:
    """Base class for all interactions.

    Attributes:
        _registry: The registry of interactions.
        stack: The stack to use for the interaction.
        branch: The branch to use for the interaction.
        artifacts: The artifacts to use for the interaction.
    """

    _registry: ClassVar[Dict[str, Type["Interaction"]]] = (
        {}
    )  # Class variable, not a field

    stack: "Stack" = field(repr=False, compare=False)
    branch: Optional[str] = field(default=None, repr=False)
    artifacts: List[Artifact] = field(
        default_factory=list, repr=False, compare=False
    )

    @property
    def id(self) -> str:
        """Get the uuid of the interaction.

        Returns:
            The uuid of the interaction.
        """
        if not hasattr(self, "uuid"):
            raise ValueError("Interaction uuid not set")
        return str(self.uuid)

    @id.setter
    def id(self, id: str) -> None:
        """Set the uuid of the interaction.

        Args:
            id: The uuid to set.
        """
        self.uuid = id

    @abstractmethod
    def step(self) -> bool:
        """
        Execute the interaction logic.

        Args:
            stack: The stack to use for the interaction.
            branch: The branch to use for the interaction.

        Returns:
            True if the interaction was successful, False otherwise.
        """
        pass

    def add_artifact(self, artifact: Artifact) -> None:
        """Add an artifact to the interaction.

        Args:
            artifact: The artifact to add.
        """
        self.artifacts.append(artifact)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            The serialized interaction.
        """
        # Manually construct dict excluding stack and artifacts to avoid recursion
        data: Dict[str, Any] = {}
        for f in fields(self):
            if f.name in ("stack", "artifacts", "response_interaction"):
                continue
            value = getattr(self, f.name)
            # Use asdict for nested dataclasses, but handle them carefully
            if hasattr(value, "__dataclass_fields__"):
                data[f.name] = asdict(value)
            else:
                data[f.name] = value
        # Handle artifacts separately (store only IDs)
        if self.artifacts:
            data["artifacts"] = [artifact.id for artifact in self.artifacts]
        # Add uuid if present (added by @with_uuid, not a dataclass field)
        if hasattr(self, "uuid"):
            data["uuid"] = self.uuid
        # Add created_at if present (added by @with_uuid, not a dataclass field)
        if hasattr(self, "created_at"):
            data["created_at"] = getattr(self, "created_at")
        return {"type": self.__class__.__name__, "data": data}

    @classmethod
    def register(cls) -> Callable[[Type["Interaction"]], Type["Interaction"]]:
        """Register a interaction class with a string name.

        Args:
            model_class: The interaction class to register.

        Returns:
            The registered interaction class.
        """

        def decorator(model_class: Type["Interaction"]) -> Type["Interaction"]:
            cls._registry[model_class.__name__] = model_class
            return model_class

        return decorator

    @classmethod
    def get_interaction(cls, name: str) -> Type["Interaction"]:
        """Get a interaction class by name from the registry.

        Args:
            name: The name of the interaction to get.

        Returns:
            The interaction class.
        """
        if name not in cls._registry:
            available_interactions = list(cls._registry.keys())
            raise ValueError(
                f"Interaction '{name}' not found. "
                f"Available interactions: "
                f"{', '.join(available_interactions)}"
            )
        return cls._registry[name]

    @classmethod
    def _from_dict(
        cls: Type[T],
        data: Dict[str, Any],
        stack: "Stack",
        artifacts: List[Artifact],
    ) -> T:
        """Construct from dictionary.

        Args:
            data: The data to construct the interaction from.
            stack: The stack to use for the interaction.
            artifacts: The artifacts to use for the interaction.

        Returns:
            The constructed interaction.
        """
        # Extract uuid and created_at if present
        # (they're not dataclass fields, so pass them to __init__)
        uuid_value = data.pop("uuid", None)
        created_at_value = data.pop("created_at", None)

        # Create instance, passing uuid and created_at to avoid generating new ones
        kwargs = {"stack": stack, **data}
        if uuid_value is not None:
            kwargs["uuid"] = uuid_value
        if created_at_value is not None:
            kwargs["created_at"] = created_at_value

        instance = cls(**kwargs)
        instance.artifacts = artifacts

        return instance

    @classmethod
    def from_dict(cls, data: Dict[str, Any], stack: "Stack") -> "Interaction":
        """Deserialize any interaction type.

        Args:
            data: The data to deserialize the interaction from.
            stack: The stack to use for the interaction.

        Returns:
            The deserialized interaction.
        """
        if stack.agent.session.storage is None:
            raise ValueError("Stack agent session storage is None")
        interaction_type = data.get("type")
        interaction_data = data.get("data", data)
        artifacts_data = interaction_data.get("artifacts", [])
        artifacts = [
            stack.agent.session.storage.load_artifact(
                artifact_uuid, stack=stack, load_interaction=False
            )
            for artifact_uuid in artifacts_data
        ]
        if interaction_type not in cls._registry:
            raise ValueError(
                f"Unknown interaction type: {interaction_type}"
                f" available: {cls._registry.keys()}"
            )

        cls_type = cls._registry[interaction_type]
        interaction = cls_type._from_dict(
            data=interaction_data, stack=stack, artifacts=artifacts
        )
        for artifact in artifacts:
            artifact.interaction = interaction
        return interaction

    @classmethod
    def list_interactions(cls) -> list[str]:
        """List all registered interaction names.

        Returns:
            A list of all registered interaction names.
        """
        return list(cls._registry.keys())
