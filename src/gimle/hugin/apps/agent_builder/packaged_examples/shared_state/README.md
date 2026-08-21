# Shared State Example

Demonstrates agents sharing state through `session.state` with namespaces.

## Concept

This example shows how multiple agents can read and write to shared state using the session's `SessionState`. Agents can use `stack.get_shared_state()` and `stack.set_shared_state()` to share data through named namespaces.

## Key Features

- **Shared state**: Agents share data via `session.state`
- **Namespaces**: State is organized into namespaces with access control
- **Producer-consumer**: One agent writes numbers, another reads them

## Structure

```
shared_state/
├── configs/
│   ├── producer.yaml   # Agent that writes to shared state
│   └── consumer.yaml   # Agent that reads from shared state
├── tasks/
│   ├── produce.yaml
│   └── consume.yaml
├── templates/
│   ├── producer_system.yaml
│   └── consumer_system.yaml
└── tools/
    ├── state_tools.py
    ├── set_number.yaml
    ├── get_number.yaml
    └── list_numbers.yaml
```

## Running

Use the Hugin CLI with `--namespace` to create the shared namespace and `--agent` for each agent:

```bash
uv run hugin run -p examples/shared_state -n numbers -a produce:producer -a consume:consumer
```

The `-n numbers` flag creates the "numbers" namespace before the agents are created.

## How It Works

1. The CLI creates a session and a shared namespace called "numbers"
2. Two agents are created: producer and consumer
3. Producer writes numbers to shared state using `set_number`
4. Consumer reads numbers from shared state using `get_number`
5. Both agents can see the same data through the namespace

## Programmatic Usage

```python
session = Session(environment=env)
session.state.create_namespace("numbers")
```

Agent configs declare namespace access:
```yaml
state_namespaces:
  - numbers
```

Tools use stack methods to access state:
```python
# Write
stack.set_shared_state(key, value, namespace="numbers")

# Read
value = stack.get_shared_state(key, namespace="numbers")
```

## Access Control

Agents can only access namespaces listed in their config's `state_namespaces`. This provides isolation between different agent groups.

### Two Types of Access Control

**1. Config-based Access (Static)**

Declare namespaces in agent config:
```yaml
state_namespaces:
  - numbers
  - results
```

**2. Dynamic Permissions (Runtime)**

Grant or revoke access programmatically:

```python
# Create a restricted namespace
session.state.create_namespace("restricted", open_access=False)

# Grant access to specific agent
session.state.grant_access("restricted", agent_id="agent-123")

# Revoke access
session.state.revoke_access("restricted", agent_id="agent-123")

# List agents with access
agents = session.state.list_namespaces_for_agent(agent_id="agent-123")
```

### Access Control Patterns

**Open Access Namespace** (default):
```python
session.state.create_namespace("public")  # Anyone with config access can use
```

**Restricted Namespace**:
```python
session.state.create_namespace("private", open_access=False)
session.state.grant_access("private", agent_id="trusted-agent")
# Only agents explicitly granted access can use this namespace
```

**Common Namespace** (always accessible):
```python
# No need to create - always exists
stack.set_shared_state("key", "value")  # Uses "common" namespace by default
```

### Use Cases for Permissions

- **Security**: Restrict sensitive data to authorized agents only
- **Isolation**: Prevent agents from interfering with each other's state
- **Coordination**: Share state between specific agent groups
- **Audit**: Track which agents have access to which namespaces
