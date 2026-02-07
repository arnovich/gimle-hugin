"""Weather system for The Hugins world."""

import random
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class WeatherType(Enum):
    """Types of weather conditions."""

    CLEAR = "clear"
    RAIN = "rain"
    FOG = "fog"
    WIND = "wind"
    SNOW = "snow"


# Energy cost multipliers per weather type
WEATHER_ENERGY_MODIFIER: Dict[str, float] = {
    "clear": 1.0,
    "rain": 1.5,
    "fog": 1.0,
    "wind": 1.3,
    "snow": 2.0,
}

# Visibility (look radius) modifier per weather type
WEATHER_VISIBILITY_MODIFIER: Dict[str, int] = {
    "clear": 0,
    "rain": 0,
    "fog": -1,
    "wind": 0,
    "snow": 0,
}


@dataclass
class WeatherSystem:
    """Manages weather transitions in the world."""

    current: WeatherType = WeatherType.CLEAR
    next_change_tick: int = 0

    def tick(self, current_tick: int) -> None:
        """Advance weather, possibly transitioning."""
        if current_tick >= self.next_change_tick:
            self._transition()
            duration = random.randint(20, 40)
            self.next_change_tick = current_tick + duration

    def _transition(self) -> None:
        """Pick a new weather type with weighted randomness."""
        weights = {
            WeatherType.CLEAR: 40,
            WeatherType.RAIN: 20,
            WeatherType.FOG: 15,
            WeatherType.WIND: 15,
            WeatherType.SNOW: 10,
        }
        types = list(weights.keys())
        w = list(weights.values())
        self.current = random.choices(types, weights=w, k=1)[0]

    def get_energy_modifier(self) -> float:
        """Get movement energy cost multiplier."""
        return WEATHER_ENERGY_MODIFIER.get(
            self.current.value, 1.0
        )

    def get_visibility_modifier(self) -> int:
        """Get look radius modifier (negative reduces radius)."""
        return WEATHER_VISIBILITY_MODIFIER.get(
            self.current.value, 0
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize weather state."""
        return {
            "current": self.current.value,
            "next_change_tick": self.next_change_tick,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WeatherSystem":
        """Deserialize weather state."""
        return cls(
            current=WeatherType(data.get("current", "clear")),
            next_change_tick=data.get("next_change_tick", 0),
        )
