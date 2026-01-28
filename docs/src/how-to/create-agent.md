---
layout: base.njk
title: Create an Agent
---

# Create an Agent

This guide walks through creating a Hugin agent from scratch. You'll learn what each file does and why it's needed.

## Prerequisites

- Hugin installed (`pip install gimle-hugin`)
- An LLM provider configured (API key or local Ollama)

## Step 1: Create the Directory Structure

Every Hugin agent lives in a directory with up to four subdirectories:

```bash
mkdir -p my_agent/{configs,tasks,templates,tools}
```

```
my_agent/
├── configs/     # Agent configurations (behavior, model, tools)
├── tasks/       # Task definitions (what the agent should do)
├── templates/   # System prompts (agent personality/instructions)
└── tools/       # Custom tools (optional)
```

| Directory | Purpose |
|-----------|---------|
| `configs/` | Defines *how* an agent behaves: which model, system prompt, and tools to use |
| `tasks/` | Defines *what* an agent should do: the initial prompt and any parameters |
| `templates/` | Defines the agent's personality and instructions via Jinja2 templates |
| `tools/` | Custom tools the agent can call (Python + YAML pairs) |

## Step 2: Create the System Template

The system template defines your agent's personality and instructions. Create `templates/assistant.yaml`:

```yaml
name: assistant
template: |
  You are a helpful assistant.

  Your goal is to complete the user's task thoroughly and accurately.
  When you have finished, use the finish tool to indicate completion.
```

**Why this matters:** The system template is rendered fresh with each LLM call, so you can include dynamic content using Jinja2 syntax. This is where you define the agent's core behavior.

## Step 3: Create the Config

The config ties everything together. Create `configs/assistant.yaml`:

```yaml
name: assistant
description: A helpful assistant agent
system_template: assistant
llm_model: haiku-latest
tools:
  - builtins.finish:finish
```

| Field | Description |
|-------|-------------|
| `name` | Unique identifier for this config |
| `description` | Human-readable description |
| `system_template` | Name of the template to use (from `templates/`) |
| `llm_model` | Which LLM to use (e.g., `haiku-latest`, `sonnet-latest`, `ollama:llama3.2`) |
| `tools` | List of tools the agent can call |

**Tool format:** `module:tool_name` where `module` is either `builtins.{category}` for built-in tools or a local file name.

## Step 4: Create the Task

The task defines what the agent should accomplish. Create `tasks/hello.yaml`:

```yaml
name: hello
description: A simple greeting task
prompt: |
  Hello! Please introduce yourself and explain what you can help with.
```

For tasks with parameters, use structured definitions:

```yaml
name: analyze
description: Analyze a topic
parameters:
  topic:
    type: string
    description: The topic to analyze
    required: true
  depth:
    type: string
    description: How deep to go (brief, detailed, comprehensive)
    required: false
    default: detailed
prompt: |
  Please analyze the following topic: {{ topic }}

  Depth of analysis: {{ depth }}
```

## Step 5: Run the Agent

```bash
hugin run --task hello --task-path my_agent
```

You should see the agent introduce itself and then call the `finish` tool.

**With parameters:**
```bash
hugin run --task analyze --task-path my_agent --parameters '{"topic": "climate change"}'
```

## Step 6: Add a Custom Tool (Optional)

Tools let agents interact with the world. Each tool needs two files:

**tools/search.py** (implementation):
```python
def search(stack, query: str) -> str:
    """Search for information about a topic."""
    # In a real tool, you'd call an API or database
    return f"Results for '{query}': [simulated search results]"
```

**tools/search.yaml** (definition):
```yaml
name: search
description: Search for information about a topic
parameters:
  - name: query
    type: string
    description: The search query
    required: true
implementation: search:search
```

**Wire it into your config:**
```yaml
tools:
  - builtins.finish:finish
  - search:search
```

Now the agent can call `search` during execution.

### Tool Tips

- The `stack` parameter is auto-injected and gives access to agent context
- Access environment variables via `stack.agent.environment.env_vars`
- Return a string for simple results
- For complex results, return a `ToolResponse` object
- To spawn a child agent, return an `AgentCall` (see [Tools concept](/concepts/tools/))

## Complete Example

Here's the full directory structure:

```
my_agent/
├── configs/
│   └── assistant.yaml
├── tasks/
│   └── hello.yaml
├── templates/
│   └── assistant.yaml
└── tools/
    ├── search.py
    └── search.yaml
```

## Next Steps

- [Use the Monitor](/how-to/use-monitor/) - Visualize your agent's execution
- [Core Concepts](/concepts/) - Understand the architecture in depth
- [Tools](/concepts/tools/) - Learn more about tool development
- [Examples](/examples/) - See more complex agent patterns
