"""Template module."""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class Template:
    """A template definition."""

    name: str
    template: str
    description: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Template":
        """Deserialize the template from a dictionary."""
        return cls(**data)
