"""Tool to perform technical analysis and generate charts for financial data."""

import base64
from io import BytesIO
from typing import TYPE_CHECKING, Optional

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import yfinance as yf

from gimle.hugin.tools.tool import ToolResponse

matplotlib.use("Agg")  # Use non-interactive backend

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index (RSI)."""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(
    prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate MACD (Moving Average Convergence Divergence)."""
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_bollinger_bands(
    prices: pd.Series, period: int = 20, std_dev: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate Bollinger Bands."""
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    return upper_band, sma, lower_band


def technical_analysis(
    stack: "Stack",
    symbol: str,
    period: str = "6mo",
    interval: str = "1d",
    indicators: Optional[list[str]] = None,
    generate_chart: bool = True,
) -> ToolResponse:
    """
    Perform technical analysis on a stock symbol.

    Args:
        stack: The interaction stack (auto-injected)
        symbol: Stock ticker symbol (e.g., AAPL, BTC-USD, EURUSD=X, GC=F)
        period: Time period for analysis (1mo, 3mo, 6mo, 1y, 2y, 5y, max)
        interval: Data interval (1d, 1wk, 1mo)
        indicators: List of indicators to calculate
                   (sma, ema, rsi, macd, bollinger, volume)
        generate_chart: Whether to generate and save visualization chart

    Returns:
        Dictionary with technical analysis results and chart artifact ID
    """
    # Handle None values from LLM calls
    if symbol is None:
        return ToolResponse(
            is_error=True,
            content={"error": "Symbol is required for technical analysis"},
        )
    if period is None:
        period = "6mo"
    if interval is None:
        interval = "1d"
    if generate_chart is None:
        generate_chart = True
    if indicators is None:
        indicators = ["sma", "ema", "rsi", "macd", "bollinger", "volume"]

    try:
        ticker = yf.Ticker(symbol)

        # Get historical data
        hist = ticker.history(period=period, interval=interval)

        if hist.empty:
            return ToolResponse(
                is_error=True,
                content={"error": f"No data found for symbol {symbol}"},
            )

        # Basic price statistics
        current_price = hist["Close"].iloc[-1]
        period_high = hist["High"].max()
        period_low = hist["Low"].min()
        period_return = (
            (hist["Close"].iloc[-1] - hist["Close"].iloc[0])
            / hist["Close"].iloc[0]
        ) * 100

        result = {
            "symbol": symbol.upper(),
            "period": period,
            "interval": interval,
            "data_points": len(hist),
            "current_price": round(current_price, 2),
            "period_high": round(period_high, 2),
            "period_low": round(period_low, 2),
            "period_return_percent": round(period_return, 2),
            "indicators": {},
        }

        # Calculate indicators
        if "sma" in indicators:
            sma_20 = hist["Close"].rolling(window=20).mean().iloc[-1]
            sma_50 = hist["Close"].rolling(window=50).mean().iloc[-1]
            sma_200 = (
                hist["Close"].rolling(window=200).mean().iloc[-1]
                if len(hist) >= 200
                else None
            )

            result["indicators"]["sma"] = {
                "sma_20": round(sma_20, 2) if pd.notna(sma_20) else None,
                "sma_50": round(sma_50, 2) if pd.notna(sma_50) else None,
                "sma_200": (
                    round(sma_200, 2)
                    if sma_200 is not None and pd.notna(sma_200)
                    else None
                ),
                "price_vs_sma_20": (
                    round(((current_price / sma_20) - 1) * 100, 2)
                    if pd.notna(sma_20)
                    else None
                ),
                "price_vs_sma_50": (
                    round(((current_price / sma_50) - 1) * 100, 2)
                    if pd.notna(sma_50)
                    else None
                ),
            }

        if "ema" in indicators:
            ema_12 = hist["Close"].ewm(span=12, adjust=False).mean().iloc[-1]
            ema_26 = hist["Close"].ewm(span=26, adjust=False).mean().iloc[-1]

            result["indicators"]["ema"] = {
                "ema_12": round(ema_12, 2),
                "ema_26": round(ema_26, 2),
            }

        if "rsi" in indicators:
            rsi = calculate_rsi(hist["Close"])
            current_rsi = rsi.iloc[-1]

            rsi_signal = (
                "oversold"
                if current_rsi < 30
                else ("overbought" if current_rsi > 70 else "neutral")
            )

            result["indicators"]["rsi"] = {
                "value": (
                    round(current_rsi, 2) if pd.notna(current_rsi) else None
                ),
                "signal": rsi_signal,
                "interpretation": (
                    "Strong buy signal"
                    if current_rsi < 30
                    else (
                        "Strong sell signal"
                        if current_rsi > 70
                        else "No clear signal"
                    )
                ),
            }

        if "macd" in indicators:
            macd_line, signal_line, histogram = calculate_macd(hist["Close"])

            current_macd = macd_line.iloc[-1]
            current_signal = signal_line.iloc[-1]
            current_hist = histogram.iloc[-1]

            macd_signal = "bullish" if current_hist > 0 else "bearish"

            result["indicators"]["macd"] = {
                "macd_line": (
                    round(current_macd, 2) if pd.notna(current_macd) else None
                ),
                "signal_line": (
                    round(current_signal, 2)
                    if pd.notna(current_signal)
                    else None
                ),
                "histogram": (
                    round(current_hist, 2) if pd.notna(current_hist) else None
                ),
                "signal": macd_signal,
            }

        if "bollinger" in indicators:
            upper_band, middle_band, lower_band = calculate_bollinger_bands(
                hist["Close"]
            )

            current_upper = upper_band.iloc[-1]
            current_middle = middle_band.iloc[-1]
            current_lower = lower_band.iloc[-1]

            # Calculate Bollinger Band Width
            bb_width = ((current_upper - current_lower) / current_middle) * 100

            # Price position within bands
            price_position = (
                (current_price - current_lower)
                / (current_upper - current_lower)
            ) * 100

            result["indicators"]["bollinger"] = {
                "upper_band": (
                    round(current_upper, 2) if pd.notna(current_upper) else None
                ),
                "middle_band": (
                    round(current_middle, 2)
                    if pd.notna(current_middle)
                    else None
                ),
                "lower_band": (
                    round(current_lower, 2) if pd.notna(current_lower) else None
                ),
                "bandwidth_percent": (
                    round(bb_width, 2) if pd.notna(bb_width) else None
                ),
                "price_position_percent": (
                    round(price_position, 2)
                    if pd.notna(price_position)
                    else None
                ),
                "interpretation": (
                    "Near upper band - potentially overbought"
                    if price_position > 80
                    else (
                        "Near lower band - potentially oversold"
                        if price_position < 20
                        else "Within normal range"
                    )
                ),
            }

        if "volume" in indicators:
            avg_volume = hist["Volume"].mean()
            recent_volume = hist["Volume"].tail(5).mean()
            volume_trend = ((recent_volume / avg_volume) - 1) * 100

            result["indicators"]["volume"] = {
                "average_volume": int(avg_volume),
                "recent_avg_volume": int(recent_volume),
                "volume_trend_percent": round(volume_trend, 2),
                "interpretation": (
                    "High volume activity"
                    if volume_trend > 20
                    else (
                        "Low volume activity"
                        if volume_trend < -20
                        else "Normal volume activity"
                    )
                ),
            }

        # Generate chart if requested
        if generate_chart:
            try:
                chart_artifact_id = _generate_chart(
                    stack, symbol, hist, indicators
                )
                result["chart_artifact_id"] = chart_artifact_id
            except Exception as e:
                result["chart_error"] = f"Could not generate chart: {str(e)}"

        return ToolResponse(is_error=False, content=result)

    except Exception as e:
        return ToolResponse(
            is_error=True,
            content={"error": f"Error analyzing {symbol}: {str(e)}"},
        )


def _generate_chart(
    stack: "Stack", symbol: str, hist: pd.DataFrame, indicators: list[str]
) -> str:
    """Generate technical analysis chart and save as artifact."""
    # Set style
    sns.set_style("darkgrid")
    plt.rcParams["figure.facecolor"] = "#f8f9fa"

    # Determine number of subplots
    num_plots = 1  # Price always included
    if "rsi" in indicators:
        num_plots += 1
    if "macd" in indicators:
        num_plots += 1
    if "volume" in indicators:
        num_plots += 1

    # Create figure with subplots
    fig, axes = plt.subplots(
        num_plots, 1, figsize=(14, 4 * num_plots), sharex=True
    )

    if num_plots == 1:
        axes = [axes]

    current_plot = 0

    # Plot 1: Price with moving averages and Bollinger Bands
    ax = axes[current_plot]
    ax.plot(
        hist.index,
        hist["Close"],
        label="Close Price",
        linewidth=2,
        color="#2c3e50",
    )

    if "sma" in indicators:
        sma_20 = hist["Close"].rolling(window=20).mean()
        sma_50 = hist["Close"].rolling(window=50).mean()
        ax.plot(
            hist.index,
            sma_20,
            label="SMA 20",
            linewidth=1.5,
            alpha=0.7,
            color="#3498db",
        )
        ax.plot(
            hist.index,
            sma_50,
            label="SMA 50",
            linewidth=1.5,
            alpha=0.7,
            color="#e74c3c",
        )

        if len(hist) >= 200:
            sma_200 = hist["Close"].rolling(window=200).mean()
            ax.plot(
                hist.index,
                sma_200,
                label="SMA 200",
                linewidth=1.5,
                alpha=0.7,
                color="#9b59b6",
            )

    if "bollinger" in indicators:
        upper_band, middle_band, lower_band = calculate_bollinger_bands(
            hist["Close"]
        )
        ax.plot(
            hist.index,
            upper_band,
            label="BB Upper",
            linewidth=1,
            linestyle="--",
            alpha=0.5,
            color="#95a5a6",
        )
        ax.plot(
            hist.index,
            middle_band,
            label="BB Middle",
            linewidth=1,
            linestyle="--",
            alpha=0.5,
            color="#7f8c8d",
        )
        ax.plot(
            hist.index,
            lower_band,
            label="BB Lower",
            linewidth=1,
            linestyle="--",
            alpha=0.5,
            color="#95a5a6",
        )
        ax.fill_between(
            hist.index, lower_band, upper_band, alpha=0.1, color="#95a5a6"
        )

    ax.set_ylabel("Price ($)", fontsize=12, fontweight="bold")
    ax.set_title(
        f"{symbol} Technical Analysis", fontsize=16, fontweight="bold", pad=20
    )
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(True, alpha=0.3)

    current_plot += 1

    # Plot 2: Volume
    if "volume" in indicators and current_plot < num_plots:
        ax = axes[current_plot]
        colors = [
            (
                "#27ae60"
                if hist["Close"].iloc[i] >= hist["Close"].iloc[i - 1]
                else "#e74c3c"
            )
            for i in range(1, len(hist))
        ]
        colors.insert(0, "#95a5a6")  # First bar color
        ax.bar(hist.index, hist["Volume"], color=colors, alpha=0.6, width=0.8)
        ax.set_ylabel("Volume", fontsize=12, fontweight="bold")
        ax.set_title("Trading Volume", fontsize=14, fontweight="bold", pad=15)
        ax.grid(True, alpha=0.3)
        current_plot += 1

    # Plot 3: RSI
    if "rsi" in indicators and current_plot < num_plots:
        ax = axes[current_plot]
        rsi = calculate_rsi(hist["Close"])
        ax.plot(hist.index, rsi, label="RSI (14)", linewidth=2, color="#3498db")
        ax.axhline(
            y=70,
            color="#e74c3c",
            linestyle="--",
            linewidth=1,
            alpha=0.7,
            label="Overbought (70)",
        )
        ax.axhline(
            y=30,
            color="#27ae60",
            linestyle="--",
            linewidth=1,
            alpha=0.7,
            label="Oversold (30)",
        )
        ax.fill_between(hist.index, 30, 70, alpha=0.1, color="#95a5a6")
        ax.set_ylabel("RSI", fontsize=12, fontweight="bold")
        ax.set_title(
            "Relative Strength Index (RSI)",
            fontsize=14,
            fontweight="bold",
            pad=15,
        )
        ax.set_ylim([0, 100])
        ax.legend(loc="upper left", fontsize=10)
        ax.grid(True, alpha=0.3)
        current_plot += 1

    # Plot 4: MACD
    if "macd" in indicators and current_plot < num_plots:
        ax = axes[current_plot]
        macd_line, signal_line, histogram = calculate_macd(hist["Close"])
        ax.plot(
            hist.index, macd_line, label="MACD", linewidth=2, color="#3498db"
        )
        ax.plot(
            hist.index,
            signal_line,
            label="Signal",
            linewidth=2,
            color="#e74c3c",
        )
        colors = ["#27ae60" if h > 0 else "#e74c3c" for h in histogram]
        ax.bar(
            hist.index,
            histogram,
            label="Histogram",
            color=colors,
            alpha=0.4,
            width=0.8,
        )
        ax.axhline(y=0, color="#000000", linestyle="-", linewidth=0.5)
        ax.set_ylabel("MACD", fontsize=12, fontweight="bold")
        ax.set_title(
            "MACD (Moving Average Convergence Divergence)",
            fontsize=14,
            fontweight="bold",
            pad=15,
        )
        ax.legend(loc="upper left", fontsize=10)
        ax.grid(True, alpha=0.3)
        current_plot += 1

    # Format x-axis for bottom plot
    axes[-1].set_xlabel("Date", fontsize=12, fontweight="bold")

    plt.tight_layout()

    # Save to BytesIO
    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)

    # Encode to base64
    img_base64 = base64.b64encode(buf.read()).decode("utf-8")

    # Save as artifact through storage directly
    # We create a simple artifact dict instead of using the Artifact class
    # which requires interaction context
    import uuid
    from datetime import datetime

    artifact_id = str(uuid.uuid4())
    artifact_data = {
        "id": artifact_id,
        "name": f"technical_analysis_{symbol}",
        "description": f"Technical analysis chart for {symbol}",
        "content_type": "image/png",
        "content": img_base64,
        "created_at": datetime.now().isoformat(),
        "metadata": {
            "symbol": symbol,
            "type": "technical_analysis_chart",
            "encoding": "base64",
        },
    }

    # Save through storage
    storage = None
    if stack.agent.session and stack.agent.session.storage:
        storage = stack.agent.session.storage
    elif hasattr(stack.agent.environment, "storage"):
        storage = stack.agent.environment.storage

    if storage and hasattr(storage, "artifacts_path"):
        # Save directly as JSON file in artifacts directory
        import json

        artifacts_path = storage.artifacts_path
        artifacts_path.mkdir(parents=True, exist_ok=True)
        artifact_file = artifacts_path / f"{artifact_id}.json"
        with open(artifact_file, "w") as f:
            json.dump(artifact_data, f, indent=2)

    return artifact_id
