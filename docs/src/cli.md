---
layout: base.njk
title: CLI Reference
---

# CLI Reference

## hugin create

Interactive wizard for creating new agents.

```bash
hugin create
```

Guides you through:
- Naming your agent
- Selecting an LLM model
- Choosing tools
- Creating config, task, and template files

## hugin run

Run an agent with a task.

```bash
hugin run [options]
```

| Option | Description |
|--------|-------------|
| `-t, --task` | Task name to run |
| `-p, --task-path` | Path to agent directory |
| `-c, --config` | Config name (default: first found) |
| `--parameters` | JSON string of task parameters |
| `--max-steps` | Maximum steps (default: 100) |
| `--storage-path` | Where to save execution data |
| `--model` | Override LLM model |
| `--monitor` | Also start the web dashboard |
| `-i, --interactive` | Run the agent inside the interactive TUI |

**Examples:**

```bash
# Interactive mode - prompts for task and directory
hugin run

# Run specific task
hugin run -t my_task -p ./my_agent

# With parameters
hugin run -t analyze -p ./agent --parameters '{"input": "data.csv"}'

# Using local Ollama model
hugin run -t hello -p ./agent --model ollama:llama3.2

# Run with monitoring dashboard
hugin run -t my_task -p ./agent --monitor

# Run inside the interactive TUI
hugin run -t my_task -p ./agent -i
```

## hugin interactive

Open the interactive TUI for browsing and exploring sessions and agents without running anything.

```bash
hugin interactive [options]
```

| Option | Description |
|--------|-------------|
| `-p, --task-path` | Path to agent directory |
| `-s, --storage-path` | Path to agent storage |

**Examples:**

```bash
# Browse all sessions in default storage
hugin interactive

# Browse sessions for a specific agent directory
hugin interactive -p ./my_agent

# Browse a specific storage location
hugin interactive -s ./data/my_agent
```

## hugin monitor

Web dashboard for watching agent execution.

```bash
hugin monitor [options]
```

| Option | Description |
|--------|-------------|
| `-s, --storage-path` | Path to agent storage |
| `-p, --port` | Server port (default: 8000) |
| `--no-browser` | Don't auto-open browser |

**Example:**

```bash
# Start monitor for specific storage
hugin monitor -s ./data/my_agent

# Custom port
hugin monitor -s ./storage -p 8080
```

Features:
- Real-time interaction flow visualization
- Tool call inspection
- Agent state browsing
- Session/agent selection

## hugin rate

Rate an artifact as a human reviewer.

```bash
hugin rate [options]
```

| Option | Description |
|--------|-------------|
| `-s, --storage-path` | Path to agent storage |
| `--artifact-id` | UUID of the artifact to rate |
| `--rating` | Rating from 1 (poor) to 5 (excellent) |
| `--comment` | Optional comment explaining the rating |

When run without flags, enters interactive mode: lists available artifacts, prompts for selection, rating, and optional comment. Provide all flags for non-interactive/scripted usage.

**Examples:**

```bash
# Interactive mode - browse and rate artifacts
hugin rate -s ./storage

# Non-interactive mode
hugin rate -s ./storage --artifact-id abc123 --rating 4 --comment "Very useful"
```

## Interactive TUI

Terminal UI for browsing and managing agents. Access it via `hugin interactive` (browse only) or `hugin run -i` (run agent inside TUI).

```bash
# Browse existing sessions
hugin interactive --storage-path ./storage

# Run an agent inside the TUI
hugin run -t my_task -p ./my_agent -i
```

| Key | Action |
|-----|--------|
| `↑/↓` or `j/k` | Navigate |
| `Enter` | Select / Drill down |
| `q` | Back / Quit |
| `r` | Refresh |
| `N` | New agent (on sessions screen) |
| `?` | Help |

Screens:
- **Sessions** - List all saved sessions
- **Agents** - Agents within a session
- **Interactions** - Agent's execution stack
- **Detail** - Full interaction data

## hugin apps

List available example apps.

```bash
hugin apps
```

## hugin app

Run a specific app.

```bash
hugin app <name> [args]
```

**Example:**

```bash
hugin app data_analyst
hugin app rap_machine --random-agents
```

## hugin install-models

Install recommended Ollama models.

```bash
hugin install-models
```
