"""Structure effects for The Hugins world."""

from typing import Any, Dict

# Effects granted by each structure type.
# rest_bonus: extra energy gained when resting on this structure
# storage_capacity: max items the cell can hold (0 = no storage)
# look_radius: override look radius when standing on structure
STRUCTURE_EFFECTS: Dict[str, Dict[str, Any]] = {
    "shelter": {
        "rest_bonus": 10,
        "description": "Restores 15 energy when resting (base 5 + 10 bonus).",
    },
    "campfire": {
        "rest_bonus": 5,
        "lit_radius": 2,
        "description": "Restores 10 energy when resting. Lights nearby cells.",
    },
    "marker": {
        "look_radius": 2,
        "description": "Extends vision to 5x5 when standing on it.",
    },
    "storage": {
        "storage_capacity": 10,
        "description": "Holds up to 10 items safely.",
    },
    "bridge": {
        "description": "Allows crossing over water.",
    },
}

STORAGE_CAPACITY = 10
