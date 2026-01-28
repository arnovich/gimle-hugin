"""Tool for creatures to recall their long-term memories."""

from typing import TYPE_CHECKING, Optional

from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def recall_memories_tool(
    world_id: str,
    query: str,
    memory_type: Optional[str] = None,
    limit: int = 5,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Search your long-term memories for relevant information.

    Use this to recall discoveries, relationships, locations, or events
    that you saved in previous sessions.

    Args:
        world_id: The ID of the world
        query: Search terms to find relevant memories
        memory_type: Optional filter by type (discovery, relationship,
                     location, event, thought)
        limit: Maximum number of memories to return (default 5)
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        List of matching memories with previews
    """
    if not stack:
        return ToolResponse(
            is_error=True, content={"error": "Stack not available"}
        )

    # Get query engine from environment
    environment = stack.agent.environment
    if not environment.storage:
        return ToolResponse(
            is_error=False,
            content={
                "found": False,
                "message": "No memories stored yet. Use 'remember' to save "
                "important moments!",
                "memories": [],
            },
        )

    query_engine = environment.query_engine

    try:
        # Search for memories (they're stored as Text artifacts)
        results = query_engine.query(
            query=query, limit=limit, artifact_type="Text"
        )

        if not results:
            return ToolResponse(
                is_error=False,
                content={
                    "found": False,
                    "message": f"No memories found matching '{query}'. "
                    "Try different search terms.",
                    "memories": [],
                },
            )

        # Format results for creature
        memories = []
        for result in results:
            # Parse memory type from preview if possible
            preview = result.content_preview
            mem_type = "unknown"
            if "Type**: discovery" in preview:
                mem_type = "discovery"
            elif "Type**: relationship" in preview:
                mem_type = "relationship"
            elif "Type**: location" in preview:
                mem_type = "location"
            elif "Type**: event" in preview:
                mem_type = "event"
            elif "Type**: thought" in preview:
                mem_type = "thought"

            # Filter by memory type if specified
            if memory_type and mem_type != memory_type.lower():
                continue

            memories.append(
                {
                    "memory_id": result.artifact_id,
                    "type": mem_type,
                    "preview": (
                        preview[:200] + "..." if len(preview) > 200 else preview
                    ),
                    "relevance": result.score,
                }
            )

        if not memories:
            msg = f"No {memory_type} memories found matching '{query}'."
            if memory_type:
                msg += " Try without the type filter."
            return ToolResponse(
                is_error=False,
                content={
                    "found": False,
                    "message": msg,
                    "memories": [],
                },
            )

        return ToolResponse(
            is_error=False,
            content={
                "found": True,
                "query": query,
                "count": len(memories),
                "memories": memories,
                "message": f"Found {len(memories)} memory/memories matching "
                f"'{query}'. Use 'get_memory_detail' with a memory_id "
                "to see full content.",
            },
        )

    except Exception as e:
        return ToolResponse(
            is_error=True,
            content={"error": f"Error recalling memories: {str(e)}"},
        )


def get_memory_detail_tool(
    world_id: str,
    memory_id: str,
    reason: Optional[str] = None,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Get the full content of a specific memory.

    Use this after recall_memories to see the complete details of a
    memory that seems relevant.

    Args:
        world_id: The ID of the world
        memory_id: The ID of the memory to retrieve
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        The full memory content
    """
    if not stack:
        return ToolResponse(
            is_error=True, content={"error": "Stack not available"}
        )

    environment = stack.agent.environment
    if not environment.storage:
        return ToolResponse(
            is_error=True,
            content={"error": "No storage available."},
        )

    query_engine = environment.query_engine

    try:
        content = query_engine.get_artifact_content(memory_id)

        if content is None:
            return ToolResponse(
                is_error=True,
                content={
                    "error": f"Memory {memory_id} not found. It may have "
                    "been from a different session."
                },
            )

        return ToolResponse(
            is_error=False,
            content={
                "memory_id": memory_id,
                "content": content,
                "message": "Here is the full memory:",
            },
        )

    except Exception as e:
        return ToolResponse(
            is_error=True,
            content={"error": f"Error retrieving memory: {str(e)}"},
        )
