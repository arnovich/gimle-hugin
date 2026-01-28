"""Gimle Human Response Interaction."""

from dataclasses import dataclass
from typing import Optional

from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.utils.uuid import with_uuid


@Interaction.register()
@dataclass
@with_uuid
class ExternalInput(Interaction):
    """An external input interaction.

    Attributes:
        input: The input from the external source to the agent.
    """

    input: Optional[str] = None

    def step(self) -> bool:
        """Step the external input interaction.

        Returns:
            True if the external input interaction was successful, False otherwise.
        """
        self.stack.add_interaction(
            AskOracle.create_from_external_input(external_input=self)
        )
        return True
