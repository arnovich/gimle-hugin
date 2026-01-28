"""Object model for items and creatures in the world."""

from dataclasses import dataclass
from enum import Enum


class ObjectType(str, Enum):
    """Types of objects in the world."""

    ITEM = "item"  # Regular items that can be picked up
    CREATURE = "creature"  # Other creatures (agents)


@dataclass
class Object:
    """An object in the world (item or creature reference)."""

    name: str
    type: ObjectType
    description: str
    # For creatures, this is the agent_id
    # For items, this is a unique identifier
    id: str

    def to_dict(self) -> dict:
        """Serialize object to dictionary."""
        return {
            "name": self.name,
            "type": self.type.value,
            "description": self.description,
            "id": self.id,
        }
