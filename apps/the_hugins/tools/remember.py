"""Tool for creatures to save long-term memories."""

from typing import TYPE_CHECKING, Optional

from gimle.hugin.artifacts.text import Text
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


MEMORY_TYPES = ["discovery", "relationship", "location", "event", "thought"]


def remember_tool(
    world_id: str,
    memory_type: str,
    description: str,
    importance: int = 5,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Save an important memory for long-term storage.

    Use this to remember significant discoveries, relationships, locations,
    or events that you want to recall in future sessions.

    Args:
        world_id: The ID of the world
        memory_type: Type of memory - discovery, relationship, location,
                     event, or thought
        description: What you want to remember
        importance: How important this memory is (1-10, default 5)
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        Confirmation of memory saved with artifact ID
    """
    if not stack:
        return ToolResponse(
            is_error=True, content={"error": "Stack not available"}
        )

    memory_type = memory_type.lower().strip()
    if memory_type not in MEMORY_TYPES:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Invalid memory type '{memory_type}'. "
                f"Choose from: {MEMORY_TYPES}",
                "valid_types": MEMORY_TYPES,
            },
        )

    # Clamp importance to 1-10
    importance = max(1, min(10, importance))

    # Get creature info if available
    creature_name = "Unknown Creature"
    agent_id = stack.agent.id
    env_vars = stack.agent.environment.env_vars
    worlds = env_vars.get("worlds", {})
    world = worlds.get(world_id)
    if world:
        creature = world.get_creature(agent_id)
        if creature:
            creature_name = creature.name

    # Format as structured markdown for searchability
    memory_content = f"""# Memory: {memory_type.title()}

**Creature**: {creature_name}
**Importance**: {importance}/10
**Type**: {memory_type}
**World**: {world_id}

## What I Remember

{description}
"""

    try:
        artifact = Text(
            interaction=stack.interactions[-1],
            content=memory_content,
            format="markdown",
        )
        stack.interactions[-1].add_artifact(artifact)

        return ToolResponse(
            is_error=False,
            content={
                "success": True,
                "artifact_id": artifact.id,
                "memory_type": memory_type,
                "importance": importance,
                "message": f"Memory saved! You will be able to recall this "
                f"{memory_type} in future sessions.",
            },
        )

    except Exception as e:
        return ToolResponse(
            is_error=True,
            content={"error": f"Failed to save memory: {str(e)}"},
        )
