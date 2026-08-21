# Sub-Agent Example

Demonstrates how a parent agent can spawn child agents using the `builtins.launch_agent` tool.

## Concept

This example shows the simplest form of multi-agent interaction: a parent agent that delegates work to a child agent. The parent agent uses the built-in `launch_agent` tool to spawn a child, which runs to completion and returns its results.

## Key Features

- **Agent spawning**: Parent uses `launch_agent` to create a child agent
- **Synchronous execution**: Parent waits for child to complete
- **Result passing**: Child's output is returned to parent

## Structure

```
sub_agent/
├── configs/
│   ├── parent.yaml     # Parent agent that spawns children
│   └── child.yaml      # Child agent that performs computation
├── tasks/
│   ├── delegate.yaml   # Main task for parent
│   └── compute.yaml    # Task template for child
└── templates/
    ├── parent_system.yaml
    └── child_system.yaml
```

## Running

```bash
uv run hugin run --task delegate --task-path examples/sub_agent -c parent
```

## How It Works

1. Parent agent receives a task that requires computation
2. Parent uses `list_agents` to see available child configs
3. Parent uses `launch_agent` to spawn a child with a specific task
4. Child agent completes its work and returns results
5. Parent receives the results and finishes

## Key Code Pattern

The parent agent config includes:
```yaml
tools:
  - builtins.launch_agent:launch_agent
  - builtins.list_agents:list_agents
  - builtins.finish:finish
```

When the parent calls `launch_agent`:
```
launch_agent(
  config_name="child",
  task_name="compute",
  task_description="Calculate the sum of 1 to 10"
)
```

The child runs to completion and returns its results to the parent.
