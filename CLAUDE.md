# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Git Workflow

**Never commit directly to `main`.** Always work on a feature branch:
- Create a new branch for any change (`git checkout -b descriptive_branch_name`)
- Use snake_case for branch names
- Commit to the branch, then merge via PR or as instructed
- **Do NOT add Co-Authored-By lines** - commit messages should not include Claude as author

## Pull Request Workflow

### Before Committing

1. **Run pre-commit checks** - Always run before committing:
   ```bash
   uv run pre-commit run --all-files
   ```
   If files are modified by hooks, run again to verify all pass.

2. **Run tests** - Ensure nothing is broken:
   ```bash
   uv run pytest -x -q
   ```

3. **Test manually** - For UI/app changes, run the app and verify:
   ```bash
   uv run hugin app the_hugins  # For Hugins changes
   ```

### Commit Messages

Write clear, descriptive commit messages:
```
Short summary line (imperative mood, <50 chars)

Longer description if needed:
- What changed and why
- Any important details
- Related issues or context
```

### Creating a PR

```bash
# Push branch
git push -u origin branch_name

# Create PR with structured description
gh pr create --title "Short descriptive title" --body "$(cat <<'EOF'
## Summary
Brief description of what this PR does.

## Changes
- Change 1
- Change 2

## Testing
How the changes were tested.
EOF
)"
```

### PR Description Best Practices

- **Summary**: 1-2 sentences on what and why
- **Changes**: Bullet list of specific changes
- **Testing**: How you verified it works
- For bug fixes: Include steps to reproduce
- For features: Include usage examples

## GitHub CLI Patterns

### Working with Issues

```bash
# List all issues
gh issue list --repo gimlelabs/gimle-hugin --state all

# Get issue details as JSON
gh issue list --state open --json number,title,body,labels

# Close an issue with comment
gh issue close 123 --comment "Fixed in PR #456"

# Create a new issue
gh issue create --title "Bug: description" --body "Details..."
```

### Syncing Issues to Local Tasks

```bash
# Fetch all issues and create local task files
gh issue list --state all --limit 100 --json number,title,state,body,labels,createdAt |
  jq -r '.[] | "tasks/\(if .state == "OPEN" then "open" else "closed" end)/\(.number)-\(.title | gsub(" "; "-") | ascii_downcase).md"'
```

### Working with PRs

```bash
# Create PR from current branch
gh pr create --title "Title" --body "Description"

# List open PRs
gh pr list

# View PR details
gh pr view 123

# Merge PR
gh pr merge 123 --merge
```

## Multi-Agent Parallel Work

Use git worktrees to enable multiple Claude agents working simultaneously on different tasks.

### Setup for Parallel Agents

```bash
# Main repo structure
/Users/you/gimle/
├── gimle-hugin/              # Main worktree (main branch)
├── gimle-hugin-task-001/     # Agent 1 working on task 001
├── gimle-hugin-task-006/     # Agent 2 working on task 006
└── gimle-hugin-experiment/   # Agent 3 experimenting
```

### Creating Worktrees for Agents

```bash
# From main repo
cd gimle-hugin

# Create worktree for each agent/task
git worktree add ../gimle-hugin-task-001 -b task/001-artifact-feedback
git worktree add ../gimle-hugin-task-006 -b task/006-parallel-tools
git worktree add ../gimle-hugin-ui-fixes -b fix/ui-improvements
```

### Running Multiple Claude Sessions

1. Open separate terminal/Claude sessions
2. Point each session to a different worktree directory
3. Each agent works independently on their branch
4. No conflicts since each has isolated working directory

### Coordinating Parallel Work

- **Avoid overlapping files** - Assign different areas to each agent
- **Rebase regularly** - Keep branches up to date with main
- **Small, focused PRs** - Easier to merge without conflicts
- **Communicate via tasks** - Update task files with progress/blockers

### Cleanup After Merging

```bash
# List all worktrees
git worktree list

# Remove completed worktree
git worktree remove ../gimle-hugin-task-001

# Prune stale references
git worktree prune

# Delete merged branch
git branch -d task/001-artifact-feedback
```

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

## Task Management

Tasks are tracked in the `tasks/` folder at the repository root, organized by status:

```
tasks/
├── open/           # Active tasks to be worked on
│   ├── 001-artifact-feedback.md
│   └── 006-parallel-tool-calls/
│       ├── description.md
│       ├── plan.md
│       └── spec.md
└── closed/         # Completed or abandoned tasks
    └── 015-live-monitor-updates.md
```

### Task Structure

**Simple tasks** - A single markdown file:
```
tasks/open/001-artifact-feedback.md
```

**Complex tasks** - A folder with multiple documents:
```
tasks/open/006-parallel-tool-calls/
├── description.md    # What and why
├── plan.md          # Implementation steps
├── spec.md          # Technical specification
└── notes.md         # Research, decisions, etc.
```

### Task File Format

Each task file should have YAML frontmatter:

```markdown
---
github_issue: 6           # Optional: linked GitHub issue
title: Support parallel tool calls
state: OPEN
labels: [enhancement]
priority: high
---

# Title

Description of what needs to be done and why.

## Tasks

- [ ] Subtask 1
- [ ] Subtask 2

## Success Criteria

- [ ] Criterion 1
- [ ] Criterion 2
```

### Git Worktree Workflow

**Always use git worktrees when working on tasks.** This enables parallel work on multiple tasks.

#### Starting a New Task

```bash
# From main repo, create a worktree for the task
git worktree add ../gimle-hugin-task-006 -b task/006-parallel-tool-calls

# Work in the new worktree
cd ../gimle-hugin-task-006

# Create/update task planning documents
mkdir -p tasks/open/006-parallel-tool-calls
# Add description.md, plan.md, spec.md as needed

# Implement the task...

# Commit your work
git add .
git commit -m "Implement parallel tool calls support"

# Push and create PR
git push -u origin task/006-parallel-tool-calls
gh pr create --title "Implement parallel tool calls" --body "Closes #6"
```

#### Completing a Task

```bash
# After PR is merged, move task to closed
git mv tasks/open/006-parallel-tool-calls tasks/closed/

# Or for simple tasks
git mv tasks/open/006-parallel-tool-calls.md tasks/closed/

# Clean up worktree
cd /path/to/main/repo
git worktree remove ../gimle-hugin-task-006
```

#### Managing Worktrees

```bash
# List all worktrees
git worktree list

# Remove a worktree (after merging)
git worktree remove ../gimle-hugin-task-006

# Prune stale worktree references
git worktree prune
```

### Branch Naming Convention

Use `task/` prefix with task ID:
- `task/001-artifact-feedback`
- `task/006-parallel-tool-calls`
- `task/fix-memory-leak` (for tasks without numeric IDs)

### When to Create Tasks

- Feature requests and enhancements
- Bugs discovered during development
- Ideas that are out of scope for current work
- Technical debt to address later
- Any work that benefits from planning before implementation
