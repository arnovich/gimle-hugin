"""Creature state tracking in the world."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from world.goals import Goal, Memory, Plan, PlanStatus, Relationship
from world.object import Object


@dataclass
class CreatureState:
    """State of a creature in the world."""

    agent_id: str
    position: Tuple[int, int]
    name: str
    description: str
    personality: str  # Personality traits that influence behavior
    inventory: List[Object] = field(
        default_factory=list
    )  # Items the creature is carrying
    goals: List[Goal] = field(default_factory=list)  # Current goals
    memories: List[Memory] = field(
        default_factory=list
    )  # Memories of past events
    relationships: Dict[str, Relationship] = field(
        default_factory=dict
    )  # Relationships with other creatures
    plans: List[Plan] = field(default_factory=list)  # Multi-step plans

    def add_to_inventory(self, obj: Object) -> None:
        """Add an object to the creature's inventory."""
        self.inventory.append(obj)

    def remove_from_inventory(self, obj_name: str) -> Optional[Object]:
        """Remove an object from inventory by name."""
        for i, obj in enumerate(self.inventory):
            if obj.name == obj_name:
                return self.inventory.pop(i)
        return None

    def get_inventory(self) -> List[Object]:
        """Get the creature's inventory."""
        return self.inventory.copy()

    def add_goal(self, goal: Goal) -> None:
        """Add a goal to the creature."""
        self.goals.append(goal)
        # Sort by priority
        self.goals.sort(key=lambda g: g.priority, reverse=True)

    def complete_goal(self, goal_index: int) -> None:
        """Mark a goal as completed."""
        if 0 <= goal_index < len(self.goals):
            self.goals[goal_index].completed = True
            self.goals[goal_index].progress = 1.0

    def add_memory(self, memory: Memory) -> None:
        """Add a memory to the creature."""
        self.memories.append(memory)
        # Keep only the most important memories (limit to 50)
        if len(self.memories) > 50:
            self.memories.sort(key=lambda m: m.importance, reverse=True)
            self.memories = self.memories[:50]

    def get_relationship(self, creature_name: str) -> Optional[Relationship]:
        """Get relationship with another creature."""
        return self.relationships.get(creature_name)

    def update_relationship(
        self,
        creature_name: str,
        relationship_type: str,
        sentiment_change: int = 0,
    ) -> None:
        """Update relationship with another creature."""
        if creature_name not in self.relationships:
            self.relationships[creature_name] = Relationship(
                other_creature_name=creature_name,
                relationship_type=relationship_type,
            )

        rel = self.relationships[creature_name]
        rel.interactions += 1
        rel.sentiment = max(1, min(10, rel.sentiment + sentiment_change))
        rel.relationship_type = relationship_type

    def add_plan(self, plan: Plan) -> None:
        """Add a plan to the creature."""
        self.plans.append(plan)
        # Sort by priority
        self.plans.sort(key=lambda p: p.priority, reverse=True)

    def get_active_plan(self) -> Optional[Plan]:
        """Get the highest priority active plan."""
        for plan in self.plans:
            if plan.status == PlanStatus.ACTIVE:
                return plan
        return None

    def get_plan_by_id(self, plan_id: str) -> Optional[Plan]:
        """Get a plan by its ID."""
        for plan in self.plans:
            if plan.id == plan_id:
                return plan
        return None

    def remove_plan(self, plan_id: str) -> bool:
        """Remove a plan by its ID."""
        for i, plan in enumerate(self.plans):
            if plan.id == plan_id:
                self.plans.pop(i)
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize creature state to dictionary."""
        return {
            "agent_id": self.agent_id,
            "position": list(self.position),
            "name": self.name,
            "description": self.description,
            "personality": self.personality,
            "inventory": [obj.to_dict() for obj in self.inventory],
            "goals": [goal.to_dict() for goal in self.goals],
            "memories": [
                memory.to_dict() for memory in self.memories[-10:]
            ],  # Last 10 memories
            "relationships": {
                name: rel.to_dict() for name, rel in self.relationships.items()
            },
            "plans": [plan.to_dict() for plan in self.plans],
        }
