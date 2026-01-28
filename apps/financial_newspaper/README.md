# Financial Newspaper Agent

An agentic financial journalist that creates a daily market newspaper using real-time financial data and deep article analysis.

## Overview

This app demonstrates a **multi-agent workflow** for "The Daily Market Herald" newspaper:

- **Financial Journalist** (main agent) - Researches news, writes articles, coordinates the workflow
- **Technical Analyst** (sub-agent) - Provides deep technical analysis with RSI, MACD, Bollinger Bands
- **Editor** (sub-agent) - Reviews articles for quality, approves/rejects with feedback, creates final layout

The journalist automatically delegates to specialists: launching the technical analyst for stock analysis, and submitting each article to the editor for review. Articles may be revised up to 2 times based on editor feedback before publication.

**What the system does:**
- Fetches current stock market data using Yahoo Finance
- Researches recent financial news from multiple sources
- Deep-dives into full article content to extract real insights
- Analyzes multiple sources to find hidden trends and connections
- Writes original, insightful articles (not just summaries!)
- Generates a classic newspaper-style HTML layout
- Supports incremental article generation and session continuation

## Features

- **Real-time market data**: Uses yfinance to get current prices, volumes, and trends
- **Deep article analysis**: Fetches and analyzes full article content from URLs
- **Multi-source research**: Cross-references multiple sources to find the real story
- **Original insights**: Writes analysis and implications, not just news summaries
- **Incremental mode**: Generate one article at a time with `--incremental`
- **Session continuation**: Resume previous sessions with `--session-id`
- **Classic newspaper design**: Traditional newspaper styling with modern interactivity
- **Expandable articles**: Click to read full articles without page navigation

## Quick Start

### Install Dependencies
```bash
uv pip install yfinance beautifulsoup4 requests
```

### Basic Run
```bash
# Generate newspaper edition with 3 articles (default)
uv run hugin app financial_newspaper

# Quick edition with just 2 articles
uv run hugin app financial_newspaper -- --number-of-articles 2

# Longer edition with 5 articles
uv run hugin app financial_newspaper -- --number-of-articles 5

# Custom stock symbols
uv run hugin app financial_newspaper -- --symbols AAPL MSFT NVDA AMD

# Combine options
uv run hugin app financial_newspaper -- --number-of-articles 2 --symbols AAPL MSFT --monitor
```

### Incremental Mode (NEW!)
Start a new session that writes one article at a time (instead of planning all articles upfront):

```bash
# Start a new incremental session - writes first article
uv run hugin app financial_newspaper -- --incremental

# Output shows session ID like: Session ID: abc123def456

# Resume to write the next article (--resume auto-continues)
uv run hugin app financial_newspaper -- --resume

# Or continue specific session by ID
uv run hugin app financial_newspaper -- --session-id abc123def456
```

Note: `--incremental` is only for starting **new** sessions. To continue an existing session, just use `--resume` - it automatically adds a continuation task if the agent has finished.

### Session Continuation (NEW!)
Resume from any previous session:

```bash
# Resume most recent session (no need to remember session ID!)
uv run hugin app financial_newspaper -- --resume

# Continue specific session by ID
uv run hugin app financial_newspaper -- --session-id abc123def456
```

When you resume a session:
- If the agent is still working, it continues from where it left off
- If the agent has finished, a new continuation task is automatically added
- The agent preserves its full context and memory from previous work

The newspaper will automatically open in your browser when generation is complete!

### With Live Updates (NEW!)
```bash
# Run with live updating webpage - see articles appear in real-time!
uv run hugin app financial_newspaper -- --live

# Custom port for live page
uv run hugin app financial_newspaper -- --live --live-port 9000
```

This automatically opens a live-updating newspaper page that shows:
- Real-time status updates as the agent works
- Articles appearing as soon as they're written
- Progress sidebar showing all articles
- Beautiful newspaper layout that updates live

### With Agent Monitor (NEW!)
```bash
# Run with agent monitor for debugging and observability
uv run hugin app financial_newspaper -- --monitor

# Monitor opens at http://localhost:8081/ by default
# Custom port for monitor
uv run hugin app financial_newspaper -- --monitor --monitor-port 9000
```

The agent monitor provides:
- **Real-time agent reasoning**: See the agent's thought process and decision-making
- **Tool call inspection**: Watch every tool call with parameters and results
- **Interaction flowcharts**: Visual representation of the agent's execution path
- **Artifact tracking**: See all artifacts (articles, charts) as they're created
- **Multi-agent monitoring**: Track sub-agents launched for specialized analysis
- **Error debugging**: Identify and diagnose failures immediately

Perfect for:
- Understanding how the agent works
- Debugging issues
- Learning about agentic systems
- Demonstrating AI capabilities

This automatically opens:
- The static HTML newspaper in your browser when complete
- The agent monitor at `http://localhost:8080/` to view agent interactions in real-time

## Tools Available

### fetch_stock_data
Retrieves comprehensive stock information including:
- Current price and daily changes
- Volume analysis vs historical average
- 52-week highs/lows
- Company fundamentals (PE ratio, market cap, etc.)
- Recent price trend analysis

### fetch_market_news
Aggregates recent financial news headlines and summaries from major sources, filtered by relevance.
Use this as the starting point to survey available stories.

