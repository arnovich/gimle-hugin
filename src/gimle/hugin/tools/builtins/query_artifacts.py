"""Query artifacts tool for searching saved insights and knowledge."""

from typing import TYPE_CHECKING, Optional

from gimle.hugin.tools.tool import Tool, ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


@Tool.register(
    name="builtins.query_artifacts",
    description="Search through saved artifacts (insights, knowledge) using keywords. Returns matching artifacts with previews. Use this to find relevant information from previously saved research and findings.",
    parameters={
        "query": {
            "type": "string",
            "description": "Search keywords to find relevant artifacts",
            "required": True,
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of results to return (default: 5)",
            "required": False,
        },
        "artifact_type": {
            "type": "string",
            "description": "Optional filter by artifact type (e.g., 'Text')",
            "required": False,
        },
    },
    is_interactive=False,
)
def query_artifacts(
    stack: "Stack",
    query: str,
    limit: int = 5,
    artifact_type: Optional[str] = None,
) -> ToolResponse:
    """
    Search through saved artifacts (insights, knowledge) using keyword search.

    Use this tool to find relevant information from previously saved insights.
    This is useful when you need to reference past research, findings, or knowledge
    that was saved during this or previous sessions.

    Args:
        query: Search keywords to find relevant artifacts
        limit: Maximum number of results to return (default: 5)
        artifact_type: Optional filter by artifact type (e.g., "Text")
        stack: The stack (passed automatically)

    Returns:
        ToolResponse with matching artifacts and their content previews
    """
    # Get query engine from environment
    environment = stack.agent.environment
    if not environment.storage:
        return ToolResponse(
            is_error=True,
            content={
                "error": "No storage available. Cannot query artifacts without storage."
            },
        )

    query_engine = environment.query_engine

    # Perform search
    try:
        results = query_engine.query(
            query=query, limit=limit, artifact_type=artifact_type
        )

        if not results:
            return ToolResponse(
                is_error=False,
                content={
                    "found": False,
                    "message": f"No artifacts found matching query: '{query}'",
                    "results": [],
                },
            )

        # Format results for agent
        formatted_results = []
        for result in results:
            formatted_results.append(
                {
                    "artifact_id": result.artifact_id,
                    "type": result.artifact_type,
                    "preview": result.content_preview,
                    "relevance_score": result.score,
                    "created_at": result.metadata.get("created_at"),
                }
            )

        return ToolResponse(
            is_error=False,
            content={
                "found": True,
                "query": query,
                "count": len(formatted_results),
                "results": formatted_results,
                "message": f"Found {len(formatted_results)} artifact(s) matching '{query}'",
            },
        )

    except Exception as e:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Error querying artifacts: {str(e)}",
            },
        )


@Tool.register(
    name="builtins.get_artifact_content",
    description="Retrieve the full content of a specific artifact by ID. Use this after query_artifacts to get complete content of a relevant artifact.",
    parameters={
        "artifact_id": {
            "type": "string",
            "description": "UUID of the artifact to retrieve",
            "required": True,
        },
    },
    is_interactive=False,
)
def get_artifact_content(
    artifact_id: str,
    stack: Optional["Stack"] = None,
    branch: Optional[str] = None,
) -> ToolResponse:
    """
    Retrieve the full content of a specific artifact by ID.

    Use this after query_artifacts to get the complete content of an artifact
    that seems relevant.

    Args:
        artifact_id: UUID of the artifact to retrieve
        stack: The stack (passed automatically)
        branch: Optional branch identifier (passed automatically)

    Returns:
        ToolResponse with the full artifact content
    """
    if not stack:
        return ToolResponse(
            is_error=True,
            content={"error": "Stack not available"},
        )

    # Get query engine from environment
    environment = stack.agent.environment
    if not environment.storage:
        return ToolResponse(
            is_error=True,
            content={
                "error": "No storage available. Cannot retrieve artifact without storage."
            },
        )

    query_engine = environment.query_engine

    # Get artifact content
    try:
        content = query_engine.get_artifact_content(artifact_id)

        if content is None:
            return ToolResponse(
                is_error=True,
                content={
                    "error": f"Artifact {artifact_id} not found",
                },
            )

        return ToolResponse(
            is_error=False,
            content={
                "artifact_id": artifact_id,
                "content": content,
            },
        )

    except Exception as e:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Error retrieving artifact: {str(e)}",
            },
        )
