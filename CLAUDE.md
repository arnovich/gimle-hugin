# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Git Workflow

**Never commit directly to `main`.** Always work on a feature branch:
- Create a new branch for any change (`git checkout -b descriptive_branch_name`)
- Use snake_case for branch names
- Commit to the branch, then merge via PR or as instructed
- **Do NOT add Co-Authored-By lines** - commit messages should not include Claude as author

## Development Commands

### Running Agents
```bash
# Basic agent run
uv run hugin run --task hello_world --task-path examples/basic_agent

# With custom parameters
uv run hugin run --task hello_world --task-path examples/basic_agent --parameters '{"questions": "What is AI?"}'

# With more steps and debug logging
uv run hugin run --task analyze --task-path apps/data_analyst --max-steps 50 --log-level DEBUG

# Run multiple agents (multi-agent examples)
uv run hugin run -p examples/parallel_agents -a count_evens -a count_odds

# Multiple agents with different configs (TASK:CONFIG format)
uv run hugin run -p examples/agent_messaging -a start_ping:ping -a wait_pong:pong

# Multiple agents with shared namespace
uv run hugin run -p examples/shared_state -n numbers -a produce:producer -a consume:consumer

# Run apps
uv run hugin app rap_machine -- --random-agents --model haiku-latest
uv run hugin app the_hugins
uv run hugin app financial_newspaper

# Run an agent inside the interactive TUI
uv run hugin run --task hello_world --task-path examples/basic_agent -i

# List available apps
uv run hugin apps
```

### Testing
```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov

# Run specific test
uv run pytest tests/test_agent.py

# Run with specific markers
uv run pytest -m unit
uv run pytest -m integration
```

### Code Quality
```bash
# Run pre-commit checks (includes black, isort, flake8, mypy)
uv run pre-commit run --all-files

# Individual tools
uv run black .
uv run isort .
uv run flake8 .
uv run mypy .
```

### Monitoring & Debugging
```bash
# Monitor any agent's execution flow by pointing to its storage
# Browser opens automatically by default
uv run hugin monitor --storage-path ./storage/financial_newspaper --port 8001
uv run hugin monitor --storage-path ./storage/worlds --port 8002

# Disable automatic browser opening
uv run hugin monitor --storage-path ./storage/worlds --port 8002 --no-browser

# Provides visual flowcharts, interaction details, tool results, and debugging info

# Interactive TUI for browsing sessions and agents
uv run hugin interactive --storage-path ./storage/worlds
uv run hugin interactive --task-path examples/basic_agent
```

## Architecture Overview

Hugin is an agent framework built around a state machine architecture with the following key components:

### Core Components

**Agent**: The main entity that executes tasks. Contains a `Stack` of interactions and references to `Config` and `Session`.
- Location: `src/gimle/hugin/agent/agent.py`
- Created from tasks using `Agent.create_from_task()`

**Session**: Manages multiple agents and provides shared environment access
- Location: `src/gimle/hugin/agent/session.py`
- Contains environment and manages agent lifecycles

**Environment**: Provides access to registries (configs, tasks, templates, tools) and storage
- Location: `src/gimle/hugin/agent/environment.py`
- Loaded from directory structure using `Environment.load()`

**Stack**: Manages the interaction flow for an agent (state machine)
- Location: `src/gimle/hugin/interaction/stack.py`
- Contains ordered list of interactions that get executed

### Key Patterns

**Interaction-based**: Everything is an interaction that can be added to an agent's stack:
- `TaskDefinition`: Initial task prompt
- `AskOracle`: LLM completion calls
- `ToolCall`: Tool execution
- `ToolResult`: Result from tool execution
- `AgentCall`: Launches a child agent (adds `Waiting` to parent stack)
- `Waiting`: Pauses parent agent until child completes
- `AskHuman`: Human input requests

**Registry Pattern**: All components are managed by registries:
- `ConfigRegistry`: Agent configurations
- `TaskRegistry`: Task definitions
- `TemplateRegistry`: Jinja2 templates for prompts
- `ToolRegistry`: Available tools

