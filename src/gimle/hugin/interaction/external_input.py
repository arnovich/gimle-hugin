"""Durable external input records awaiting a model turn."""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.utils.uuid import with_uuid

DEFAULT_CONTEXT_WINDOW = 5


@Interaction.register()
@dataclass
@with_uuid
class ExternalInput(Interaction):
    """An external input interaction.

    Attributes:
        input: The input from the external source to the agent.
        source: Caller-supplied provenance label, not verified identity.
        context_window: Positive model-turn window including delivery.
    """

    input: Optional[str] = None
    source: str = "external"
    context_window: int = DEFAULT_CONTEXT_WINDOW

    def to_message(self) -> Dict[str, Any]:
        """Capture a durable message without its stack reference."""
        return {
            "id": self.id,
            "input": self.input,
            "source": self.source,
            "context_window": self.context_window,
        }

    def step(self) -> bool:
        """Step the external input interaction.

        Returns:
            True if the external input interaction was successful, False otherwise.
        """
        self.stack.add_interaction(
            AskOracle.create_from_external_input(external_input=self)
        )
        return True
