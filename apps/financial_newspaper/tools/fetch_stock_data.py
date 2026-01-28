"""Tool to fetch stock data using yfinance."""

import yfinance as yf

from gimle.hugin.tools.tool import ToolResponse


def fetch_stock_data(
    symbol: str, period: str = "5d", include_info: bool = True
) -> ToolResponse:
    """
    Fetch stock data for a given symbol.

    Args:
        stack: The interaction stack (auto-injected)
        symbol: Stock ticker symbol
        period: Time period for historical data
        include_info: Whether to include company info

    Returns:
        Dictionary containing stock data and analysis
    """
    # Handle None values from LLM calls
    if symbol is None:
        return ToolResponse(
            is_error=True,
            content={"error": "Symbol is required for fetching stock data"},
        )
    if period is None:
        period = "5d"
    if include_info is None:
        include_info = True

    try:
        ticker = yf.Ticker(symbol)

        # Get historical data
        hist = ticker.history(period=period)

        if hist.empty:
            return ToolResponse(
                is_error=True,
                content={"error": f"No data found for symbol {symbol}"},
            )

        # Calculate basic metrics
        latest = hist.iloc[-1]
        previous = hist.iloc[-2] if len(hist) > 1 else hist.iloc[-1]

        price_change = latest["Close"] - previous["Close"]
        price_change_pct = (price_change / previous["Close"]) * 100

        # Get volume analysis
        avg_volume = hist["Volume"].mean()
        latest_volume = latest["Volume"]
        volume_ratio = latest_volume / avg_volume if avg_volume > 0 else 1.0

        result = {
            "symbol": symbol.upper(),
            "current_price": round(latest["Close"], 2),
            "price_change": round(price_change, 2),
            "price_change_percent": round(price_change_pct, 2),
            "volume": int(latest_volume),
            "volume_vs_average": round(volume_ratio, 2),
            "high_52w": round(hist["High"].max(), 2),
            "low_52w": round(hist["Low"].min(), 2),
            "period_analyzed": period,
            "trading_days": len(hist),
        }

        # Add company info if requested
        if include_info:
            try:
                info = ticker.info
                if info and isinstance(info, dict):
                    result["company_info"] = {
                        "name": info.get("longName", "N/A"),
                        "sector": info.get("sector", "N/A"),
                        "industry": info.get("industry", "N/A"),
                        "market_cap": info.get("marketCap", "N/A"),
                        "pe_ratio": info.get(
                            "forwardPE", info.get("trailingPE", "N/A")
                        ),
                        "dividend_yield": info.get("dividendYield", "N/A"),
                        "beta": info.get("beta", "N/A"),
                    }
                else:
                    result["company_info_error"] = "Company info not available"
            except Exception as e:
                result["company_info_error"] = (
                    f"Could not fetch company info: {str(e)}"
                )

        # Add price trend analysis
        if len(hist) >= 5:
            recent_trend = hist["Close"].tail(5).pct_change().mean() * 100
            result["recent_trend"] = {
                "direction": "up" if recent_trend > 0 else "down",
                "strength": abs(round(recent_trend, 2)),
            }

        return ToolResponse(is_error=False, content=result)

    except Exception as e:
        return ToolResponse(
            is_error=True,
            content={"error": f"Error fetching data for {symbol}: {str(e)}"},
        )