### analyze_article (NEW!)
Deep-dives into full article content from URLs:
- Fetches complete article text (not just headlines)
- Extracts key data points (numbers, percentages, dates)
- Finds notable quotes from experts
- Provides context for deeper analysis
- Enables cross-referencing multiple sources

This tool transforms the agent from a summarizer into a real analyst!

### write_article
Creates and formats professional financial articles with:
- Engaging headlines
- Structured content with insights
- Category classification
- Related stock symbol tracking
- Word count and metadata

### update_newspaper_layout
Generates a complete newspaper front page with:
- Classic newspaper design
- Featured article prominence
- Expandable articles (click to read full content)
- Category-based article organization
- Related stock symbols display
- Collapsible metadata section

## Configuration

The agent can be customized via the task parameters:

```yaml
# In tasks/daily_edition.yaml
parameters:
  number_of_articles: 3                                       # How many articles to write
  target_symbols: ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]  # Stocks to focus on
  focus_areas: ["market_trends", "earnings", "tech_analysis"] # Content areas
  edition_date: "{{ current_date }}"                          # Publication date
```

## Generated Output

The agent creates:
- **Individual articles**: Stored in `data/newspaper_demo/` as markdown files
- **Newspaper layout**: HTML file in `data/newspaper_layouts/` with classic styling
- **Latest edition**: Always available at `data/newspaper_layouts/latest.html`
- **Auto-opens**: The finished newspaper automatically opens in your browser

### Newspaper Features
- **Expandable Articles**: Click any article preview to read the full text
- **Metadata Section**: Collapsible section showing generation time, article counts, and stats
- **Responsive Design**: Works on desktop and mobile browsers
- **Self-contained**: No external dependencies, can be shared as a single file

## Example Articles

The agent generates articles like:

```
# Tech Giants Rally as AI Sentiment Surges

**Category:** Markets
**Published:** 2024-01-15 at 14:30

Apple (AAPL) led technology stocks higher today, gaining 3.2% to close at $185.43
amid renewed optimism about artificial intelligence integration across consumer
devices. The rally came as investors rotated back into growth names...

**Related Stocks:** $AAPL, $MSFT, $GOOGL
```

## Command Line Options

```bash
usage: run.py [-h] [--number-of-articles N] [--symbols SYMBOLS [SYMBOLS ...]]
              [--max-steps MAX_STEPS] [--monitor] [--monitor-port PORT]
              [--session-id SESSION_ID] [--resume] [--incremental]

options:
  --number-of-articles N   Number of articles to write (default: 3)
  --symbols SYMBOLS        Stock symbols to cover (default: AAPL MSFT GOOGL AMZN TSLA)
  --max-steps MAX_STEPS    Maximum agent steps (default: 100)
  --monitor              Run with agent monitor for debugging
  --monitor-port PORT    Agent monitor port (default: 8081)
  --session-id SESSION_ID  Continue from existing session ID
  --resume                 Resume from most recent session (auto-continues if finished)
  --incremental            Start new session in incremental mode (one article at a time)

Examples:
  # Quick 2-article edition
  uv run hugin app financial_newspaper -- --number-of-articles 2

  # Standard 3-article edition (default)
  uv run hugin app financial_newspaper

  # Longer 5-article edition
  uv run hugin app financial_newspaper -- --number-of-articles 5

  # With monitor
  uv run hugin app financial_newspaper -- --number-of-articles 2 --monitor

  # Custom symbols
  uv run hugin app financial_newspaper -- --symbols AAPL NVDA AMD

  # Resume most recent session
  uv run hugin app financial_newspaper -- --resume
```

## Debugging and Monitoring

### Built-in Agent Monitoring
Use the `--monitor` flag to watch the agent work in real-time:

```bash
uv run hugin app financial_newspaper -- --monitor

# Monitor shows:
# - Agent decision-making process
# - Tool calls (fetch_stock_data, write_article, etc.)
# - Article generation progress
# - LLM prompts and responses
```

### Standalone Monitoring (Post-Run Analysis)
You can monitor any session after generation completes to review the complete trace:

```bash
# From the project root
uv run hugin monitor --storage-path ./storage/financial_newspaper --port 8081
```

**What You'll See:**
- Complete agent execution history and decision-making
- All tool calls with parameters and results (`technical_analysis`, `fetch_stock_data`, `write_article`)
- **Sub-agent delegation**: When the main journalist launches the technical analyst sub-agent
- LLM prompts and responses for both main and sub-agents
- Generated artifacts (articles, charts with technical indicators)
- Visual flowchart of the entire execution path

**Key Parameters:**
- `--storage-path`: Where session data is stored
- `--config-path`: Agent directory with configs/templates (required for proper loading)
- `--port`: Web interface port (default: 8081)

The monitor automatically discovers all sessions and lets you select which one to review.

## Best Practice Examples

This app demonstrates patterns from the `examples/` directory:

- **`examples/sub_agent/`** - Sub-agent delegation with `launch_agent` (technical analyst and editor sub-agents)
- **`examples/artifacts/`** - Long-term memory with `save_insight`, `query_artifacts`, and `get_artifact_content`
- **`examples/task_chaining/`** - Incremental mode task transitions between `daily_edition` and `write_next_article`
