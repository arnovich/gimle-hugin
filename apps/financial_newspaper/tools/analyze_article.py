"""Tool to fetch and analyze full article content."""

import re
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from gimle.hugin.tools.tool import ToolResponse


def analyze_article(
    url: str, focus_questions: Optional[List[str]] = None
) -> ToolResponse:
    """Fetch and analyze the full content of a news article.

    Args:
        stack: The interaction stack (auto-injected)
        url: URL of the article to analyze
        focus_questions: Specific questions or angles to analyze

    Returns:
        Dictionary containing full article content and metadata
    """
    try:
        # Set user agent to avoid being blocked
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

        # Fetch the article
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # Parse HTML
        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        # Try to find article content
        # Common article content selectors
        article_selectors = [
            "article",
            '[class*="article"]',
            '[class*="story"]',
            '[class*="content"]',
            "main",
        ]

        article_content = None
        for selector in article_selectors:
            article_content = soup.select_one(selector)
            if article_content:
                break

        if not article_content:
            article_content = soup.body

        # Extract text
        if article_content is None:
            text = ""
        else:
            text = article_content.get_text(separator="\n", strip=True)

        # Clean up text
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        text = "\n".join(lines)

        # Extract title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.h1:
            title = soup.h1.get_text(strip=True)

        # Extract key data points (numbers, percentages, dates)
        numbers = re.findall(r"\$?[\d,]+\.?\d*%?", text)
        dates = re.findall(
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
            text,
            re.IGNORECASE,
        )

        # Extract quoted text (potential insights from experts)
        quotes = []
        quote_pattern = r'[""]([^""]{20,200})[""]'
        found_quotes = re.findall(quote_pattern, text)
        quotes = found_quotes[:5]  # Limit to 5 quotes

        # Word count and reading time
        word_count = len(text.split())
        reading_time = max(1, word_count // 200)  # ~200 words per minute

        result = {
            "url": url,
            "title": title,
            "full_content": text[
                :5000
            ],  # Limit to 5000 chars to avoid token issues
            "word_count": word_count,
            "reading_time_minutes": reading_time,
            "key_numbers": list(set(numbers[:20])),  # Deduplicate and limit
            "dates_mentioned": list(set(dates)),
            "notable_quotes": quotes,
            "focus_questions": focus_questions or [],
            "content_preview": text[:500] + "..." if len(text) > 500 else text,
        }

        return ToolResponse(is_error=False, content=result)

    except requests.Timeout:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Timeout while fetching article from {url}",
                "url": url,
            },
        )
    except requests.RequestException as e:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Error fetching article: {str(e)}",
                "url": url,
            },
        )
    except Exception as e:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Error analyzing article: {str(e)}",
                "url": url,
            },
        )
