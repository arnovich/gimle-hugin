# Hugin Agent Creator Plugin

A Claude Code plugin that helps coding agents (Claude Code, Cursor) build Hugin AI agents with comprehensive guidance, templates, and examples.

## Installation

Add this plugin to your Claude Code session:

```bash
claude --plugin-dir ./skills/hugin-agent-creator
```

Or reference it from your project's CLAUDE.md:

```markdown
Use the hugin-agent-creator plugin at ./skills/hugin-agent-creator for building Hugin agents.
```

## Skills

### hugin-guide

Comprehensive guide for creating Hugin AI agents.

```
/hugin-agent-creator:hugin-guide
```

Provides:
- Quick start (minimal 3-file agent)
- Directory structure explanation
- Core concepts (config, task, template, tool)
- Decision tree for choosing patterns
- Links to detailed references

### hugin-scaffold

Generate starter files for a new Hugin agent.

```
/hugin-agent-creator:hugin-scaffold my_agent
/hugin-agent-creator:hugin-scaffold data_processor tool
/hugin-agent-creator:hugin-scaffold report_gen pipeline
```

Types:
- `minimal` - Config + task + template (default)
- `tool` - Minimal + sample custom tool
- `pipeline` - 3-stage task sequence

## Directory Structure

```
hugin-agent-creator/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest
├── skills/
│   ├── hugin-guide/
│   │   └── SKILL.md         # Main guide skill
│   └── hugin-scaffold/
│       └── SKILL.md         # Scaffolding skill
├── references/
│   ├── config-reference.md  # Config YAML schema
│   ├── task-reference.md    # Task YAML schema
│   ├── template-reference.md # System template patterns
│   ├── tool-reference.md    # Custom tool creation
│   └── patterns.md          # Common agent patterns
├── templates/
│   ├── minimal-config.yaml  # Starter config
│   ├── minimal-task.yaml    # Starter task
│   ├── minimal-template.yaml # Starter system template
│   ├── tool-definition.yaml # Tool YAML template
│   └── tool-implementation.py # Tool Python template
└── README.md
```

## Reference Documentation

Detailed schemas and examples in `references/`:

| File | Content |
|------|---------|
| `config-reference.md` | Agent configuration schema, fields, tool reference syntax |
| `task-reference.md` | Task definition schema, parameters, pipelines |
| `template-reference.md` | System template patterns and examples |
| `tool-reference.md` | Custom tool creation (ToolResponse, AgentCall, AskHuman) |
| `patterns.md` | 6 common patterns with full examples |

## Quick Start

Create a minimal agent:

```bash
# Create directory
mkdir -p my_agent/{configs,tasks,templates}

# Copy templates
cp templates/minimal-config.yaml my_agent/configs/my_agent.yaml
cp templates/minimal-task.yaml my_agent/tasks/my_task.yaml
cp templates/minimal-template.yaml my_agent/templates/my_system.yaml

# Run
uv run hugin run --task my_task --task-path ./my_agent
```

## Links

- [Hugin Documentation](https://gimle-hugin.readthedocs.io/)
- [Hugin Repository](https://github.com/gimlelabs/gimle-hugin)
