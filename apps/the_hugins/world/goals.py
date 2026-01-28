"""Goal system for creatures."""

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class GoalType(str, Enum):
    """Types of goals creatures can have."""

    EXPLORE = "explore"  # Explore new areas
    COLLECT = "collect"  # Collect specific items
    MEET = "meet"  # Meet other creatures
    AVOID = "avoid"  # Avoid certain things
    REACH = "reach"  # Reach a specific location
    CUSTOM = "custom"  # Custom goal


@dataclass
class Goal:
    """A goal for a creature."""

    type: GoalType
    description: str
    priority: int = 5  # 1-10, higher is more important
    target: Optional[str] = None  # Target item, creature, or location
    target_position: Optional[Tuple[int, int]] = None
    completed: bool = False
    progress: float = 0.0  # 0.0 to 1.0

    def to_dict(self) -> dict:
        """Serialize goal to dictionary."""
        return {
            "type": self.type.value,
            "description": self.description,
            "priority": self.priority,
            "target": self.target,
            "target_position": (
                list(self.target_position) if self.target_position else None
            ),
            "completed": self.completed,
            "progress": self.progress,
        }


@dataclass
class Memory:
    """A memory of an event or interaction."""

    event_type: str  # "met_creature", "found_item", "visited_location", etc.
    description: str
    location: Optional[Tuple[int, int]] = None
    related_creature: Optional[str] = None
    related_item: Optional[str] = None
    timestamp: int = 0  # World tick when this happened
    importance: int = 5  # 1-10, how important this memory is

    def to_dict(self) -> dict:
        """Serialize memory to dictionary."""
        return {
            "event_type": self.event_type,
            "description": self.description,
            "location": list(self.location) if self.location else None,
            "related_creature": self.related_creature,
            "related_item": self.related_item,
            "timestamp": self.timestamp,
            "importance": self.importance,
        }


@dataclass
class Relationship:
    """Relationship between creatures."""

    other_creature_name: str
    relationship_type: str  # "friend", "rival", "neutral", "unknown"
    interactions: int = 0
    last_interaction_tick: int = 0
    sentiment: int = 5  # 1-10, 1 = very negative, 10 = very positive

    def to_dict(self) -> dict:
        """Serialize relationship to dictionary."""
        return {
            "other_creature_name": self.other_creature_name,
            "relationship_type": self.relationship_type,
            "interactions": self.interactions,
            "last_interaction_tick": self.last_interaction_tick,
            "sentiment": self.sentiment,
        }


class PlanStatus(str, Enum):
    """Status of a plan."""

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class StepStatus(str, Enum):
    """Status of a plan step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """A step in a multi-step plan."""

    id: str
    description: str
    required_tools: List[str] = field(default_factory=list)
    success_condition: Optional[str] = None
    status: StepStatus = StepStatus.PENDING
    notes: str = ""
    order: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize step to dictionary."""
        return {
            "id": self.id,
            "description": self.description,
            "required_tools": self.required_tools,
            "success_condition": self.success_condition,
            "status": self.status.value,
            "notes": self.notes,
            "order": self.order,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanStep":
        """Deserialize step from dictionary."""
        return cls(
            id=data["id"],
            description=data["description"],
            required_tools=data.get("required_tools", []),
            success_condition=data.get("success_condition"),
            status=StepStatus(data.get("status", "pending")),
            notes=data.get("notes", ""),
            order=data.get("order", 0),
        )


@dataclass
class Plan:
    """A multi-step plan for a creature."""

    id: str
    name: str
    description: str
    steps: List[PlanStep] = field(default_factory=list)
    current_step_index: int = 0
    status: PlanStatus = PlanStatus.ACTIVE
    created_tick: int = 0
    priority: int = 5  # 1-10, higher is more important
    related_goal: Optional[str] = None  # Link to a Goal if applicable

    def __post_init__(self) -> None:
        """Generate ID if not provided."""
        if not self.id:
            self.id = str(uuid.uuid4())[:8]

    def get_current_step(self) -> Optional[PlanStep]:
        """Get the current step to work on."""
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def advance_step(self) -> bool:
        """Mark current step as completed and advance to next."""
        current = self.get_current_step()
        if current:
            current.status = StepStatus.COMPLETED
            self.current_step_index += 1

            if self.current_step_index >= len(self.steps):
                self.status = PlanStatus.COMPLETED
                return False  # No more steps
            else:
                next_step = self.get_current_step()
                if next_step:
                    next_step.status = StepStatus.IN_PROGRESS
                return True
        return False

    def fail_current_step(self, notes: str = "") -> None:
        """Mark current step as failed."""
        current = self.get_current_step()
        if current:
            current.status = StepStatus.FAILED
            current.notes = notes
            self.status = PlanStatus.FAILED

    def get_progress(self) -> float:
        """Get plan progress as a percentage (0.0 to 1.0)."""
        if not self.steps:
            return 0.0
        completed = sum(
            1 for s in self.steps if s.status == StepStatus.COMPLETED
        )
        return completed / len(self.steps)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize plan to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
            "status": self.status.value,
            "created_tick": self.created_tick,
            "priority": self.priority,
            "related_goal": self.related_goal,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Plan":
        """Deserialize plan from dictionary."""
        steps = [PlanStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            steps=steps,
            current_step_index=data.get("current_step_index", 0),
            status=PlanStatus(data.get("status", "active")),
            created_tick=data.get("created_tick", 0),
            priority=data.get("priority", 5),
            related_goal=data.get("related_goal"),
        )
