"""Gimle Human Response Interaction."""

from dataclasses import dataclass
from typing import Optional

from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.utils.uuid import with_uuid


@Interaction.register()
@dataclass
@with_uuid
class HumanResponse(Interaction):
    """A human response interaction.

    Attributes:
        response: The response from the human.
    """

    response: Optional[str] = None

    def step(self) -> bool:
        """Step the human response interaction.

        Returns:
            True if the human response interaction was successful, False otherwise.
        """
        self.stack.add_interaction(
            AskOracle.create_from_human_response(human_response=self)
        )
        return True
