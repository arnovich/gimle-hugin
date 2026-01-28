"""Prompt module."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Literal, Optional


@dataclass
class Prompt:
    """A prompt definition."""

    type: Literal["tool_result", "text", "template"] = "text"
    tool_use_id: Optional[str] = None
    tool_name: Optional[str] = None
    text: Optional[str] = None
    template_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the prompt to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Prompt":
        """Deserialize the prompt from a dictionary."""
        return cls(**data)
