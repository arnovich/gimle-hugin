"""Tool to write and store financial news articles."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Union

from gimle.hugin.agent.task import Task
from gimle.hugin.artifacts.text import Text
from gimle.hugin.interaction.agent_call import AgentCall
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def write_article(
    stack: "Stack",
    headline: str,
    content: str,
    category: str = "markets",
    related_symbols: Optional[List[str]] = None,
    chart_artifact_ids: Optional[List[str]] = None,
    skip_editor_review: bool = False,
) -> Union[ToolResponse, AgentCall]:
    """Write and format a financial news article.

    Args:
        stack: The interaction stack (auto-injected)
        headline: Article headline
        content: Article content (can include references to chart artifacts)
        category: Article category
        related_symbols: Stock symbols mentioned
        chart_artifact_ids: List of chart artifact IDs to embed in article

    Returns:
        Dictionary containing article info and storage path
    """
    try:
        # Check article limit
        env_vars = getattr(stack.agent.environment, "env_vars", {})
        max_articles = env_vars.get("number_of_articles", 999)
        current_articles = env_vars.get("newspaper_articles", [])

        if len(current_articles) >= max_articles:
            return ToolResponse(
                is_error=True,
                content={
                    "error": f"Article limit reached! You have already written "
                    f"{len(current_articles)} articles (limit: {max_articles}). "
                    f"Please proceed to create the newspaper layout with "
                    f"`update_newspaper_layout` instead of writing more articles."
                },
            )
        # Get current date for article dating
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M")

        # Create article ID
        article_id = str(uuid.uuid4())[:8]

        # Format the article
        formatted_article = f"""
# {headline}

**Category:** {category.title()}
**Published:** {date_str} at {time_str}
**Article ID:** {article_id}

{content}

---
"""

        if related_symbols:
            symbols_str = ", ".join(
                [f"${symbol}" for symbol in related_symbols]
            )
            formatted_article += f"**Related Stocks:** {symbols_str}\n\n"

        # Create article data structure
        article_data = {
            "id": article_id,
            "headline": headline,
            "content": content,
            "category": category,
            "related_symbols": related_symbols or [],
            "chart_artifact_ids": chart_artifact_ids or [],
            "published": now.isoformat(),
            "word_count": len(content.split()),
            "formatted": formatted_article,
        }

        # Save article as a Text artifact
        artifact = Text(
            interaction=stack.interactions[-1],
            content=formatted_article,
            format="markdown",
        )
        stack.interactions[-1].add_artifact(artifact)

        # Store article in agent's environment for newspaper layout
        # This allows update_newspaper_layout to access all articles easily
        if hasattr(stack.agent.environment, "env_vars"):
            if "newspaper_articles" not in stack.agent.environment.env_vars:
                stack.agent.environment.env_vars["newspaper_articles"] = []

            # Add artifact ID to article data for reference
            article_data["artifact_id"] = artifact.id

            stack.agent.environment.env_vars["newspaper_articles"].append(
                article_data
            )

        result = {
            "success": True,
            "article_id": article_id,
            "artifact_id": artifact.id,
            "headline": headline,
            "category": category,
            "word_count": len(content.split()),
            "published_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "related_symbols": related_symbols or [],
            "chart_artifact_ids": chart_artifact_ids or [],
            "preview": content[:200] + "..." if len(content) > 200 else content,
        }

        # Check if editor review is enabled
        if skip_editor_review:
            return ToolResponse(is_error=False, content=result)

        # Automatically trigger editor review
        try:
            editor_config = stack.agent.environment.config_registry.get(
                "editor"
            )

            # Create review prompt with article embedded
            review_prompt = f"""Review this article for The Daily Market Herald.

**Article ID**: {article_id}
**Headline**: {headline}

---
## Article Content:

{formatted_article}

---

## Your Review Task:

Evaluate this article against our publication standards:
1. Does it provide unique INSIGHTS, not just news summaries?
2. Is it accurate and well-sourced?
3. Does it include relevant technical analysis data (RSI, MACD, etc.)?
4. Is the writing clear and engaging?

After your evaluation, call the `finish` tool with your decision:
{{
  "decision": "approved" or "rejected",
  "quality_score": 1-10,
  "feedback": "specific feedback",
  "placement": "featured" / "top_story" / "regular"
}}
"""

            # Create the review task
            review_task = Task(
                name="review_article",
                description=f"Review article: {headline}",
                parameters={},
                prompt=review_prompt,
                tools=editor_config.tools,
                system_template=editor_config.system_template,
                llm_model=editor_config.llm_model,
            )

            # Return AgentCall to trigger editor review
            return AgentCall(
                stack=stack,
                config=editor_config,
                task=review_task,
            )
        except (KeyError, ValueError):
            # Editor config not found, return normal response
            result["note"] = "Editor review skipped - editor config not found"
            return ToolResponse(is_error=False, content=result)

    except Exception as e:
        return ToolResponse(
            is_error=True, content={"error": f"Error writing article: {str(e)}"}
        )
