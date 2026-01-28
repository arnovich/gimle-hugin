"""Battle arena state management for RapMachine."""

import json
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class BattleStatus(Enum):
    """Battle status enumeration."""

    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


class TurnType(Enum):
    """Turn type enumeration."""

    RAPPER_1 = "rapper_1"
    RAPPER_2 = "rapper_2"
    JUDGE = "judge"


@dataclass
class RapVerse:
    """A single rap verse in the battle."""

    rapper_name: str
    rapper_id: str
    verse: str
    timestamp: float
    turn_number: int


@dataclass
class BattleResult:
    """Result of a completed battle."""

    winner_id: str
    winner_name: str
    reasoning: str
    timestamp: float


@dataclass
class Battle:
    """A rap battle instance."""

    id: str
    topic: str
    status: BattleStatus
    current_turn: TurnType
    turn_number: int

    # Participants
    rapper_1_id: str
    rapper_1_name: str
    rapper_2_id: str
    rapper_2_name: str
    judge_id: str

    # Battle content
    verses: List[RapVerse]

    # Battle rules
    max_rounds: int = 10  # Maximum number of rounds before declaring winner

    # Models used
    rapper_1_model: str = "haiku-latest"
    rapper_2_model: str = "haiku-latest"
    judge_model: str = "haiku-latest"
    result: Optional[BattleResult] = None

    # Timestamps
    created_at: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0

    def __post_init__(self) -> None:
        """Initialize timestamps."""
        if self.created_at == 0.0:
            self.created_at = time.time()

    def start_battle(self) -> None:
        """Start the battle."""
        self.status = BattleStatus.IN_PROGRESS
        self.started_at = time.time()
        self.current_turn = TurnType.RAPPER_1
        self.turn_number = 1

    def add_verse(self, rapper_id: str, rapper_name: str, verse: str) -> None:
        """Add a verse to the battle."""
        rap_verse = RapVerse(
            rapper_name=rapper_name,
            rapper_id=rapper_id,
            verse=verse.strip(),
            timestamp=time.time(),
            turn_number=self.turn_number,
        )
        self.verses.append(rap_verse)

        # Switch turns
        if self.current_turn == TurnType.RAPPER_1:
            self.current_turn = TurnType.RAPPER_2
        else:
            self.current_turn = TurnType.RAPPER_1
            self.turn_number += 1

    def is_rapper_turn(self, rapper_id: str) -> bool:
        """Check if it's a specific rapper's turn."""
        if rapper_id == self.rapper_1_id:
            return self.current_turn == TurnType.RAPPER_1
        elif rapper_id == self.rapper_2_id:
            return self.current_turn == TurnType.RAPPER_2
        return False

    def can_judge_act(self) -> bool:
        """Check if judge can act (evaluate/end battle)."""
        return (
            self.status == BattleStatus.IN_PROGRESS
            and len(self.verses) >= 2  # At least one verse from each rapper
        )

    def finish_battle(
        self, winner_id: str, winner_name: str, reasoning: str
    ) -> None:
        """Finish the battle with a winner."""
        self.status = BattleStatus.FINISHED
        self.finished_at = time.time()
        self.result = BattleResult(
            winner_id=winner_id,
            winner_name=winner_name,
            reasoning=reasoning,
            timestamp=time.time(),
        )

    def get_battle_summary(self) -> Dict[str, Any]:
        """Get a summary of the battle state."""
        # Convert verses to serializable format for JavaScript
        recent_verses = []
        for verse in self.verses:
            recent_verses.append(
                {
                    "rapper": verse.rapper_name,
                    "rapper_id": verse.rapper_id,
                    "verse": verse.verse,
                    "turn": verse.turn_number,
                    "timestamp": verse.timestamp,
                }
            )

        # Check if we've reached max rounds
        reached_max_rounds = self.turn_number > self.max_rounds

        return {
            "id": self.id,
            "topic": self.topic,
            "status": self.status.value,
            "current_turn": (
                self.current_turn.value
                if self.status == BattleStatus.IN_PROGRESS
                else None
            ),
            "turn_number": self.turn_number,
            "max_rounds": self.max_rounds,
            "total_verses": len(self.verses),
            "reached_max_rounds": reached_max_rounds,
            "participants": {
                "rapper_1": {
                    "id": self.rapper_1_id,
                    "name": self.rapper_1_name,
                    "model": self.rapper_1_model,
                },
                "rapper_2": {
                    "id": self.rapper_2_id,
                    "name": self.rapper_2_name,
                    "model": self.rapper_2_model,
                },
                "judge": {
                    "id": self.judge_id,
                    "model": self.judge_model,
                },
            },
            "recent_verses": recent_verses,
            "latest_verse": asdict(self.verses[-1]) if self.verses else None,
            "result": asdict(self.result) if self.result else None,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert battle to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "topic": self.topic,
            "status": self.status.value,
            "current_turn": self.current_turn.value,
            "turn_number": self.turn_number,
            "max_rounds": self.max_rounds,
            "rapper_1_id": self.rapper_1_id,
            "rapper_1_name": self.rapper_1_name,
            "rapper_2_id": self.rapper_2_id,
            "rapper_2_name": self.rapper_2_name,
            "judge_id": self.judge_id,
            "rapper_1_model": self.rapper_1_model,
            "rapper_2_model": self.rapper_2_model,
            "judge_model": self.judge_model,
            "verses": [asdict(verse) for verse in self.verses],
            "result": asdict(self.result) if self.result else None,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Battle":
        """Create battle from dictionary."""
        verses = [
            RapVerse(**verse_data) for verse_data in data.get("verses", [])
        ]
        result = BattleResult(**data["result"]) if data.get("result") else None

        return cls(
            id=data["id"],
            topic=data["topic"],
            status=BattleStatus(data["status"]),
            current_turn=TurnType(data["current_turn"]),
            turn_number=data["turn_number"],
            rapper_1_id=data["rapper_1_id"],
            rapper_1_name=data["rapper_1_name"],
            rapper_2_id=data["rapper_2_id"],
            rapper_2_name=data["rapper_2_name"],
            judge_id=data["judge_id"],
            verses=verses,
            max_rounds=data.get("max_rounds", 10),
            rapper_1_model=data.get("rapper_1_model", "haiku-latest"),
            rapper_2_model=data.get("rapper_2_model", "haiku-latest"),
            judge_model=data.get("judge_model", "haiku-latest"),
            result=result,
            created_at=data.get("created_at", 0.0),
            started_at=data.get("started_at", 0.0),
            finished_at=data.get("finished_at", 0.0),
        )

    def save(self, filepath: str) -> None:
        """Save battle to JSON file."""
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> "Battle":
        """Load battle from JSON file."""
        with open(filepath, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)
