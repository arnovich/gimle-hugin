---
layout: base.njk
title: Getting Started
---

# Getting Started

This guide will help you set up Hugin and create your first agent.

## Installation

### 1. Setup an LLM Provider

You can use cloud APIs or local models:

**Cloud APIs** (Anthropic or OpenAI):
```bash
export ANTHROPIC_API_KEY="your-key"
# or
export OPENAI_API_KEY="your-key"
```

**Local with Ollama**:
```bash
# Install Ollama from https://ollama.com/download
ollama pull llama3.2
```

### 2. Install Hugin

```bash
pip install gimle-hugin
```

Or with uv:
```bash
uv add gimle-hugin
```

Or install latest from source:
```bash
pip install git+https://github.com/gimlelabs/gimle-hugin.git
```

### 3. Create Your First Agent

The quickest way to get started is with the agent builder:

```bash
hugin create
```

This interactive wizard will guide you through creating a simple agent.

## Manual Setup

If you prefer to set things up manually, create a directory structure:

```
my_agent/
├── configs/
│   └── my_config.yaml
├── tasks/
│   └── my_task.yaml
└── templates/
    └── my_system.yaml
```

### Configuration

**configs/my_config.yaml**:
```yaml
name: my_agent
description: My first agent
system_template: my_system
llm_model: haiku-latest
tools:
  - builtins.finish:finish
```

### Task Definition

**tasks/my_task.yaml**:
```yaml
name: my_task
description: My first task
prompt: "Hello! Please introduce yourself and explain what you can do."
```

### System Template

**templates/my_system.yaml**:
```yaml
name: my_system
template: |
  You are a helpful assistant.
  Complete the task and use the finish tool when done.
```

### Run the Agent

```bash
hugin run --task my_task --task-path my_agent
```

## Adding Custom Tools

Create a tool with a Python implementation and YAML definition:

**tools/greet.py**:
```python
def greet(stack, name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"
```

**tools/greet.yaml**:
```yaml
name: greet
description: Greet someone by name
parameters:
  - name: name
    type: string
    description: The name to greet
    required: true
implementation: greet:greet
```

Add to your config:
```yaml
tools:
  - builtins.finish:finish
  - greet:greet
```

## Monitoring Your Agent

Watch your agent's execution in real-time:

```bash
# Terminal 1: Run agent with storage
hugin run --task my_task --task-path my_agent --storage-path ./data/my_agent

# Terminal 2: Start the monitor
# The monitor is a web dashboard that shows the agent's interaction flow, tool calls, and decision tree.
hugin monitor --storage-path ./data/my_agent

# Or run the agent and monitor in one command
hugin run --task my_task --task-path my_agent --monitor

# Or run the agent inside the interactive TUI
# The TUI lets you follow the agent's execution, pause/resume, and browse interactions.
hugin run -i --task my_task --task-path my_agent

# Or browse existing sessions without running anything
hugin interactive --storage-path ./data/my_agent
```

## Next Steps

- [Core Concepts](/concepts/) - Understand agents, stacks, and interactions
- [CLI](/cli/) - Learn the command line interfaces
- [Examples](/examples/) - Learn from working examples
- [API Reference](/api/) - Detailed API documentation
