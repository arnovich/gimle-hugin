"""Tool for judge to declare the winner of the battle."""

from typing import Optional

from battle_utils import get_battle

from gimle.hugin.interaction.stack import Stack
from gimle.hugin.tools.tool import ToolResponse


def declare_winner(
    battle_id: str,
    winner: str,
    reasoning: str,
    stack: Stack,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Declare the winner of the rap battle.

    Args:
        battle_id: ID of the battle
        winner: Name of the winning rapper
        reasoning: Detailed reasoning for the decision
        stack: Agent stack (auto-injected)

    Returns:
        Dict with final battle results
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
                "error": "Only the judge can declare the winner",
                "status": "error",
            },
        )

    # Check if battle is ready to be finished
    if battle.status.value == "finished":
        return ToolResponse(
            is_error=True,
            content={
                "error": "Battle already finished",
                "status": "already_finished",
                "result": battle.result,
            },
        )

    # Determine winner ID
    winner_id = None
    winner_name = winner.strip()

    if winner_name.lower() == battle.rapper_1_name.lower():
        winner_id = battle.rapper_1_id
        winner_name = battle.rapper_1_name
    elif winner_name.lower() == battle.rapper_2_name.lower():
        winner_id = battle.rapper_2_id
        winner_name = battle.rapper_2_name
    else:
        # Try to match partial names
        if winner_name.lower() in battle.rapper_1_name.lower():
            winner_id = battle.rapper_1_id
            winner_name = battle.rapper_1_name
        elif winner_name.lower() in battle.rapper_2_name.lower():
            winner_id = battle.rapper_2_id
            winner_name = battle.rapper_2_name
        else:
            return ToolResponse(
                is_error=True,
                content={
                    "error": (
                        f"Winner '{winner}' not found. "
                        f"Choose between '{battle.rapper_1_name}' "
                        f"or '{battle.rapper_2_name}'"
                    ),
                    "status": "error",
                },
            )

    # Finish the battle
    battle.finish_battle(winner_id, winner_name, reasoning)

    # Persist updated battle state
    stack.set_shared_state(battle_id, battle, namespace="battles")

    return ToolResponse(
        is_error=False,
        content={
            "status": "battle_finished",
            "message": f"🏆 {winner_name} WINS! 🏆",
            "winner": {"id": winner_id, "name": winner_name},
            "reasoning": reasoning,
            "battle_state": battle.get_battle_summary(),
            "final_message": (
                f"🎤 Ladies and gentlemen, {winner_name} is your "
                f"RAP BATTLE CHAMPION! 🎤"
            ),
        },
    )
