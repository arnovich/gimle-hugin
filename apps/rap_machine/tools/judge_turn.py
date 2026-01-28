"""Tool for judge to evaluate and control the battle."""

from typing import Optional

from battle_utils import get_battle

from gimle.hugin.interaction.stack import Stack
from gimle.hugin.tools.tool import ToolResponse


def judge_turn(
    stack: Stack,
    battle_id: str,
    action: str,
    commentary: str = "",
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Judge the battle and decide whether to continue or end it.

    Args:
        battle_id: ID of the battle
        action: 'continue' or 'end'
        commentary: Judge's commentary on the battle
        stack: Agent stack (auto-injected)

    Returns:
        Dict with judge's decision and battle state
    """
    # Get battle from session state
    battle = get_battle(stack, battle_id)

    if battle is None:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Battle {battle_id} not found",
                "status": "error",
            },
        )

    agent_id = stack.agent.id

    # Verify this is the judge
    if agent_id != battle.judge_id:
        return ToolResponse(
            is_error=True,
            content={
                "error": "Only the judge can make battle decisions",
                "status": "error",
            },
        )

    # Check if judge can act
    if not battle.can_judge_act():
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    "Battle not ready for judging (need at least 2 verses)"
                ),
                "status": "waiting",
                "battle_state": battle.get_battle_summary(),
            },
        )

    if action.lower() == "end":
        # Signal that judge wants to end the battle
        # But don't actually end it yet - need declare_winner for that
        return ToolResponse(
            is_error=False,
            content={
                "status": "ready_to_judge",
                "message": ("🎤 JUDGE CALLS TIME! Ready to declare winner."),
                "commentary": commentary,
                "battle_state": battle.get_battle_summary(),
                "instruction": (
                    "Now use declare_winner to announce the champion!"
                ),
            },
        )
    elif action.lower() == "continue":
        return ToolResponse(
            is_error=False,
            content={
                "status": "battle_continues",
                "message": "⏰ Battle continues! Rappers keep spitting!",
                "commentary": commentary,
                "battle_state": battle.get_battle_summary(),
            },
        )
    else:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Invalid action '{action}'. Use 'continue' or 'end'",
                "status": "error",
            },
        )
