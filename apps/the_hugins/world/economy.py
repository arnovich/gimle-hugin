"""Economy system constants and data structures for The Hugins."""

import uuid
from dataclasses import dataclass
from typing import Any, Dict

# Energy constants
MAX_ENERGY = 100
STARTING_ENERGY = 100
STARTING_MONEY = 50

# Energy costs
ENERGY_COST_MOVE = 1
ENERGY_RECOVERY_REST = 5

# Food energy values - what creatures can eat to restore energy
FOOD_ENERGY: Dict[str, int] = {
    "apple": 20,
    "berry": 10,
    "mushroom": 8,
    "herb": 5,
    "herb_bundle": 25,
    "mushroom_stew": 40,
    "acorn": 3,
}

# Item base prices for trading
ITEM_PRICES: Dict[str, int] = {
    # Food items
    "apple": 15,
    "berry": 8,
    "mushroom": 6,
    "herb": 5,
    "herb_bundle": 20,
    "mushroom_stew": 35,
    "acorn": 4,
    # Basic materials
    "stone": 5,
    "stick": 3,
    "seed": 3,
    "leaf": 2,
    "feather": 4,
    "pebble": 2,
    "flower": 6,
    # Crafted items
    "tool": 25,
    "rope": 15,
    "basket": 20,
}

# Resource spawning configuration
SPAWN_INTERVAL_TICKS = 10  # Spawn resources every N ticks
SPAWN_COUNT = 3  # Number of items to spawn each interval

# Weighted spawn chances (more common items have higher weights)
SPAWN_WEIGHTS: Dict[str, int] = {
    "berry": 5,
    "apple": 3,
    "mushroom": 4,
    "stick": 4,
    "stone": 3,
    "seed": 3,
    "leaf": 4,
    "herb": 2,
    "feather": 2,
    "pebble": 3,
    "flower": 2,
    "acorn": 3,
}


@dataclass
class TradeOffer:
    """A trade offer between two creatures."""

    id: str  # Unique trade ID
    from_creature: str  # Name of the proposer
    action: str  # "buy" or "sell" (from proposer's perspective)
    item_name: str
    price: int
    created_tick: int

    def __post_init__(self) -> None:
        """Generate ID if not provided."""
        if not self.id:
            self.id = str(uuid.uuid4())[:8]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize trade offer to dictionary."""
        return {
            "id": self.id,
            "from_creature": self.from_creature,
            "action": self.action,
            "item_name": self.item_name,
            "price": self.price,
            "created_tick": self.created_tick,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradeOffer":
        """Deserialize trade offer from dictionary."""
        return cls(
            id=data["id"],
            from_creature=data["from_creature"],
            action=data["action"],
            item_name=data["item_name"],
            price=data["price"],
            created_tick=data["created_tick"],
        )
