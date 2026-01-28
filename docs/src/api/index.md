---
layout: base.njk
title: API Reference
---

# API Reference

This reference covers the main classes and interfaces in Hugin.

## Agent

The main entity that executes tasks.

```python
from gimle.hugin.agent.agent import Agent
```

### Creating Agents

```python
# From task (recommended)
agent = Agent.create_from_task(config, task, session)

# Direct creation
agent = Agent(config=config, task=task, session=session)
```

### Methods

| Method | Description |
|--------|-------------|
| `step()` | Execute one step. Returns `True` if more steps remain. |
| `run()` | Run to completion. |
| `get_result()` | Get the final result after completion. |

### Properties

| Property | Description |
|----------|-------------|
| `stack` | The interaction stack |
| `config` | Current configuration |
| `task` | Current task |
| `session` | Parent session |
| `environment` | Environment with registries |

## Session

Manages multiple agents and provides shared environment.

```python
from gimle.hugin.agent.session import Session
```

### Creating Sessions

```python
session = Session(environment=env)
```

### Methods

| Method | Description |
|--------|-------------|
| `create_agent_from_task(config, task)` | Create and add an agent |
| `run()` | Run all agents to completion |
| `get_agent(name)` | Get agent by name |

### Properties

| Property | Description |
|----------|-------------|
| `agents` | List of agents |
| `environment` | Shared environment |
| `state` | Session-wide shared state |

## Environment

Provides access to registries and storage.

```python
from gimle.hugin.agent.environment import Environment
```

### Loading

```python
# From directory
env = Environment.load("./my_agent", storage=storage)

# With environment variables
env = Environment.load(
    "./my_agent",
    storage=storage,
    env_vars={"API_KEY": "xxx"}
)
```

### Properties

| Property | Description |
|----------|-------------|
| `config_registry` | Agent configurations |
| `task_registry` | Task definitions |
| `template_registry` | Jinja2 templates |
| `tool_registry` | Available tools |
| `storage` | Storage backend |
| `env_vars` | Environment variables |

## Stack

Manages the interaction history.

```python
from gimle.hugin.interaction.stack import Stack
```

### Methods

| Method | Description |
|--------|-------------|
| `push(interaction)` | Add interaction to stack |
| `get_context()` | Get context for LLM call |
| `create_branch(name)` | Create a parallel branch |
| `get_branch_context(branch_id)` | Get branch-specific context |
| `get_shared_state(namespace)` | Get shared state |
| `set_shared_state(namespace, state)` | Set shared state |

## Storage

Interface for persisting agent state.

```python
from gimle.hugin.storage.local import LocalStorage
```

### LocalStorage

```python
storage = LocalStorage(base_path="./storage")
```

File-based storage for development and single-machine deployments.
