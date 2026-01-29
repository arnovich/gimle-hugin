---
layout: base.njk
title: Use Claude Code to Build Agents
---

# Use Claude Code to Build Agents

Hugin includes a Claude Code plugin that helps AI coding assistants (Claude Code, Cursor, etc.) build Hugin agents with comprehensive guidance, templates, and examples.

## What is the Claude Code Plugin?

The plugin provides two skills:

| Skill | Purpose |
|-------|---------|
| `hugin-guide` | Comprehensive guide for creating agents - covers configs, tasks, templates, tools, and common patterns |
| `hugin-scaffold` | Generates starter files for a new agent based on type (minimal, tool, or pipeline) |

## Step 1: Start Claude Code with the Plugin

```bash
# From the hugin repository
claude --plugin-dir ./skills/hugin-agent-creator

# Or with an absolute path
claude --plugin-dir /path/to/gimle-hugin/skills/hugin-agent-creator
```

## Step 2: Use the Guide Skill

Ask Claude Code to help you build an agent:

```
/hugin-agent-creator:hugin-guide
```

Or simply describe what you want:

```
I want to create a Hugin agent that analyzes CSV files and generates reports.
```

Claude Code will use the plugin's reference documentation to guide you through:

1. Choosing the right pattern (minimal, tool, pipeline, etc.)
2. Creating the config file
3. Writing the task definition
4. Setting up the system template
5. Implementing custom tools if needed

## Step 3: Scaffold a New Agent

Generate starter files automatically:

```
/hugin-agent-creator:hugin-scaffold my_agent
```

### Scaffold Types

| Type | Command | What You Get |
|------|---------|--------------|
| **minimal** | `/hugin-agent-creator:hugin-scaffold my_agent` | Config + task + template |
| **tool** | `/hugin-agent-creator:hugin-scaffold my_agent tool` | Minimal + custom tool (Python + YAML) |
| **pipeline** | `/hugin-agent-creator:hugin-scaffold my_agent pipeline` | 3-stage task sequence |

### Example: Create a Tool Agent

```
/hugin-agent-creator:hugin-scaffold data_processor tool
```

This creates:

```
data_processor/
├── configs/
│   └── data_processor.yaml
├── tasks/
│   └── data_processor_task.yaml
├── templates/
│   └── data_processor_system.yaml
└── tools/
    ├── data_processor_tool.yaml
    └── data_processor_tool.py
```

## Step 4: Run Your Agent

After Claude Code creates the files:

```bash
hugin run --task data_processor_task --task-path ./data_processor
```

## What the Plugin Provides

### Reference Documentation

The plugin includes detailed reference files that Claude Code reads when you need specific information:

- **config-reference.md** - Config YAML schema, model options, tool references
- **task-reference.md** - Task YAML schema, parameters, pipelines
- **template-reference.md** - System template patterns and examples
- **tool-reference.md** - Custom tool creation (ToolResponse, AgentCall, AskHuman)
- **patterns.md** - 6 common patterns with complete examples

### Starter Templates

Copy-paste ready templates:

- `minimal-config.yaml` - Basic agent config
- `minimal-task.yaml` - Basic task definition
- `minimal-template.yaml` - Basic system template
- `tool-definition.yaml` - Tool YAML template
- `tool-implementation.py` - Tool Python template

## Example Session

Here's what a typical session looks like:

```
You: I want to build an agent that can search a knowledge base and answer questions.

Claude: I'll help you create a Hugin agent for knowledge base Q&A.
[Reads hugin-guide references]

Based on your needs, I recommend the "tool" pattern since you'll need
a custom search tool. Let me scaffold that for you...

[Creates files using hugin-scaffold]

I've created the knowledge_qa agent with:
- configs/knowledge_qa.yaml - Uses haiku-latest
- tasks/knowledge_qa_task.yaml - Takes a question parameter
- templates/knowledge_qa_system.yaml - Q&A assistant prompt
- tools/search_kb.py - Knowledge base search tool (needs your implementation)

To run it:
  hugin run --task knowledge_qa_task --task-path ./knowledge_qa

Next, you'll want to implement the actual search logic in tools/search_kb.py
```

## Troubleshooting

### Plugin Not Recognized

If `/hugin-agent-creator:hugin-guide` doesn't work:

1. Check the plugin path is correct
2. Try with debug flag: `claude --debug --plugin-dir ./skills/hugin-agent-creator`
3. Verify plugin.json exists at `.claude-plugin/plugin.json`

### Skills Not Available

Run `/help` in Claude Code to see available skills. The hugin skills should appear as:
- `hugin-agent-creator:hugin-guide`
- `hugin-agent-creator:hugin-scaffold`

## Next Steps

- [Create an Agent](/how-to/create-agent/) - Manual agent creation for full control
- [Use the Agent Creator](/how-to/use-creator/) - Interactive CLI wizard
- [Core Concepts](/concepts/) - Understanding agents, stacks, and interactions
