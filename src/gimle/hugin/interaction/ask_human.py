"""Gimle Ask Human Interaction."""

from dataclasses import dataclass
from typing import Optional

from gimle.hugin.interaction.interaction import Interaction
from gimle.hugin.utils.uuid import with_uuid


@Interaction.register()
@dataclass
@with_uuid
class AskHuman(Interaction):
    """Ask a human a question.

    Attributes:
        question: The question to ask the human.
        response_template_name: The name of the template to use for the response.
    """

    question: Optional[str] = None
    response_template_name: Optional[str] = None

    def step(self) -> bool:
        """Step the ask human interaction.

        Returns:
            True if the ask human interaction was successful, False otherwise.
        """
        # here we wait for a response from the human
        # next step must be a HumanResponse
        # interaction on the stack
        return False