**Tool Architecture**: Tools are defined with:
- Python implementation (`.py` file)
- YAML definition (`.yaml` file with parameters/description)
- Tools receive `stack` parameter for context access
- Tools return `ToolResponse` for immediate results, or `AgentCall` to spawn a child agent

### Directory Structure Conventions

Agent directories follow this pattern:
```
agent_directory/
├── configs/           # Agent configs (.yaml)
├── tasks/            # Task definitions (.yaml)
├── templates/        # Jinja2 templates (.yaml)
└── tools/           # Custom tools (.py + .yaml)
```

## Development Guidelines

### Agent Development
- Study existing examples in `examples/` and `apps/` before creating new agents
- Use `examples/basic_agent/` as the simplest starting point
- See `examples/human_interaction/` for human-in-the-loop patterns
- See `examples/task_sequences/` for multi-stage pipelines with result passing
- See `examples/shared_state/` for multi-agent state sharing with permissions
- See `examples/artifacts/` for long-term memory patterns
- See `examples/branching/` for parallel exploration patterns
- See `examples/sub_agent/` for launching child agents from tools
- See `apps/` for complex, production-like application showcases
- Agent configs specify `system_template`, `llm_model`, and available `tools`
- Tasks define the initial prompt and parameters for an agent

### Tool Development
- Tools must accept `stack` parameter (auto-injected)
- Access agent context via `stack.agent.environment.env_vars`
- Follow pattern: tool.py implementation + tool.yaml definition
- Built-in tools in `src/gimle/hugin/tools/builtins/`
- To spawn a child agent from a tool, return an `AgentCall` (not `ToolResponse`). The framework will create the child agent and add a `Waiting` interaction to the parent. Never run a sub-agent synchronously inside a tool.

### Task Parameters
Tasks support structured parameter definitions with type, description, required status, and defaults:

**Structured format (recommended):**
```yaml
parameters:
  data_source:
    type: string
    description: Path to the sales data CSV file
    required: true
  limit:
    type: integer
    description: Maximum number of items to return
    required: false
    default: 10
```

**Simple format (still supported):**
```yaml
parameters:
  questions: "What is the meaning of life?"
```

**Supported types:** `string`, `integer`, `number`, `boolean`, `array`

**Validation:**
- Required parameters must be provided or task creation fails
- Optional parameters use defaults if not provided
- Parameters are validated when creating agents from tasks
- CLI prompts show type hints, descriptions, and default values

### Testing
- Mock dependencies using fixtures in `tests/conftest.py`
- Use `MockModel` for LLM calls in tests
- Test markers available: `unit`, `integration`, `slow`
- All fixtures support both programmatic and YAML-based agent creation

### Code Style
- Line length: 80 characters
- Use Black formatting with isort for imports
- Type hints required (mypy with strict settings)
- Python 3.12+ required

## Apps

Production-like application showcases are in the `apps/` directory. Available apps: `data_analyst`, `financial_newspaper`, `rap_machine`, `the_hugins`.

### The Hugins - Creature World Simulation

An isometric world where AI creatures (Hugins) explore, interact, craft, and plan autonomously.

```bash
# Run the world simulation
uv run hugin app the_hugins

# Run with web dashboard
uv run hugin app the_hugins -- --monitor --port 8080
```

- Creatures have tools for movement, interaction, crafting, building, memory, and planning
- All creature tools accept an optional `reason` parameter so creatures explain their actions
- World state is rendered as an isometric canvas with a live-updating web UI
- Creature sprites are generated and rendered as animated stickmen

### Financial Newspaper - Multi-Agent Journalism

AI journalist and editor agents collaborating to produce a financial newspaper.

```bash
# Run newspaper generation
uv run hugin app financial_newspaper

# With monitoring
uv run hugin app financial_newspaper -- --monitor --port 8001
```

