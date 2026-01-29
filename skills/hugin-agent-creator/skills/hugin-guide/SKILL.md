---
name: hugin-guide
description: Comprehensive guide for creating Hugin AI agents. Use when building agents, working with configs, tasks, templates, or tools.
---

# Hugin Agent Creation Guide

This guide helps you create Hugin AI agents. For detailed schema references, see the `references/` directory in this plugin.

## Quick Start: Minimal Agent (3 Files)

A working agent needs just 3 files:

```
my_agent/
├── configs/my_agent.yaml      # Agent configuration
├── tasks/my_task.yaml         # Task definition
├── templates/my_system.yaml   # System prompt template
```

### 1. Config (`configs/my_agent.yaml`)

```yaml
name: my_agent
description: What this agent does
system_template: my_system
llm_model: haiku-latest
tools:
  - builtins.finish:finish
interactive: false
options: {}
```

### 2. Task (`tasks/my_task.yaml`)

```yaml
name: my_task
description: What this task accomplishes
parameters:
  input:
    type: string
    description: The input to process
    required: false
    default: "default value"
prompt: |
  Process this input: {{ input.value }}

  When complete, use the finish tool.
```

### 3. Template (`templates/my_system.yaml`)

```yaml
name: my_system
template: |
  You are a helpful AI assistant.

  When you have completed the task, use the finish tool to indicate completion.
```

### Run It

```bash
uv run hugin run --task my_task --task-path ./my_agent
```

## Directory Structure

```
agent_directory/
├── configs/           # Agent configurations (.yaml)
├── tasks/            # Task definitions (.yaml)
├── templates/        # Jinja2 system templates (.yaml)
└── tools/           # Custom tools (.py + .yaml)
```

## Core Concepts

### Config
Defines an agent's identity: model, system template, available tools. One config can run many tasks.

**Key fields:**
- `name`: Unique identifier
- `system_template`: References template by name
- `llm_model`: `haiku-latest`, `sonnet-latest`, or `opus-4-5`
- `tools`: List of available tools (format: `namespace.tool:alias`)
- `interactive`: `true` for human-in-the-loop agents

### Task
Defines what an agent should do. Contains the prompt and parameters.

**Key fields:**
- `name`: Unique identifier
- `prompt`: Jinja2 template with `{{ param.value }}` syntax
- `parameters`: Typed inputs with defaults
- `task_sequence`: Optional list of follow-up tasks
- `pass_result_as`: Parameter name for passing result to next task

### Template
System prompt that sets agent behavior and personality.

**Key fields:**
- `name`: Referenced by configs/tasks
- `template`: The system prompt content

### Tool
Extends agent capabilities. Consists of YAML definition + Python implementation.

## Built-in Tools

Reference with `builtins.<tool>:<alias>`:

| Tool | Description |
|------|-------------|
| `builtins.finish:finish` | Complete task with success/failure |
| `builtins.save_insight:save_insight` | Save findings as artifacts |
| `builtins.launch_agent:launch_agent` | Spawn sub-agents |
| `builtins.list_agent_configs:list_configs` | List available configs |

## Decision Tree: Which Pattern?

```
Do you need custom tools?
├── No → Minimal pattern
└── Yes → Tool pattern
    └── Does the tool spawn another agent?
        ├── No → Simple tool
        └── Yes → AgentCall pattern

Do you need human input during execution?
├── No → Set interactive: false
└── Yes → AskHuman pattern (interactive: true)

Do you need multiple processing stages?
├── No → Single task
└── Yes → Task sequence pattern (task_sequence + pass_result_as)

Do you need multiple agents running together?
└── Yes → Multi-agent pattern (shared state via env_vars)
```

## Common Patterns

### 1. Minimal Agent
Just config + task + template. Uses only built-in tools.

### 2. Tool Agent
Adds custom tools for specific capabilities. See `references/tool-reference.md`.

### 3. Pipeline Agent
Multi-stage processing with result passing between tasks:

```yaml
# First task
task_sequence:
  - stage_2
  - stage_3
pass_result_as: stage_1_result
```

### 4. Human-in-the-Loop
Set `interactive: true` in config, use `AskHuman` in tools.

### 5. Agent Delegation
Use `builtins.launch_agent` or return `AgentCall` from custom tool.

### 6. Multi-Agent
Multiple agents sharing state via `environment.env_vars`.

## Reference Documentation

For detailed schemas and examples:
- `references/config-reference.md` - Config YAML schema
- `references/task-reference.md` - Task YAML schema
- `references/template-reference.md` - System template patterns
- `references/tool-reference.md` - Custom tool creation
- `references/patterns.md` - Detailed pattern examples

## Starter Templates

Copy-paste templates in `templates/` directory:
- `minimal-config.yaml`
- `minimal-task.yaml`
- `minimal-template.yaml`
- `tool-definition.yaml`
- `tool-implementation.py`
