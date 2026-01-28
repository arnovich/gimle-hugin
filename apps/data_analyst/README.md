# Data Analyst Agent

An AI-powered data analyst that explores datasets, identifies patterns, creates visualizations, and generates HTML reports with embedded charts.

## What It Does

The Data Analyst agent performs end-to-end data analysis:

1. **Explores your data** - Understands the structure, columns, and data types
2. **Identifies patterns** - Finds trends, correlations, and insights
3. **Creates visualizations** - Generates charts (line, bar, scatter, pie, etc.) saved as **Image artifacts**
4. **Documents findings** - Saves insights as **Text artifacts** for reference
5. **Generates a report** - Creates a professional HTML report with embedded visualizations

## Self-Reflection Pipeline

The Data Analyst uses a **three-stage self-reflection pipeline** to ensure high-quality insights:

```
analyze → evaluate → refine
```

### How It Works

1. **Initial Analysis** (`analyze` task)
   - The data analyst agent explores the data, creates visualizations, and generates an initial report
   - Uses tools: describe_data, sql_query, visualize, generate_report, etc.

2. **Evaluation** (`evaluate_analysis` task)
   - A separate **evaluator agent** critiques the analysis quality
   - Evaluates: insight depth, statistical rigor, completeness, actionability
   - Provides structured feedback: strengths, weaknesses, suggested improvements

3. **Refinement** (`refine_analysis` task)
   - The original analyst receives the evaluation feedback
   - Addresses identified weaknesses and explores missing insights
   - Generates an improved final report

### Why Self-Reflection?

Self-reflection helps the agent move beyond surface-level observations:

| Without Reflection | With Reflection |
|--------------------|-----------------|
| "Sales increased in Q1" | "Sales increased 23% in Q1, driven primarily by Widget A in the North region, correlating with the marketing campaign launch on Jan 15" |

The evaluator specifically looks for:
- **Insight Quality**: Are findings actionable or just descriptive?
- **Depth**: Does the analysis go beyond obvious observations?
- **Completeness**: Are there missed patterns or dimensions?
- **Statistical Rigor**: Are claims properly supported by data?

### Configuration

The pipeline uses two agent configurations:
- `data_analyst` - Performs analysis and refinement (sonnet-latest)
- `evaluator` - Provides critique (sonnet-latest)

Task chaining is configured via `task_sequence` in `tasks/analyze.yaml`:
```yaml
task_sequence: [evaluate_analysis, refine_analysis]
pass_result_as: initial_analysis
```

### Artifacts Created

The agent creates several types of artifacts during analysis:

| Artifact Type | Description | Where to View |
|---------------|-------------|---------------|
| **Image** | Chart visualizations (PNG) | Agent monitor, embedded in report |
| **Text** | Saved insights and findings | Agent monitor |
| **Text (HTML)** | Final analysis report | Agent monitor, opens in browser |

All artifacts are stored in `./storage/data_analyst/` and can be viewed in the agent monitor.

## Usage

### Quick Start

```bash
# Analyze the included sample data
uv run hugin app data_analyst

# Analyze your own data file
uv run hugin app data_analyst -- path/to/your/data.csv

# Analyze with a specific focus
uv run hugin app data_analyst -- mydata.csv --focus "sales trends by region"

# Add focus to the default sample data
uv run hugin app data_analyst -- --focus "monthly patterns"
```

### Command-Line Options

| Option | Description |
|--------|-------------|
| `file` | Path to data file (CSV or SQLite) to analyze |
| `--focus` | Specific focus or instruction for the analysis |
| `--max-steps` | Maximum agent steps (default: 50) |
| `--no-monitor` | Disable the agent monitor |
| `--port` | Agent monitor port (default: 8080) |
| `--log-level` | Logging level: DEBUG, INFO, WARNING, ERROR |

### Examples

```bash
# Basic analysis with monitor
uv run hugin app data_analyst -- sales_2024.csv

# Focus on specific aspects
uv run hugin app data_analyst -- revenue.csv --focus "quarterly growth trends"

# Run without monitor for scripting
uv run hugin app data_analyst -- data.csv --no-monitor --max-steps 30

# Debug mode
uv run hugin app data_analyst -- --log-level DEBUG
```

## Output

