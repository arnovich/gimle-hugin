"""Tool for creatures to check their relationships with others."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union, cast

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from world import World

    from gimle.hugin.interaction.stack import Stack

# Type alias for relationship dict
RelationshipDict = Dict[str, Union[str, int, None]]


def get_relationships_tool(
    world_id: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Check your relationships with other creatures you have met.

    Args:
        world_id: The ID of the world
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        List of relationships with sentiment and interaction history
    """
    if not stack:
        return ToolResponse(
            is_error=True, content={"error": "Stack not available"}
        )

    agent_id = stack.agent.id

    # Get world from environment
    env_vars = stack.agent.environment.env_vars
    worlds: Dict[str, Any] = env_vars.get("worlds", {})
    if world_id not in worlds:
        return ToolResponse(
            is_error=True, content={"error": f"World '{world_id}' not found"}
        )

    world = cast("World", worlds[world_id])

    # Get creature
    creature = world.get_creature(agent_id)
    if not creature:
        return ToolResponse(
            is_error=True,
            content={"error": f"Creature {agent_id} not found in world"},
        )

    # Get relationships
    relationships: List[RelationshipDict] = []
    for name, rel in creature.relationships.items():
        sentiment_desc = _describe_sentiment(rel.sentiment)
        relationships.append(
            {
                "creature_name": name,
                "relationship_type": rel.relationship_type,
                "sentiment": rel.sentiment,
                "sentiment_description": sentiment_desc,
                "interactions": rel.interactions,
                "last_interaction_tick": rel.last_interaction_tick,
            }
        )

    # Sort by most recent interaction
    def get_last_tick(r: RelationshipDict) -> int:
        tick = r.get("last_interaction_tick")
        return tick if isinstance(tick, int) else 0

    relationships.sort(key=get_last_tick, reverse=True)

    # Create summary
    if relationships:
        friends: List[str] = []
        rivals: List[str] = []
        for r in relationships:
            sentiment = r.get("sentiment")
            name_val = r.get("creature_name")
            if isinstance(sentiment, int) and isinstance(name_val, str):
                if sentiment >= 7:
                    friends.append(name_val)
                elif sentiment <= 3:
                    rivals.append(name_val)

        summary_parts = [f"You know {len(relationships)} creature(s)."]
        if friends:
            summary_parts.append(f"Friends: {', '.join(friends)}")
        if rivals:
            summary_parts.append(f"Rivals: {', '.join(rivals)}")
        summary = " ".join(summary_parts)
    else:
        summary = "You haven't met any other creatures yet."

    return ToolResponse(
        is_error=False,
        content={
            "relationships": relationships,
            "count": len(relationships),
            "summary": summary,
        },
    )


def _describe_sentiment(sentiment: int) -> str:
    """Convert sentiment score to description."""
    if sentiment >= 9:
        return "best friend"
    elif sentiment >= 7:
        return "friend"
    elif sentiment >= 5:
        return "acquaintance"
    elif sentiment >= 3:
        return "unfriendly"
    else:
        return "rival"
