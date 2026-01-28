"""Utilities for battle tools."""

from typing import Optional

from arena.battle import Battle

from gimle.hugin.interaction.stack import Stack


def get_battle(stack: Stack, battle_id: str) -> Optional[Battle]:
    """Get battle from state and ensure it's a Battle object.

    Handles both Battle objects and dicts (from deserialization).
    Automatically converts dicts to Battle objects and updates state.

    Args:
        stack: Agent stack
        battle_id: ID of the battle to retrieve

    Returns:
        Battle object or None if not found
    """
    battle = stack.get_shared_state(battle_id, namespace="battles")
    if battle is None:
        return None

    # If it's a dict (from deserialization), convert to Battle
    if isinstance(battle, dict):
        battle = Battle.from_dict(battle)
        # Update state with the Battle object for next time
        stack.set_shared_state(battle_id, battle, namespace="battles")

    if not isinstance(battle, Battle):
        raise ValueError(f"Battle {battle_id} is not a Battle object")

    return battle
