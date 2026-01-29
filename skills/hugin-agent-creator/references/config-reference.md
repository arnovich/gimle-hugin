# Config Reference

Agent configuration files define an agent's identity, model, and capabilities.

## File Location

`configs/<config_name>.yaml`

## Schema

```yaml
name: string              # Required. Unique identifier for this config
description: string       # Required. What this agent does
system_template: string   # Required. Name of template to use (from templates/)
llm_model: string         # Required. Model to use
tools: list               # Required. List of available tools
interactive: boolean      # Optional. Default: false
options: object           # Optional. Additional config options
```

## Fields

### name
Unique identifier for this configuration. Used when launching agents.

```yaml
name: data_analyst
```

### description
Human-readable description of what this agent does.

```yaml
description: Analyzes data and generates reports
```

### system_template
Name of the system template to use. Must match a file in `templates/`.

```yaml
system_template: analyst_system
# Looks for templates/analyst_system.yaml
```

### llm_model
The LLM model to use. Options:

| Model | Description | Use Case |
|-------|-------------|----------|
| `haiku-latest` | Fast, cost-effective | Simple tasks, iteration |
| `sonnet-latest` | Balanced | Most production use cases |
| `opus-4-5` | Most capable | Complex reasoning |

```yaml
llm_model: haiku-latest
```

### tools
List of tools available to this agent. Format: `namespace.tool_name:alias`

```yaml
tools:
  - builtins.finish:finish           # Built-in tool
  - builtins.save_insight:insight    # Alias can differ from tool name
  - my_tool:my_tool                  # Custom tool from tools/
```

**Built-in tools** use `builtins.` prefix:
- `builtins.finish:finish` - Complete task
- `builtins.save_insight:save_insight` - Save artifacts
- `builtins.launch_agent:launch_agent` - Spawn sub-agents
- `builtins.list_agent_configs:list_configs` - List available configs

**Custom tools** use their name directly:
- `my_tool:my_tool` - Looks for `tools/my_tool.yaml` and `tools/my_tool.py`

### interactive
Whether this agent requires human interaction during execution.

```yaml
interactive: false  # Default, fully autonomous
interactive: true   # Allows AskHuman interactions
```

### options
Additional configuration options (currently unused in most cases).

```yaml
options: {}
```

## Examples

### Minimal Config

```yaml
name: simple_agent
description: A simple autonomous agent
system_template: simple_system
llm_model: haiku-latest
tools:
  - builtins.finish:finish
interactive: false
options: {}
```

### Agent with Custom Tools

```yaml
name: data_processor
description: Processes and transforms data
system_template: processor_system
llm_model: sonnet-latest
tools:
  - process_data:process
  - validate_data:validate
  - builtins.save_insight:save
  - builtins.finish:finish
interactive: false
options: {}
```

### Interactive Agent

```yaml
name: approval_agent
description: Agent that requires human approval for decisions
system_template: approval_system
llm_model: haiku-latest
tools:
  - request_approval:request_approval
  - builtins.finish:finish
interactive: true
options: {}
```

### Agent with Sub-Agent Capabilities

```yaml
name: orchestrator
description: Orchestrates work across specialized sub-agents
system_template: orchestrator_system
llm_model: sonnet-latest
tools:
  - builtins.launch_agent:launch
  - builtins.list_agent_configs:list_configs
  - builtins.finish:finish
interactive: false
options: {}
```

## Tool Reference Format

The tool reference format is `source:alias`:

- **source**: Where the tool comes from
  - `builtins.<name>` for built-in tools
  - `<tool_name>` for custom tools in `tools/` directory
- **alias**: How the agent refers to the tool (can be the same as source name)

```yaml
tools:
  - builtins.finish:finish           # source: builtins.finish, alias: finish
  - builtins.save_insight:save       # source: builtins.save_insight, alias: save
  - custom_tool:custom               # source: custom_tool, alias: custom
```