- Journalist agent researches and writes articles, delegates to technical analyst sub-agents
- Editor agent reviews articles and creates the final HTML layout
- Uses `AgentCall` pattern for agent delegation (journalist → editor)
- Generated newspaper saved to `storage/newspaper_layouts/latest.html`

### RapMachine - AI Agent Battles

Multi-agent rap battle competitions.

```bash
# Random AI rapper battle (requires ANTHROPIC_API_KEY for haiku-latest)
uv run hugin app rap_machine -- --random-agents --model haiku-latest

# Run with web dashboard
uv run hugin app rap_machine -- --random-agents --monitor --port 8080 --model haiku-latest

# Custom topic and rounds
uv run hugin app rap_machine -- --random-agents --topic "Future of AI" --rounds 5 --model haiku-latest
```

**Notes:**
- **Recommended**: Use haiku-latest (default) as it handles complex tool calling reliably
- **Requires API Key**: haiku-latest and sonnet-latest require `ANTHROPIC_API_KEY` environment variable
- Override models with `--model`, `--rapper1-model`, `--rapper2-model`, `--judge-model`
- **Known Issue with Local Models**: qwen2.5-0.5b does NOT reliably call tools in multi-turn conversations. For reliable local operation, use a more capable model like llama3.3.

## Common Patterns

### Creating Agents Programmatically
```python
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.storage.local import LocalStorage

# Load environment
storage = LocalStorage(base_path="./storage")
env = Environment.load("examples/basic_agent", storage=storage)
session = Session(environment=env)

# Create agent
config = env.config_registry.get("basic_agent")
task = env.task_registry.get("hello_world")
session.create_agent_from_task(config, task)

# Run agent
agent = session.agents[0]
while agent.step():
    pass

# or run session to end
session.run()
```

### Launching Sub-Agents from Tools
Tools that need to delegate work to a child agent should return an `AgentCall`:
```python
from gimle.hugin.interaction.agent_call import AgentCall

def my_tool(stack, ...) -> Union[ToolResponse, AgentCall]:
    config = stack.agent.environment.config_registry.get("child_config")
    task = Task(name="child_task", prompt="Do something", ...)
    return AgentCall(stack=stack, config=config, task=task)
```
The framework creates the child agent and adds a `Waiting` interaction to the parent stack. The parent resumes when the child completes.

### Shared State (Multi-Agent)
For multi-agent scenarios, use `environment.env_vars` to share state:
```python
# Store shared state
env_vars = {"worlds": {"world_1": shared_world_object}}
env = Environment.load(path, storage=storage, env_vars=env_vars)

# Access in tools
world = stack.agent.environment.env_vars["worlds"]["world_1"]
```

### Memory and Artifacts
- **Context**: Short-term memory in agent's stack
- **Artifacts**: Long-term memory stored via `save_insight` tool
- Artifacts are stored in `artifacts/` directory with UUID names

## Task Tracking

Use `docs/tasks/` for tracking feature requests, bugs, and enhancements. Each task is a markdown file with YAML frontmatter.

### Creating a New Task

Create a file in `docs/tasks/` with format `{ID}-{short-name}.md`:

```markdown
---
title: Short descriptive title
id: ABC
type: bug | enhancement | feature
priority: low | medium | high
status: open | in-progress | done
---

## Description

What needs to be done and why.

## Tasks

- [ ] Subtask 1
- [ ] Subtask 2

## Affected Files

- `path/to/file.py` - What changes needed

## Success Criteria

- [ ] Criterion 1
- [ ] Criterion 2
```

### Task ID Convention

Use 2-4 letter uppercase IDs that hint at the task:
- `PTC` - Parallel Tool Calls
- `HGX` - Hugins Graphics
- `RMW` - RapMachine Web

### When to Create Tasks

- Bugs discovered during development
- Feature ideas that are out of scope for current work
- Enhancements identified while working on other tasks
- Technical debt that should be addressed later

This keeps the codebase organized and provides context for future development sessions.
