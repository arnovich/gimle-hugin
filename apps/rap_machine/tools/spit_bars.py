"""Tool for rappers to drop bars in the battle."""

from typing import Optional

from battle_utils import get_battle

from gimle.hugin.interaction.stack import Stack
from gimle.hugin.tools.tool import ToolResponse


def spit_bars(
    battle_id: str, verse: str, stack: Stack, branch: Optional[str] = None
) -> ToolResponse:
    """
    Drop rap bars in the battle.

    Args:
        battle_id: ID of the battle
        verse: The rap verse to perform
        stack: Agent stack (auto-injected)

    Returns:
        Dict with battle state and response
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

    # If rapper IDs aren't set yet in battle, update them
    # This happens on first call when rappers are created dynamically via AgentCall
    if not battle.rapper_1_id and not battle.rapper_2_id:
        # First rapper to arrive - assume it's rapper 1 based on turn
        if battle.current_turn.value == "rapper_1":
            battle.rapper_1_id = agent_id
        else:
            battle.rapper_2_id = agent_id
    elif not battle.rapper_1_id:
        # Rapper 2 exists, this must be rapper 1
        battle.rapper_1_id = agent_id
    elif not battle.rapper_2_id:
        # Rapper 1 exists, this must be rapper 2
        battle.rapper_2_id = agent_id

    # Check if it's this rapper's turn
    if not battle.is_rapper_turn(agent_id):
        current_turn = battle.current_turn.value
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Not your turn! Current turn: {current_turn}",
                "status": "waiting",
                "battle_state": battle.get_battle_summary(),
            },
        )

    # Start battle if not started yet
    if battle.status.value == "waiting":
        battle.start_battle()

    # Determine rapper name
    if agent_id == battle.rapper_1_id:
        rapper_name = battle.rapper_1_name
    elif agent_id == battle.rapper_2_id:
        rapper_name = battle.rapper_2_name
    else:
        return ToolResponse(
            is_error=True,
            content={
                "error": "You are not a participant in this battle",
                "status": "error",
            },
        )

    # Add the verse
    battle.add_verse(agent_id, rapper_name, verse)

    # Persist updated battle state
    stack.set_shared_state(battle_id, battle, namespace="battles")

    # Return success response
    return ToolResponse(
        is_error=False,
        content={
            "success": True,
            "message": f"🔥 {rapper_name} spits fire bars! 🔥",
            "verse": verse,
            "turn_number": battle.turn_number - 1,  # Previous turn number
            "status": "verse_delivered",
            "battle_state": battle.get_battle_summary(),
        },
    )

    # return TaskResult(
    #     stack=stack,
    #     branch=branch,
    #     finish_type="success",
    #     summary=f"{rapper_name} delivered their verse",
    #     result={
    #         "success": True,
    #         "message": f"🔥 {rapper_name} spits fire bars! 🔥",
    #         "verse": verse,
    #         "turn_number": battle.turn_number - 1,  # Previous turn number
    #         "status": "verse_delivered",
    #         "rapper_name": rapper_name,
    #     },
    # )
