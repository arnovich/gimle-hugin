# Basic Agent Example

This is a simple example agent implementation that demonstrates the basic structure of a Gimle agent.

## Structure

- `configs/basic_agent.yaml` - Agent configuration
- `tasks/hello_world.yaml` - A simple hello world task
- `templates/basic_system.yaml` - System prompt template

## Usage

### Quick Start (Recommended)

Run the example using the Hugin CLI with dashboard:

```bash
uv run hugin run --task hello_world --task-path examples/basic_agent --monitor
```

Or with specific options:

```bash
# With reduced steps
uv run hugin run --task hello_world --task-path examples/basic_agent --max-steps 20

# With custom parameters
uv run hugin run --task hello_world --task-path examples/basic_agent --parameters '{"questions": "What is AI? How does it work?"}'

# With debug logging
uv run hugin run --task hello_world --task-path examples/basic_agent --log-level DEBUG
```

### Programmatic Usage

```python
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.storage.local import LocalStorage

# Load the environment
storage = LocalStorage(base_path="./data")
env = Environment.load("examples/basic_agent", storage=storage)

# Create a session
session = Session(environment=env)

# Get the config and task
config = env.config_registry.get("basic_agent")
task = env.task_registry.get("hello_world")

# Create an agent from the task
session.create_agent_from_task(config, task)

# Run all agents in session to completion
session.run()
```
