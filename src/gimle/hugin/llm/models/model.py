"""The base interface of an LLM model."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from gimle.hugin.tools.tool import Tool

logger = logging.getLogger(__name__)


@dataclass
class ModelResponse:
    """A model response."""

    role: Literal["user", "assistant", "system"]
    content: Any
    tool_call: Optional[str] = None
    tool_call_id: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    extra_content: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the model response to a dictionary."""
        return {
            "role": self.role,
            "content": self.content,
            "tool_call": self.tool_call,
            "tool_call_id": self.tool_call_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "extra_content": self.extra_content,
        }


class Model:
    """The base interface of an LLM model."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize a model."""
        self.config = config

    @staticmethod
    def log_messages(messages: List[Dict[str, Any]]) -> None:
        """Log messages for debugging."""
        for i, message in enumerate(messages):
            logger.debug(f"{message["role"].upper()} message {i}")
            logger.debug(f"{message['content']}")

    def chat_completion(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Tool]] = None,
    ) -> ModelResponse:
        """Generate a chat completion."""
        raise NotImplementedError("chat_completion not implemented")

    @property
    def model_name(self) -> str:
        """Get the model name."""
        if "model" not in self.config:
            raise ValueError("model_name not set")
        return str(self.config["model"])

    @property
    def temperature(self) -> Optional[float]:
        """Get the temperature. Returns None if not set."""
        temp = self.config.get("temperature")
        if temp is None:
            return None
        return float(temp)

    @property
    def max_tokens(self) -> int:
        """Get the maximum number of tokens."""
        if "max_tokens" not in self.config:
            raise ValueError("max_tokens not set")
        return int(self.config["max_tokens"])

    @property
    def tool_choice(self) -> Any:
        """Get the tool choice."""
        if "tool_choice" not in self.config:
            raise ValueError("tool_choice not set")
        return self.config["tool_choice"]
