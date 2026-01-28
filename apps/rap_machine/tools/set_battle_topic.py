"""Tool for judge to set the battle topic."""

from typing import Optional

from battle_utils import get_battle

from gimle.hugin.interaction.stack import Stack
from gimle.hugin.tools.tool import ToolResponse


def set_battle_topic(
    battle_id: str, topic: str, stack: Stack, branch: Optional[str] = None
) -> ToolResponse:
    """
    Set the topic for the rap battle.

    This should be called by the judge at the start of the battle to decide
    what the rappers will be battling about.

    Args:
        battle_id: ID of the battle
        topic: The topic/theme for the battle (should be creative and interesting)
        stack: Agent stack (auto-injected)

    Returns:
        Confirmation message
    """
    # Get battle from session state
    battle = get_battle(stack, battle_id)
    if battle is None:
        raise ValueError(f"Battle {battle_id} not found")

    # Update the battle topic
    battle.topic = topic

    # Update in session state
    stack.set_shared_state(battle_id, battle, namespace="battles")

    return ToolResponse(
        is_error=False,
        content={
            "message": f"Battle topic set to: '{topic}'. The rappers will now battle about this theme!"
        },
    )
