"""Cell model for the world grid."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from world.object import Object


class TerrainType(str, Enum):
    """Types of terrain in the world."""

    GRASS = "grass"
    WATER = "water"
    STONE = "stone"
    SAND = "sand"
    DIRT = "dirt"
    FOREST = "forest"
    # New terrain types for environment interaction
    HOLE = "hole"  # Dug hole
    TILLED = "tilled"  # Tilled soil ready for planting
    PLANTED = "planted"  # Has seeds planted


@dataclass
class Cell:
    """A single cell in the world grid."""

    terrain: TerrainType
    objects: List[Object] = field(default_factory=list)
    x: int = 0
    y: int = 0
    # Environment interaction fields
    planted_seed: Optional[str] = None  # Type of seed planted
    plant_growth_tick: int = 0  # World tick when plant will be ready
    structure: Optional[str] = None  # Built structure (shelter, marker, bridge)
    lit: bool = False  # Illuminated by a nearby campfire

    def add_object(self, obj: Object) -> None:
        """Add an object to this cell."""
        self.objects.append(obj)

    def remove_object(self, obj_name: str) -> Optional[Object]:
        """Remove an object by name from this cell."""
        for i, obj in enumerate(self.objects):
            if obj.name == obj_name:
                return self.objects.pop(i)
        return None

    def get_object(self, obj_name: str) -> Optional[Object]:
        """Get an object by name from this cell."""
        for obj in self.objects:
            if obj.name == obj_name:
                return obj
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize cell to dictionary."""
        data: Dict[str, Any] = {
            "terrain": self.terrain.value,
            "objects": [obj.to_dict() for obj in self.objects],
            "x": self.x,
            "y": self.y,
        }
        # Include optional fields if set
        if self.planted_seed:
            data["planted_seed"] = self.planted_seed
            data["plant_growth_tick"] = self.plant_growth_tick
        if self.structure:
            data["structure"] = self.structure
        if self.lit:
            data["lit"] = True
        return data
