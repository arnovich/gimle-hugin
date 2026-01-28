# Gimle Hugin Apps

Applications showcasing the capabilities of the Gimle Hugin agent framework.

These apps are more complex than the educational examples in `examples/` and serve as inspiration for what you can build with Hugin.

## Getting started

From the repo root:

```bash
uv sync --all-extras
```

## Listing apps

```bash
uv run hugin apps
```

## Running apps

The easiest way to run an app is to use the `hugin app` command:

```
hugin app <name>
```

This will run `apps/<name>/run.py` when present, otherwise it will run the app as a standard agent directory.

Important: to pass app-specific flags to `hugin app`, put them after `--`:

```bash
uv run hugin app rap_machine -- --random-agents --monitor
```

## Apps

### data_analyst

A data analysis agent that can query data sources, create visualizations, and save insights.

The app runs as a standard agent, opening the monitor UI automatically, where you can view the outputs as artifacts.

```bash
# Run it on the demo data
uv run hugin app data_analyst

# Override the input data source
uv run hugin app data_analyst --parameters '{"data_source":"apps/data_analyst/data/sales.csv"}'

# Disable the monitor (enabled by default)
uv run hugin app data_analyst -- --no-monitor
```

### financial_newspaper

Agentic financial journalist that generates a newspaper-style HTML edition using live market data.

```bash
# Full edition with 3 articles (default)
uv run hugin app financial_newspaper

# Quick edition with just 2 articles
uv run hugin app financial_newspaper -- --number-of-articles 2

# Longer edition with 5 articles
uv run hugin app financial_newspaper -- --number-of-articles 5

# Custom symbols
uv run hugin app financial_newspaper -- --symbols AAPL MSFT NVDA

# With monitor for debugging
uv run hugin app financial_newspaper -- --number-of-articles 2 --monitor

# Resume the most recent session
uv run hugin app financial_newspaper -- --resume
```

Outputs are written under `storage/financial_newspaper/layouts/` (see `latest.html`).

### rap_machine

Turn-based multi-agent rap battle arena that generates a shareable HTML battle report.

```bash
# Random battle (judge picks topic unless you set one)
uv run hugin app rap_machine -- --random-agents

# Pick a topic, set rounds, and watch in the monitor
uv run hugin app rap_machine -- --topic "AI vs Humans" --rounds 8 --monitor --port 8080

# Custom rapper names
uv run hugin app rap_machine -- --rapper1-name "DJ Byte" --rapper2-name "Lil Loop"

# Override models
uv run hugin app rap_machine -- --random-agents --model sonnet-latest
```

Reports are written under `data/rap_battles/reports/` (see `latest.html`).

### the_hugins

Autonomous 2D world simulation with a live web visualization (and optional agent monitor).

```bash
# Starts the world visualization (auto-opens browser)
uv run hugin app the_hugins

# With agent monitor + custom ports
uv run hugin app the_hugins -- --monitor --world-port 8000 --monitor-port 8001
```

## Creating your own app

To create a new agent interactively, use the built-in wizard:

```bash
uv run hugin create
```

Apps follow the same structure as examples, optionally with a custom `run.py`:

```
my_app/
├── configs/          # Agent configurations
├── tasks/            # Task definitions
├── templates/        # System prompts
├── tools/            # Custom tools
├── run.py            # Custom runner (optional)
├── data/             # Data files (optional)
└── README.md         # Documentation
```

For simpler examples demonstrating specific features, see the `examples/` directory.
