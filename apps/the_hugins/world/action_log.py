"""Action logging system for tracking creature actions."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Action:
    """An action taken by a creature."""

    creature_name: str
    agent_id: str
    action_type: str  # "move", "take", "drop", "say", "talk_to", "look", etc.
    description: str
    timestamp: int  # World tick
    location: Optional[tuple] = None
    details: Dict = field(default_factory=dict)  # Additional action details
    reason: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize action to dictionary."""
        result = {
            "creature_name": self.creature_name,
            "agent_id": self.agent_id,
            "action_type": self.action_type,
            "description": self.description,
            "timestamp": self.timestamp,
            "location": list(self.location) if self.location else None,
            "details": self.details,
        }
        if self.reason:
            result["reason"] = self.reason
        return result


class ActionLog:
    """Log of actions taken by creatures."""

    def __init__(self, max_actions: int = 100):
        """Initialize action log.

        Args:
            max_actions: Maximum number of actions to keep in log
        """
        self.actions: List[Action] = []
        self.max_actions = max_actions

    def add_action(
        self,
        creature_name: str,
        agent_id: str,
        action_type: str,
        description: str,
        timestamp: int,
        location: Optional[tuple] = None,
        details: Optional[Dict] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Add an action to the log."""
        action = Action(
            creature_name=creature_name,
            agent_id=agent_id,
            action_type=action_type,
            description=description,
            timestamp=timestamp,
            location=location,
            details=details or {},
            reason=reason,
        )
        self.actions.append(action)

        # Keep only the most recent actions
        if len(self.actions) > self.max_actions:
            start_index = -self.max_actions
            self.actions = self.actions[start_index:]

    def get_recent_actions(self, count: int = 10) -> List[Action]:
        """Get the most recent actions."""
        return (
            self.actions[-count:] if len(self.actions) > count else self.actions
        )

    def get_actions_by_creature(
        self, creature_name: str, count: int = 10
    ) -> List[Action]:
        """Get recent actions by a specific creature."""
        creature_actions = [
            a for a in self.actions if a.creature_name == creature_name
        ]
        return (
            creature_actions[-count:]
            if len(creature_actions) > count
            else creature_actions
        )

    def get_actions_at_tick(self, tick: int) -> List[Action]:
        """Get all actions at a specific tick."""
        return [a for a in self.actions if a.timestamp == tick]

    def to_dict(self) -> dict:
        """Serialize action log to dictionary."""
        return {
            "actions": [action.to_dict() for action in self.actions],
            "total_actions": len(self.actions),
        }
