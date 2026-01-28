# Gimle Hugin Examples

Educational examples demonstrating specific features of the Gimle Hugin agent framework.

For more complex application showcases, see the `apps/` directory.

## Quick Start

```bash
# Run the simplest example
uv run hugin run --task hello_world --task-path examples/basic_agent

# Run multi-agent examples with --agent flag
uv run hugin run -p examples/parallel_agents -a count_evens -a count_odds

# Run an agent with the monitor dashboard
uv run hugin run --task hello_world --task-path examples/basic_agent --monitor

# Run an agent inside the interactive TUI
uv run hugin run --task hello_world --task-path examples/basic_agent -i

# Browse existing sessions in the interactive TUI (without running anything)
uv run hugin interactive --task-path examples/basic_agent

# Run the monitor dashboard on its own
uv run hugin monitor
```

We highly recommend either running the examples in interactive mode (`hugin run ... -i`) or using the monitor dashboard (`hugin monitor`). This really helps you understand the examples and the framework.

## Examples Overview

### Single Agent Examples

| Example | Description | Key Concept |
|---------|-------------|-------------|
| [basic_agent](basic_agent/) | Simplest possible agent | Agent structure basics |
| [tool_chaining](tool_chaining/) | Deterministic pipelines | `next_tool` in ToolResponse |
| [task_chaining](task_chaining/) | Task sequencing | `next_task` and `pass_result_as` |
| [task_sequences](task_sequences/) | Multi-stage pipelines | `task_sequence` with result passing |
| [plan_execute_agent](plan_execute_agent/) | Config state machine | Mode switching with different tools/prompts |
| [human_interaction](human_interaction/) | Human-in-the-loop | `AskHuman` and `HumanResponse` |

### Multi-Agent Examples

| Example | Description | Key Concept |
|---------|-------------|-------------|
| [sub_agent](sub_agent/) | Parent spawns child | `builtins.launch_agent` tool |
| [parallel_agents](parallel_agents/) | Side-by-side execution | Multiple agents via `session.step()` |
| [agent_messaging](agent_messaging/) | Direct communication | `agent.message_agent()` |
| [shared_state](shared_state/) | State sharing | `session.state` with namespaces |

### Reflection Patterns

| Example | Description | Key Concept |
|---------|-------------|-------------|
| [self_reflection](self_reflection/) | Self-critique via task chaining | `task_sequence` with `chain_config` for model switching |
| [reflexion](reflexion/) | Multi-agent critique (Reflexion pattern) | `launch_agent` to spawn critic sub-agent |

### Advanced Patterns

| Example | Description | Key Concept |
|---------|-------------|-------------|
| [artifacts](artifacts/) | Long-term memory | `save_insight`, `query_artifacts` |
| [branching](branching/) | Parallel exploration | Stack branches for multiple approaches |
| [simple_branching](simple_branching/) | Basic stack branching | `create_branch` tool, parallel execution |
| [custom_artifacts](custom_artifacts/) | Custom artifact types | `@Artifact.register`, `@ComponentRegistry.register` |

## Learning Path

### Getting Started
1. **[basic_agent](basic_agent/)** - Understand the minimal agent structure
2. **[tool_chaining](tool_chaining/)** - Learn deterministic tool pipelines
3. **[task_chaining](task_chaining/)** - Understand multi-step workflows
4. **[task_sequences](task_sequences/)** - Build multi-stage pipelines with result passing

### Interactive & Human-in-the-Loop
5. **[human_interaction](human_interaction/)** - Request human approval and feedback

### Multi-Agent Patterns
6. **[sub_agent](sub_agent/)** - How parent agents spawn children
7. **[parallel_agents](parallel_agents/)** - Running agents side-by-side
8. **[agent_messaging](agent_messaging/)** - Direct agent-to-agent communication
9. **[shared_state](shared_state/)** - Sharing data between agents

### Advanced Patterns
10. **[plan_execute_agent](plan_execute_agent/)** - Config state machines for complex workflows
11. **[artifacts](artifacts/)** - Long-term memory through persistent artifacts
12. **[branching](branching/)** - Parallel exploration of multiple approaches
13. **[simple_branching](simple_branching/)** - Basic branching with artifact output
14. **[custom_artifacts](custom_artifacts/)** - Create custom artifact types and UI components

## Running Examples

### Using the Hugin CLI
```bash
# Basic agent
uv run hugin run --task hello_world --task-path examples/basic_agent

# With parameters
uv run hugin run --task delegate --task-path examples/sub_agent --parameters '{"n": 20}'

# With more steps
uv run hugin run --task delegate --task-path examples/sub_agent --max-steps 30
```

### Running Multi-Agent Examples
Use the `--agent` flag (or `-a`) to run multiple agents:

```bash
# Multiple agents with same config
uv run hugin run -p examples/parallel_agents -a count_evens -a count_odds

# Multiple agents with different configs (TASK:CONFIG format)
uv run hugin run -p examples/agent_messaging -a start_ping:ping -a wait_pong:pong

# Multiple agents with shared namespace
uv run hugin run -p examples/shared_state -n numbers -a produce:producer -a consume:consumer
```

### Running Examples in Interactive Mode
Use the `-i` flag to run an agent inside the interactive TUI. The TUI lets you follow execution, pause/resume, and browse interactions.

```bash
# Run an agent inside the TUI
uv run hugin run --task hello_world --task-path examples/basic_agent -i
```

To browse existing sessions without running anything, use `hugin interactive`:

```bash
uv run hugin interactive --task-path examples/basic_agent
```

### Storage Path
All examples read and write from the `./storage` directory by default, as does the monitor.

You can change this behavior by passing the `--storage-path` flag to the `hugin run` command.


## Example Structure

All examples follow the same directory structure:

```
example_name/
├── README.md           # Example documentation
├── configs/            # Agent configurations (.yaml)
├── tasks/              # Task definitions (.yaml)
├── templates/          # System prompts (.yaml)
├── tools/              # Custom tools (.py + .yaml) [optional]
├── artifact_types/     # Custom artifact classes [optional]
└── ui_components/      # Custom UI components [optional]
```

## Creating Your Own Example

1. Copy `basic_agent/` as a starting point
2. Modify configs, tasks, and templates
3. Add custom tools if needed

## See Also

- **[apps/](../apps/)** - Production-like application showcases
- **[CLAUDE.md](../CLAUDE.md)** - Full development guide
- **[src/gimle/hugin/](../src/gimle/hugin/)** - Framework source code
