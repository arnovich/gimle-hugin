"""Config state machine module.

Provides data structures for defining agent configuration transitions
based on rules and events during agent execution.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


@dataclass
class TransitionTrigger:
    """Defines when a configuration transition should occur.

    Attributes:
        type: The type of trigger condition.
            - "tool_call": Triggered when a specific tool is called.
            - "step_count": Triggered after a minimum number of steps.
            - "state_pattern": Triggered when shared state matches a pattern.
        tool_name: For "tool_call" triggers, the name of the tool.
        min_steps: For "step_count" triggers, the minimum step count.
        pattern: For "state_pattern" triggers, a dict pattern to match.
    """

    type: Literal["tool_call", "step_count", "state_pattern"]
    tool_name: Optional[str] = None
    min_steps: Optional[int] = None
    pattern: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the trigger to a dictionary.

        Returns:
            The dictionary representation of the trigger.
        """
        return {
            "type": self.type,
            "tool_name": self.tool_name,
            "min_steps": self.min_steps,
            "pattern": self.pattern,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TransitionTrigger":
        """Deserialize the trigger from a dictionary.

        Args:
            data: The dictionary to deserialize the trigger from.

        Returns:
            The deserialized trigger.
        """
        return cls(
            type=data["type"],
            tool_name=data.get("tool_name"),
            min_steps=data.get("min_steps"),
            pattern=data.get("pattern"),
        )


@dataclass
class ConfigTransition:
    """Defines a state transition for agent configuration.

    Attributes:
        name: Descriptive name for this transition.
        from_state: Config name to transition from, or "*" for any.
        to_state: Target config name to transition to.
        trigger: The condition that triggers this transition.
        priority: Higher priority transitions are checked first (default 0).
    """

    name: str
    from_state: str
    to_state: str
    trigger: TransitionTrigger
    priority: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the transition to a dictionary.

        Returns:
            The dictionary representation of the transition.
        """
        return {
            "name": self.name,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "trigger": self.trigger.to_dict(),
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfigTransition":
        """Deserialize the transition from a dictionary.

        Args:
            data: The dictionary to deserialize the transition from.

        Returns:
            The deserialized transition.
        """
        return cls(
            name=data["name"],
            from_state=data["from_state"],
            to_state=data["to_state"],
            trigger=TransitionTrigger.from_dict(data["trigger"]),
            priority=data.get("priority", 0),
        )


@dataclass
class ConfigStateMachine:
    """State machine for agent configuration transitions.

    Allows an agent to change its configuration (tools, system prompt,
    LLM model) dynamically based on rules during execution.

    Attributes:
        initial_state: The config name to start with.
        transitions: List of possible transitions.
        on_no_match: Behavior when no transition matches ("stay" or "error").
    """

    initial_state: str
    transitions: List[ConfigTransition] = field(default_factory=list)
    on_no_match: Literal["stay", "error"] = "stay"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the state machine to a dictionary.

        Returns:
            The dictionary representation of the state machine.
        """
        return {
            "initial_state": self.initial_state,
            "transitions": [t.to_dict() for t in self.transitions],
            "on_no_match": self.on_no_match,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfigStateMachine":
        """Deserialize the state machine from a dictionary.

        Args:
            data: The dictionary to deserialize the state machine from.

        Returns:
            The deserialized state machine.
        """
        transitions = [
            ConfigTransition.from_dict(t) for t in data.get("transitions", [])
        ]
        return cls(
            initial_state=data["initial_state"],
            transitions=transitions,
            on_no_match=data.get("on_no_match", "stay"),
        )

    def get_transitions_by_priority(self) -> List[ConfigTransition]:
        """Get transitions sorted by priority (highest first).

        Returns:
            The transitions sorted by priority (highest first).
        """
        return sorted(self.transitions, key=lambda t: t.priority, reverse=True)
