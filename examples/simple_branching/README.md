# Simple Branching Example

This example demonstrates basic stack branching in Hugin - spawning a branch to explore a question and saving the result as an artifact.

## Concept

**Simple Branching** allows an agent to:
- Create a branch to explore a follow-up question
- The branch runs in parallel with the main task
- The branch saves its findings as an artifact
- The main task continues without waiting

This is useful when a user asks a follow-up question during a task - the agent can spawn a branch to answer it while continuing the main work.

## Key Features

### Branch Isolation
- Each branch sees the main branch history **up to the fork point**
- Branches **don't affect** the main context
- Branch results are saved as **artifacts** for the user

### Parallel Execution
- Branches run alongside the main task
- No waiting for branches to finish
- Each branch saves its own artifact

### Custom Tool

#### `create_branch`
Creates a new branch to explore a specific question.

**Parameters:**
- `branch_name`: Short name (e.g., "employee_view")
- `question`: The question to explore

## Running the Example

### Basic Run
```bash
uv run hugin run \
  --task analyze_topic \
  --task-path examples/simple_branching
```

### Custom Topic
```bash
uv run hugin run \
  --task analyze_topic \
  --task-path examples/simple_branching \
  --parameters '{"topic": "Electric vehicles", "focus": "Consumer adoption"}'
```

## Workflow

```
Main Branch: Analyzing topic
         │
         ├─> Initial analysis
         │
         ├─> create_branch("employee_view", "How do employees feel?")
         │
         │     ┌─────────────────────┐
         │     │                     │
         │   Branch:              Main:
         │   employee_view        continues...
         │     │                     │
         │   (explores)              │
         │     │                     │
         │   save_insight()          │
         │   finish()                │
         │     │                     │
         │     └─────────────────────┘
         │            ↓
         │   (artifact saved)
         │
         └─> finish() on main
```

## Context Visibility

```python
# Main branch sees only main interactions
main_context = [task_def, analysis, create_branch_call, finish]

# Branch "employee_view" sees:
# - Main branch up to fork point
# - Its own exploration
employee_view_context = [task_def, analysis, investigate, save_insight, finish]

# The user sees:
# - Main branch output
# - Artifact from branch with findings
```

## When to Use This

Use simple branching when:
- ✓ You want to answer a side question without derailing main work
- ✓ The branch result should be visible to the user (as artifact)
- ✓ You don't need to merge branch findings back into main

Don't use this when:
- ✗ You need to compare multiple approaches (use `examples/branching/`)
- ✗ You need to merge branch findings back into main analysis
- ✗ Branches need to communicate with each other

## Architecture

### Two Configs Prevent Recursion

The main branch uses `analyst` config with `create_branch` tool.
Branches use `explorer` config with only `save_insight` and `finish` tools.

This prevents branches from creating more branches.

```yaml
# analyst.yaml - can create branches
tools:
  - create_branch:create_branch
  - builtins.finish:finish

# explorer.yaml - can only save and finish
tools:
  - builtins.save_insight:save_insight
  - builtins.finish:finish
```
