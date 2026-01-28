"""Tool to finalize the newspaper edition by triggering editor layout creation."""

import json
from typing import TYPE_CHECKING, Union

from gimle.hugin.agent.task import Task
from gimle.hugin.interaction.agent_call import AgentCall
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def finalize_edition(
    stack: "Stack",
    summary: str = "",
) -> Union[ToolResponse, AgentCall]:
    """Finalize the newspaper edition by having the editor create the layout.

    This tool:
    1. Gathers all approved articles from the session
    2. Launches the editor agent to create the final newspaper layout
    3. The editor will call update_newspaper_layout and finish

    Args:
        stack: The interaction stack (auto-injected)
        summary: Optional summary of the edition

    Returns:
        AgentCall to trigger editor layout creation
    """
    try:
        env_vars = getattr(stack.agent.environment, "env_vars", {})
        articles = env_vars.get("newspaper_articles", [])

        if not articles:
            return ToolResponse(
                is_error=True,
                content={
                    "error": "No articles written yet. Write articles first."
                },
            )

        # Prepare articles list for editor
        articles_summary = []
        for article in articles:
            articles_summary.append(
                {
                    "id": article.get("id"),
                    "headline": article.get("headline"),
                    "category": article.get("category"),
                    "word_count": article.get("word_count"),
                    # Default quality score if not set by editor review
                    "quality_score": article.get("quality_score", 7),
                    "placement": article.get("placement", "regular"),
                }
            )

        # Get editor config
        try:
            editor_config = stack.agent.environment.config_registry.get(
                "editor"
            )
        except (KeyError, ValueError):
            return ToolResponse(
                is_error=True,
                content={"error": "Editor config not found"},
            )

        # Create layout prompt
        layout_prompt = f"""Create the final layout for today's edition of The Daily Market Herald.

## Approved Articles:

{json.dumps(articles_summary, indent=2)}

## Your Task:

1. Review the articles and their quality scores
2. Select the highest scoring article as FEATURED (or best if scores are equal)
3. Call `update_newspaper_layout` with the featured_article_id
4. Call `finish` with a summary of the layout

The `update_newspaper_layout` tool will arrange all articles - you just need to specify which one is featured.

{f"Edition summary from journalist: {summary}" if summary else ""}
"""

        # Create the layout task
        layout_task = Task(
            name="create_layout",
            description="Create the final newspaper layout",
            parameters={},
            prompt=layout_prompt,
            tools=editor_config.tools,
            system_template=editor_config.system_template,
            llm_model=editor_config.llm_model,
        )

        # Return AgentCall to trigger editor layout creation
        return AgentCall(
            stack=stack,
            config=editor_config,
            task=layout_task,
        )

    except Exception as e:
        return ToolResponse(
            is_error=True,
            content={"error": f"Error finalizing edition: {str(e)}"},
        )
