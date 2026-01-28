"""Tool to get the current battle state."""

from typing import Optional

from battle_utils import get_battle

from gimle.hugin.interaction.stack import Stack
from gimle.hugin.tools.tool import ToolResponse


def get_battle_state(
    battle_id: str, stack: Stack, branch: Optional[str] = None
) -> ToolResponse:
    """
    Get the current state of the rap battle.

    Args:
        battle_id: ID of the battle
        stack: Agent stack (auto-injected)

    Returns:
        Dict with current battle state
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

    # Get battle summary
    battle_summary = battle.get_battle_summary()

    # Add context for this agent
    if agent_id == battle.rapper_1_id:
        battle_summary["your_role"] = "rapper_1"
        battle_summary["your_name"] = battle.rapper_1_name
        battle_summary["your_turn"] = battle.is_rapper_turn(agent_id)
        battle_summary["opponent"] = battle.rapper_2_name
    elif agent_id == battle.rapper_2_id:
        battle_summary["your_role"] = "rapper_2"
        battle_summary["your_name"] = battle.rapper_2_name
        battle_summary["your_turn"] = battle.is_rapper_turn(agent_id)
        battle_summary["opponent"] = battle.rapper_1_name
    elif agent_id == battle.judge_id:
        battle_summary["your_role"] = "judge"
        battle_summary["can_judge"] = battle.can_judge_act()

    # Include recent verses for context
    if battle.verses:
        battle_summary["recent_verses"] = []
        # Show last 4 verses
        for verse in battle.verses[-4:]:
            battle_summary["recent_verses"].append(
                {
                    "rapper": verse.rapper_name,
                    "verse": verse.verse,
                    "turn": verse.turn_number,
                }
            )

    return ToolResponse(
        is_error=False, content={"status": "success", "battle": battle_summary}
    )
