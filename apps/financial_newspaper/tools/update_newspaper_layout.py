"""Tool to create and update newspaper layout."""

import os
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from gimle.hugin.artifacts.text import Text
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def update_newspaper_layout(
    stack: "Stack",
    edition_title: str = "Daily Edition",
    featured_article_id: Optional[str] = None,
) -> ToolResponse:
    """Update the newspaper's front page layout.

    Args:
        stack: The interaction stack (auto-injected)
        edition_title: Title for this edition
        featured_article_id: ID of featured article

    Returns:
        Dictionary containing layout info and HTML path
    """
    try:
        # Get articles from environment
        articles = []
        if hasattr(stack.agent.environment, "env_vars"):
            articles = stack.agent.environment.env_vars.get(
                "newspaper_articles", []
            )

        if not articles:
            return ToolResponse(
                is_error=True,
                content={"error": "No articles available for layout"},
            )

        # Sort articles by category priority
        category_priority = {
            "breaking": 1,
            "markets": 2,
            "earnings": 3,
            "analysis": 4,
            "opinion": 5,
        }

        sorted_articles = sorted(
            articles,
            key=lambda x: (
                category_priority.get(x["category"], 6),
                x["published"],
            ),
        )

        # Find featured article
        featured_article = None
        if featured_article_id:
            featured_article = next(
                (a for a in sorted_articles if a["id"] == featured_article_id),
                None,
            )

        if not featured_article and sorted_articles:
            featured_article = sorted_articles[0]

        # Generate newspaper HTML
        now = datetime.now()
        date_str = now.strftime("%B %d, %Y")
        generation_timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Daily Market Herald - {edition_title}</title>
    <style>
        * {{
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Georgia', 'Times New Roman', serif;
            margin: 0;
            padding: 20px;
            background: #e8e6e1;
            color: #1a1a1a;
            line-height: 1.6;
        }}
        .newspaper {{
            max-width: 1200px;
            margin: 0 auto;
            background: #faf8f4;
            box-shadow: 0 0 30px rgba(0,0,0,0.3);
            padding: 40px 50px;
        }}
        .header {{
            text-align: center;
            border-top: 3px solid #000;
            border-bottom: 3px solid #000;
            padding: 15px 0 20px 0;
            margin-bottom: 30px;
            position: relative;
        }}
        .header::before,
        .header::after {{
            content: '';
            position: absolute;
            left: 0;
            right: 0;
            height: 1px;
            background: #000;
        }}
        .header::before {{ top: 5px; }}
        .header::after {{ bottom: 5px; }}
        .masthead {{
            font-size: 72px;
            font-weight: 900;
            letter-spacing: 8px;
            margin: 10px 0 5px 0;
            text-transform: uppercase;
            font-family: 'Playfair Display', 'Georgia', serif;
            text-shadow: 2px 2px 0px rgba(0,0,0,0.1);
        }}
        .tagline {{
            font-style: italic;
            font-size: 13px;
            margin: 5px 0;
            letter-spacing: 2px;
            font-weight: 300;
        }}
        .date {{
            font-size: 14px;
            font-weight: bold;
            margin-top: 10px;
            letter-spacing: 1px;
            text-transform: uppercase;
        }}
        .featured {{
            border: 3px solid #000;
            padding: 25px;
            margin: 30px 0;
            background: #fff;
            box-shadow: inset 0 0 0 1px #000;
        }}
        .featured h2 {{
            font-size: 42px;
            margin: 0 0 18px 0;
            line-height: 1.1;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: -1px;
        }}
        .articles-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 30px;
            margin: 30px 0;
        }}
        .article {{
            border-top: 2px solid #000;
            padding-top: 15px;
        }}
        .article h3 {{
            font-size: 20px;
            margin: 0 0 12px 0;
            line-height: 1.2;
            font-weight: bold;
        }}
        .article-meta {{
            font-size: 11px;
            color: #666;
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid #ddd;
            padding-bottom: 8px;
        }}
        .article-content {{
            line-height: 1.7;
            text-align: justify;
            font-size: 14px;
            hyphens: auto;
            column-count: 1;
        }}
        .featured .article-content {{
            column-count: 2;
            column-gap: 25px;
            font-size: 15px;
        }}
        /* Expandable article styles */
        .article-details {{
            border: none;
        }}
        .article-summary {{
            cursor: pointer;
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        .article-summary::-webkit-details-marker {{
            display: none;
        }}
        .article-preview {{
            line-height: 1.7;
            text-align: justify;
            font-size: 14px;
            hyphens: auto;
            margin-bottom: 8px;
        }}
        .read-more {{
            color: #1565c0;
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 8px;
            display: inline-block;
        }}
        .read-more::after {{
            content: ' ▼';
            font-size: 10px;
        }}
        .article-details[open] .read-more {{
            display: none;
        }}
        .article-full {{
            line-height: 1.7;
            text-align: justify;
            font-size: 14px;
            hyphens: auto;
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px dashed #ddd;
        }}
        .featured .article-full {{
            column-count: 2;
            column-gap: 25px;
            font-size: 15px;
        }}
        .stocks {{
            background: #f0f0f0;
            padding: 8px 12px;
            margin: 12px 0 0 0;
            font-family: 'Courier New', monospace;
            font-size: 11px;
            border-left: 3px solid #000;
            font-weight: bold;
        }}
        .category {{
            display: inline-block;
            background: #000;
            color: white;
            padding: 4px 10px;
            font-size: 9px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 12px;
            font-weight: bold;
        }}
        .breaking {{ background: #c62828; }}
        .markets {{ background: #1565c0; }}
        .earnings {{ background: #2e7d32; }}
        .analysis {{ background: #ef6c00; }}
        .opinion {{ background: #6a1b9a; }}
        .auto-refresh {{
            position: fixed;
            top: 20px;
            right: 20px;
            background: rgba(0,0,0,0.85);
            color: white;
            padding: 8px 14px;
            border-radius: 4px;
            font-size: 11px;
            font-family: 'Courier New', monospace;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }}
        /* Metadata Section */
        .metadata-section {{
            margin: 30px 0 20px 0;
            border-top: 2px solid #000;
            padding-top: 20px;
        }}
        .metadata-details {{
            background: #f5f5f5;
            border: 1px solid #999;
        }}
        .metadata-summary {{
            padding: 12px 18px;
            cursor: pointer;
            font-weight: bold;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            user-select: none;
            list-style: none;
            background: #e8e6e1;
            border-bottom: 1px solid #999;
        }}
        .metadata-summary::-webkit-details-marker {{
            display: none;
        }}
        .metadata-summary::before {{
            content: '▶ ';
            display: inline-block;
            transition: transform 0.2s;
            margin-right: 5px;
        }}
        .metadata-details[open] .metadata-summary::before {{
            transform: rotate(90deg);
        }}
        .metadata-content {{
            padding: 18px;
            font-size: 11px;
            line-height: 1.8;
        }}
        .metadata-grid {{
            display: grid;
            grid-template-columns: auto 1fr;
            gap: 10px 20px;
            max-width: 600px;
        }}
        .metadata-label {{
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .metadata-value {{
            font-family: 'Courier New', monospace;
            color: #333;
        }}
        @media (max-width: 768px) {{
            .articles-grid {{
                grid-template-columns: 1fr;
            }}
            .featured .article-content {{
                column-count: 1;
            }}
            .masthead {{
                font-size: 42px;
                letter-spacing: 4px;
            }}
        }}
    </style>
    <script>
        // Auto-refresh every 5 minutes
        setTimeout(() => location.reload(), 300000);
    </script>
</head>
<body>
    <div class="auto-refresh">Generated: {now.strftime("%I:%M:%S %p")}</div>

    <div class="newspaper">
        <header class="header">
            <h1 class="masthead">The Daily Market Herald</h1>
            <p class="tagline">"Your Trusted Source for Financial Intelligence"</p>
            <p class="date">{date_str} • {edition_title}</p>
        </header>

"""

        # Add featured article
        if featured_article:
            content_full = featured_article["content"]
            is_truncated = len(content_full) > 400
            content_preview = (
                content_full[:400] + "..." if is_truncated else content_full
            )

            html_content += f"""
        <div class="featured">
            <span class="category {featured_article["category"]}">{featured_article["category"]}</span>
            <h2>{featured_article["headline"]}</h2>
"""

            if is_truncated:
                html_content += f"""
            <details class="article-details">
                <summary class="article-summary">
                    <div class="article-preview">{content_preview}</div>
                    <span class="read-more">Read Full Article</span>
                </summary>
                <div class="article-full">{content_full}</div>
            </details>
"""
            else:
                html_content += f"""
            <div class="article-content">{content_full}</div>
"""

            if featured_article["related_symbols"]:
                symbols_html = " | ".join(
                    [f"${s}" for s in featured_article["related_symbols"]]
                )
                html_content += (
                    f'<div class="stocks">Related: {symbols_html}</div>'
                )

            html_content += "</div>\n"

        # Add other articles in a 3-column grid
        other_articles = [a for a in sorted_articles if a != featured_article]
        if other_articles:
            html_content += '\n        <div class="articles-grid">\n'

            for article in other_articles:
                content_full = article["content"]
                is_truncated = len(content_full) > 200
                content_preview = (
                    content_full[:200] + "..." if is_truncated else content_full
                )

                html_content += f"""
            <article class="article">
                <span class="category {article["category"]}">{article["category"]}</span>
                <h3>{article["headline"]}</h3>
                <div class="article-meta">Published: {datetime.fromisoformat(article["published"]).strftime("%I:%M %p")}</div>
"""

                if is_truncated:
                    html_content += f"""
                <details class="article-details">
                    <summary class="article-summary">
                        <div class="article-preview">{content_preview}</div>
                        <span class="read-more">Read Full Article</span>
                    </summary>
                    <div class="article-full">{content_full}</div>
                </details>
"""
                else:
                    html_content += f"""
                <div class="article-content">{content_full}</div>
"""

                if article["related_symbols"]:
                    symbols_html = " | ".join(
                        [f"${s}" for s in article["related_symbols"]]
                    )
                    html_content += f'                <div class="stocks">Related: {symbols_html}</div>\n'

                html_content += "            </article>\n"

            html_content += "        </div>\n"

        # Calculate additional metadata
        total_symbols = len(
            set([sym for a in articles for sym in a["related_symbols"]])
        )
        categories_list = ", ".join(
            sorted(set([a["category"] for a in articles]))
        )
        total_word_count = sum([a.get("word_count", 0) for a in articles])

        html_content += f"""
        <!-- Metadata Section -->
        <div class="metadata-section">
            <details class="metadata-details">
                <summary class="metadata-summary">Publication Metadata</summary>
                <div class="metadata-content">
                    <div class="metadata-grid">
                        <span class="metadata-label">Generated:</span>
                        <span class="metadata-value">{generation_timestamp}</span>

                        <span class="metadata-label">Edition:</span>
                        <span class="metadata-value">{edition_title}</span>

                        <span class="metadata-label">Total Articles:</span>
                        <span class="metadata-value">{len(articles)}</span>

                        <span class="metadata-label">Featured Article:</span>
                        <span class="metadata-value">{featured_article["headline"] if featured_article else "None"}</span>

                        <span class="metadata-label">Categories Covered:</span>
                        <span class="metadata-value">{categories_list}</span>

                        <span class="metadata-label">Unique Symbols:</span>
                        <span class="metadata-value">{total_symbols}</span>

                        <span class="metadata-label">Total Word Count:</span>
                        <span class="metadata-value">{total_word_count:,}</span>
                    </div>
                </div>
            </details>
        </div>
    </div>
</body>
</html>
"""

        # Create HTML artifact for display in agent monitor
        artifact = Text(
            interaction=stack.interactions[-1],
            content=html_content,
            format="html",
        )
        stack.interactions[-1].add_artifact(artifact)

        # Also save HTML file for backward compatibility
        newspaper_dir = "storage/newspaper_layouts"
        os.makedirs(newspaper_dir, exist_ok=True)

        filename = f"newspaper_{now.strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(newspaper_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Also create/update "latest.html" for easy access
        latest_path = os.path.join(newspaper_dir, "latest.html")
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        result = {
            "success": True,
            "edition_title": edition_title,
            "articles_included": len(articles),
            "featured_article": (
                featured_article["headline"] if featured_article else None
            ),
            "artifact_id": artifact.id,
            "layout_file": filepath,
            "latest_file": latest_path,
            "categories_covered": list(set([a["category"] for a in articles])),
            "total_symbols": len(
                set([sym for a in articles for sym in a["related_symbols"]])
            ),
            "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        }

        return ToolResponse(is_error=False, content=result)

    except Exception as e:
        return ToolResponse(
            is_error=True,
            content={"error": f"Error updating newspaper layout: {str(e)}"},
        )
