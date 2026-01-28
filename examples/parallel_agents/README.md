# Parallel Agents Example

Demonstrates how to run multiple independent agents concurrently within the same session.

## Key Features

- **Multiple agents**: Two counter agents running in parallel
- **Session stepping**: All agents step together as the session steps
- **Independent tasks**: Each agent works on its own counting task

## Structure

```
parallel_agents/
├── configs/
│   └── counter.yaml    # Single config used by both agents
├── tasks/
│   ├── count_evens.yaml
│   └── count_odds.yaml
├── templates/
│   └── counter_system.yaml
└── tools/
    ├── counter_tools.py    # shared file for implementations
    └── get_count.yaml
    └── increment.yaml
```

## Running

Use the Hugin CLI with multiple `--agent` flags:

```bash
uv run hugin run -p examples/parallel_agents -a count_evens -a count_odds
```

## How It Works

1. The CLI creates a Session with the environment
2. Two agents are created with different tasks (count evens, count odds)
3. Both agents are added to `session.agents`
4. `session.step()` is called in a loop, stepping all agents together
5. Each agent independently counts using the counter tools

## Programmatic Usage

```python
from gimle.hugin.agent.session import Session

# Create session
session = Session(environment=env)

# Add multiple agents
session.create_agent_from_task(config, count_evens_task)
session.create_agent_from_task(config, count_odds_task)

# Run all agents together
session.run():
```

## Output

The agents will interleave their counting operations, demonstrating parallel execution within the session's step loop.
