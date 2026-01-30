---
name: hugin-guide
description: Comprehensive guide for creating Hugin AI agents. Use when building agents, working with configs, tasks, templates, or tools.
---

# Hugin Agent Creation Guide

This skill helps you create Hugin AI agents. It provides an overview and directs you to detailed reference documentation.

## How to Use This Skill

1. **Quick Start**: Follow the minimal agent example below
2. **Detailed Info**: Read the appropriate reference file for schemas and examples
3. **Scaffolding**: Use `/hugin-agent-creator:hugin-scaffold` to generate starter files

## Reference Files (Read These for Details)

When the user needs detailed information about a specific topic, **read the appropriate reference file** from this plugin directory:

| Topic | Reference File | When to Read |
|-------|---------------|--------------|
| Config files | `references/config-reference.md` | User asks about config options, models, tools |
| Task files | `references/task-reference.md` | User asks about tasks, parameters, prompts, pipelines |
| System templates | `references/template-reference.md` | User asks about system prompts, agent personality |
| Custom tools | `references/tool-reference.md` | User wants to create tools, use ToolResponse/AgentCall/AskHuman |
| Agent patterns | `references/patterns.md` | User needs architecture guidance, pattern examples |

**Important**: These reference files contain detailed schemas, field descriptions, and complete examples. Read them when answering specific questions.

## Starter Templates

When the user wants to create files, **read and adapt the starter templates** from this plugin:

| Template | File | Use For |
|----------|------|---------|
| Config | `templates/minimal-config.yaml` | Creating agent configs |
| Task | `templates/minimal-task.yaml` | Creating task definitions |
| System template | `templates/minimal-template.yaml` | Creating system prompts |
| Tool definition | `templates/tool-definition.yaml` | Creating tool YAML |
| Tool implementation | `templates/tool-implementation.py` | Creating tool Python code |

## Quick Start: Minimal Agent (3 Files)

A working agent needs just 3 files:

```
my_agent/
├── configs/my_agent.yaml      # Agent configuration
├── tasks/my_task.yaml         # Task definition
└── templates/my_system.yaml   # System prompt template
```

### Run Command

```bash
uv run hugin run --task my_task --task-path ./my_agent
```

## Core Concepts (Overview)

### Config
Defines an agent's identity: model, system template, available tools.
- **Read `references/config-reference.md` for full schema**

### Task
Defines what an agent should do: prompt, parameters, optional pipeline.
- **Read `references/task-reference.md` for full schema**

### Template
System prompt that sets agent behavior and personality.
- **Read `references/template-reference.md` for examples**

### Tool
Extends agent capabilities with Python code.
- **Read `references/tool-reference.md` for implementation guide**

## Built-in Tools

Reference with `builtins.<tool>:<alias>`:

| Tool | Description |
|------|-------------|
| `builtins.finish:finish` | Complete task with success/failure |
| `builtins.ask_user:ask_user` | Ask user a question (requires interactive: true) |
| `builtins.save_insight:save_insight` | Save findings as artifacts |
| `builtins.launch_agent:launch_agent` | Spawn sub-agents |
| `builtins.list_agents:list_agents` | List available agents |
| `builtins.read_file:read_file` | Read file contents (safe, read-only) |
| `builtins.list_files:list_files` | List directory contents with glob patterns |
| `builtins.search_files:search_files` | Search files for patterns (grep-like) |

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

**For detailed pattern examples, read `references/patterns.md`**

## Common Patterns (Summary)

1. **Minimal Agent** - Config + task + template, built-in tools only
2. **Tool Agent** - Custom tools for specific capabilities
3. **Pipeline Agent** - Multi-stage processing with result passing
4. **Human-in-the-Loop** - Requires human approval during execution
5. **Agent Delegation** - Spawns specialized sub-agents
6. **Multi-Agent** - Multiple agents sharing state

## Workflow for Helping Users

1. **Understand what they want to build** - Ask clarifying questions if needed
2. **Recommend a pattern** - Use the decision tree above
3. **Read the relevant reference** - Get detailed schema information
4. **Read the starter template** - Use as base for their files
5. **Customize for their use case** - Replace placeholders, add their logic
6. **Provide the run command** - Show how to test the agent
