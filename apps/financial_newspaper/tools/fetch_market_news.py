"""Tool to fetch market news headlines."""

from datetime import datetime

import yfinance as yf

from gimle.hugin.tools.tool import ToolResponse


def fetch_market_news(
    query: str = "stock market", limit: int = 10
) -> ToolResponse:
    """
    Fetch recent financial news headlines.

    Args:
        stack: The interaction stack (auto-injected)
        query: Search query for news
        limit: Maximum number of news items

    Returns:
        Dictionary containing news headlines and summaries
    """
    # Handle None values from LLM calls
    if query is None:
        query = "stock market"
    if limit is None:
        limit = 10

    try:
        # For demo purposes, we'll use yfinance to get news for major tickers
        # In a production system, you'd use a dedicated news API

        major_tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "SPY", "QQQ"]
        all_news = []

        for ticker_symbol in major_tickers:
            try:
                ticker = yf.Ticker(ticker_symbol)
                news = ticker.news

                # Handle None or empty news
                if not news or not isinstance(news, list):
                    continue

                for item in news[:2]:  # Limit per ticker to avoid too much data
                    if not item or not isinstance(item, dict):
                        continue
                    all_news.append(
                        {
                            "title": item.get("title", "No title"),
                            "summary": item.get(
                                "summary", "No summary available"
                            ),
                            "url": item.get("link", ""),
                            "published": datetime.fromtimestamp(
                                item.get(
                                    "providerPublishTime",
                                    datetime.now().timestamp(),
                                )
                            ).strftime("%Y-%m-%d %H:%M"),
                            "source": item.get("publisher", "Unknown"),
                            "related_ticker": ticker_symbol,
                        }
                    )

            except Exception:
                continue  # Skip tickers that fail

        # Sort by published time (most recent first) and limit results
        all_news.sort(key=lambda x: x["published"], reverse=True)
        limited_news = all_news[:limit]

        # If we're searching for specific terms, filter further
        if query.lower() not in ["stock market", "market", "stocks"]:
            filtered_news = []
            query_terms = query.lower().split()

            for item in limited_news:
                title_lower = item["title"].lower()
                summary_lower = item["summary"].lower()

                # Check if any query term appears in title or summary
                if any(
                    term in title_lower or term in summary_lower
                    for term in query_terms
                ):
                    filtered_news.append(item)

            if filtered_news:
                limited_news = filtered_news

        result = {
            "query": query,
            "total_found": len(limited_news),
            "news_items": limited_news,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sources_covered": list(
                set([item["source"] for item in limited_news])
            ),
        }

        return ToolResponse(is_error=False, content=result)

    except Exception as e:
        return ToolResponse(
            is_error=True,
            content={"error": f"Error fetching market news: {str(e)}"},
        )
