"""RapBattle artifact for storing battle results."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from gimle.hugin.artifacts.artifact import Artifact
from gimle.hugin.utils.uuid import with_uuid


@Artifact.register("RapBattle")
@with_uuid
@dataclass
class RapBattleArtifact(Artifact):
    """Artifact representing a completed rap battle.

    This artifact stores the complete state of a rap battle including
    participants, verses, and the final result.
    """

    # Battle metadata
    battle_id: str = ""
    topic: str = ""
    status: str = "finished"

    # Participants
    rapper_1_name: str = ""
    rapper_1_model: str = ""
    rapper_2_name: str = ""
    rapper_2_model: str = ""
    judge_model: str = ""

    # Battle content - list of verse dicts with rapper_name, verse, turn
    verses: List[Dict[str, Any]] = field(default_factory=list)

    # Result
    winner_name: Optional[str] = None
    winner_reasoning: Optional[str] = None

    @classmethod
    def from_battle(
        cls,
        interaction: Any,
        battle: Any,  # Battle object from arena/battle.py
    ) -> "RapBattleArtifact":
        """Create artifact from a Battle instance.

        Args:
            interaction: The interaction that created this artifact
            battle: A Battle instance from arena.battle

        Returns:
            RapBattleArtifact instance
        """
        verses = []
        for verse in battle.verses:
            verses.append(
                {
                    "rapper_name": verse.rapper_name,
                    "verse": verse.verse,
                    "turn": verse.turn_number,
                }
            )

        winner_name = None
        winner_reasoning = None
        if battle.result:
            winner_name = battle.result.winner_name
            winner_reasoning = battle.result.reasoning

        return cls(
            interaction=interaction,
            battle_id=battle.id,
            topic=battle.topic,
            status=battle.status.value,
            rapper_1_name=battle.rapper_1_name,
            rapper_1_model=battle.rapper_1_model,
            rapper_2_name=battle.rapper_2_name,
            rapper_2_model=battle.rapper_2_model,
            judge_model=battle.judge_model,
            verses=verses,
            winner_name=winner_name,
            winner_reasoning=winner_reasoning,
        )
