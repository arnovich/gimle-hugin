# Config Reference

Agent configuration files define an agent's identity, model, and capabilities.

## File Location

`configs/<config_name>.yaml`

## Schema

```yaml
name: string                    # Required. Unique identifier for this config
description: string             # Required. What this agent does
system_template: string         # Required. Name of template to use (from templates/)
llm_model: string               # Required. Model to use
tools: list                     # Required. List of available tools
interactive: boolean            # Optional. Default: false
enable_builtin_agents: boolean  # Optional. Default: true
state_namespaces: list          # Optional. Default: ["common"]
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
- `builtins.ask_user:ask_user` - Ask user a question (requires interactive: true)
- `builtins.save_insight:save_insight` - Save artifacts
- `builtins.launch_agent:launch_agent` - Spawn sub-agents
- `builtins.list_agents:list_agents` - List available agents
- `builtins.read_file:read_file` - Read file contents (safe, read-only)
- `builtins.list_files:list_files` - List directory contents
- `builtins.search_files:search_files` - Search for patterns in files

**Custom tools** use their name directly:
- `my_tool:my_tool` - Looks for `tools/my_tool.yaml` and `tools/my_tool.py`

### interactive
Whether this agent requires human interaction during execution.

```yaml
interactive: false  # Default, fully autonomous
interactive: true   # Allows AskHuman interactions
```

### enable_builtin_agents
Whether this agent can see and launch builtin agents like `agent_builder`.

```yaml
enable_builtin_agents: true   # Default, agent can use agent_builder
enable_builtin_agents: false  # Agent cannot see or launch builtin agents
```

When `false`:
- `list_agents` won't show builtin agents
- `launch_agent` will reject attempts to launch builtin agents

Use this to restrict agents from creating new agents dynamically.

### state_namespaces
List of session state namespaces this agent can access. Used for multi-agent
state sharing with access control.

```yaml
state_namespaces:
  - common      # Default, always included
  - my_namespace
```

All agents can access the "common" namespace by default. See the shared_state
example for usage patterns.

## Examples

### Minimal Config

```yaml
name: simple_agent
description: A simple autonomous agent
system_template: simple_system
llm_model: haiku-latest
tools:
  - builtins.finish:finish
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
```

### Interactive Agent (Human-in-the-Loop)

```yaml
name: approval_agent
description: Agent that requires human approval for decisions
system_template: approval_system
llm_model: haiku-latest
tools:
  - request_approval:request_approval
  - builtins.finish:finish
interactive: true  # Required for AskHuman
```

### Agent with Sub-Agent Capabilities

```yaml
name: orchestrator
description: Orchestrates work across specialized sub-agents
system_template: orchestrator_system
llm_model: sonnet-latest
tools:
  - builtins.launch_agent:launch
  - builtins.list_agents:list_agents
  - builtins.finish:finish
```

### Restricted Agent (No Builtin Agents)

```yaml
name: restricted_worker
description: Worker agent that cannot create new agents
system_template: worker_system
llm_model: haiku-latest
tools:
  - builtins.finish:finish
  - builtins.save_insight:save
enable_builtin_agents: false
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
