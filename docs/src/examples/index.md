---
layout: base.njk
title: Examples
---

# Examples

Learn Hugin through working examples. Each example demonstrates specific features and patterns.

## Getting Started

| Example | Description | Key Concepts |
|---------|-------------|--------------|
| [basic_agent](https://github.com/gimlelabs/gimle-hugin/tree/main/examples/basic_agent) | Simplest agent setup | Config, Task, Templates, Tools |

Start here to understand the basic structure.

## Core Patterns

| Example | Description | Key Concepts |
|---------|-------------|--------------|
| [tool_chaining](https://github.com/gimlelabs/gimle-hugin/tree/main/examples/tool_chaining) | Deterministic tool pipelines | `next_tool` parameter |
| [task_chaining](https://github.com/gimlelabs/gimle-hugin/tree/main/examples/task_chaining) | Sequential task execution | `next_task` parameter |
| [task_sequences](https://github.com/gimlelabs/gimle-hugin/tree/main/examples/task_sequences) | Multi-stage pipelines | `task_sequence`, `pass_result_as` |
| [plan_execute_agent](https://github.com/gimlelabs/gimle-hugin/tree/main/examples/plan_execute_agent) | Config-based state machines | State transitions, mode switching |
| [human_interaction](https://github.com/gimlelabs/gimle-hugin/tree/main/examples/human_interaction) | Human-in-the-loop | `AskHuman`, approval workflows |

## Advanced Features

| Example | Description | Key Concepts |
|---------|-------------|--------------|
| [branching](https://github.com/gimlelabs/gimle-hugin/tree/main/examples/branching) | Parallel exploration | Stack branching, isolation |
| [simple_branching](https://github.com/gimlelabs/gimle-hugin/tree/main/examples/simple_branching) | Basic stack branching | `create_branch` tool, artifact output |
| [artifacts](https://github.com/gimlelabs/gimle-hugin/tree/main/examples/artifacts) | Long-term memory | `save_insight`, `query_artifacts` |
| [custom_artifacts](https://github.com/gimlelabs/gimle-hugin/tree/main/examples/custom_artifacts) | Custom artifact types | `@Artifact.register`, UI components |

## Multi-Agent

| Example | Description | Key Concepts |
|---------|-------------|--------------|
| [sub_agent](https://github.com/gimlelabs/gimle-hugin/tree/main/examples/sub_agent) | Parent-child hierarchy | Agent delegation |
| [parallel_agents](https://github.com/gimlelabs/gimle-hugin/tree/main/examples/parallel_agents) | Concurrent execution | Session management |
| [agent_messaging](https://github.com/gimlelabs/gimle-hugin/tree/main/examples/agent_messaging) | Agent-to-agent communication | Message passing |
| [shared_state](https://github.com/gimlelabs/gimle-hugin/tree/main/examples/shared_state) | Shared data with access control | Namespaces, permissions |

## Running Examples

```bash
# Clone the repository
git clone https://github.com/gimlelabs/gimle-hugin.git
cd gimle-hugin

# Install dependencies
uv sync --all-extras

# Run an example
uv run hugin run --task hello_world --task-path examples/basic_agent

# With parameters
uv run hugin run --task hello_world --task-path examples/basic_agent \
  --parameters '{"questions": "What is AI?"}'

# With monitoring
uv run hugin run --task hello_world --task-path examples/basic_agent \
  --storage-path ./data/demo

# In another terminal
uv run hugin monitor --storage-path ./data/demo
```

## Demo Apps

More complex applications in the `apps/` directory:

| App | Description |
|-----|-------------|
| [data_analyst](https://github.com/gimlelabs/gimle-hugin/tree/main/apps/data_analyst) | SQL queries, data transformation, analysis |
| [financial_newspaper](https://github.com/gimlelabs/gimle-hugin/tree/main/apps/financial_newspaper) | Multi-agent financial journalism workflow |
| [rap_machine](https://github.com/gimlelabs/gimle-hugin/tree/main/apps/rap_machine) | Multi-agent rap battles (fun demo) |
| [the_hugins](https://github.com/gimlelabs/gimle-hugin/tree/main/apps/the_hugins) | Autonomous 2D world simulation |

Check them out in the repo, run them, see how they work and have fun extending them!

## Running Apps

Apps can be run either via the dedicated app runner (`hugin app`) or directly with `hugin run` when the app is a standard agent directory.

```bash
# List available apps
uv run hugin apps

# Recommended: use the app runner (uses apps/<name>/run.py when present)
# Note: pass app-specific flags after `--`
uv run hugin app data_analyst

uv run hugin app financial_newspaper -- --symbols AAPL MSFT --incremental --monitor

uv run hugin app rap_machine -- --random-agents --monitor

uv run hugin app the_hugins -- --monitor

```

See the [apps README](https://github.com/gimlelabs/gimle-hugin/tree/main/apps) for details on running these.