After analysis completes:

1. **HTML Report** opens automatically in your browser
   - Located at: `./storage/data_analyst/reports/latest.html`
   - Contains executive summary, findings, and embedded charts

2. **Agent Monitor** (if enabled) shows:
   - Real-time agent reasoning and tool calls
   - All artifacts (charts, insights, report)
   - Click on any artifact to view details

3. **Storage Directory** contains:
   - `./storage/data_analyst/reports/` - HTML reports
   - `./storage/data_analyst/visualizations/` - Chart images
   - `./storage/data_analyst/artifacts/` - All artifacts (JSON)

## Structure

```
apps/data_analyst/
├── configs/
│   ├── data_analyst.yaml         # Analyst agent (tools, model)
│   └── evaluator.yaml            # Evaluator agent (critique only)
├── templates/
│   ├── data_analyst_system.yaml  # Analyst role and workflow
│   └── evaluator_system.yaml     # Evaluator criteria and feedback format
├── tasks/
│   ├── analyze.yaml              # Initial analysis (chains to evaluate → refine)
│   ├── evaluate_analysis.yaml    # Evaluation task (uses evaluator config)
│   └── refine_analysis.yaml      # Refinement based on feedback
├── tools/
│   ├── describe_data.py          # Data profiling
│   ├── sql_query.py              # SQL execution
│   ├── calculate_statistics.py   # Statistical analysis
│   ├── detect_anomalies.py       # Anomaly detection
│   ├── visualize.py              # Chart creation (creates Image artifacts)
│   ├── sql_query_and_visualize.py # Combined query + viz
│   └── generate_report.py        # HTML report generation
└── fixtures/sales.csv            # Sample data
```

## Tools

### describe_data
Profile a dataset to understand its structure before analysis. Returns:
- Column types, missing values, unique counts
- Basic statistics for numeric columns
- Top values for categorical columns
- Suggestions for analysis approaches

**Use this first** to understand what you're working with.

### sql_query
Executes SQL queries on data sources. Supports:
- SQLite databases (.db, .sqlite files)
- CSV files (automatically converted to SQLite for querying)

### calculate_statistics
Perform statistical analysis on query results. Analysis types:
- **descriptive**: Mean, median, std, quartiles, skewness, kurtosis
- **correlation**: Correlation matrix with strong correlation detection
- **distribution**: Normality tests (Shapiro-Wilk), skewness interpretation
- **group_comparison**: Compare groups using t-test or ANOVA
- **percentiles**: Detailed percentile breakdown (p1 through p99)

### detect_anomalies
Find outliers using statistical methods:
- **iqr**: Interquartile Range method (default) - values beyond Q1-1.5×IQR or Q3+1.5×IQR
- **zscore**: Standard Z-score method - values with |z| > 3
- **modified_zscore**: More robust method using median and MAD - better for non-normal data

Returns anomaly counts, examples, and recommendations.

### visualize
Creates charts and saves them as **Image artifacts** viewable in the monitor.

**Supported chart types:** line, bar, scatter, histogram, pie, box

**Returns:** `artifact_id` for embedding in reports

### sql_query_and_visualize
Combines SQL query and visualization in one step using tool chaining.
Reduces LLM calls for the common query-then-visualize pattern.

### generate_report
Generates a professional HTML report with:
- Executive summary
- Key findings with descriptions
- Embedded chart images (from artifact IDs)

The report is saved as a **Text artifact** (HTML format) and opens in your browser.

## Sample Data

The included `fixtures/sales.csv` contains 62 transactions over 31 days with columns:
- date, product, category, quantity, price, revenue, region

The data includes 4 regions (North, South, East, West) enabling regional analysis.

Use your own CSV files or SQLite databases by passing the file path.

## Best Practice Examples

This app demonstrates patterns from the `examples/` directory:

- **`examples/self_reflection/`** - The three-stage analyze → evaluate → refine pipeline with `task_sequence` and `chain_config`
- **`examples/task_sequences/`** - Multi-stage pipelines with `pass_result_as` for passing results between tasks
- **`examples/tool_chaining/`** - The `sql_query_and_visualize` tool demonstrates deterministic tool chaining
- **`examples/artifacts/`** - Using artifacts for charts, insights, and reports
