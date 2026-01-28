---
layout: base.njk
title: Use the Monitor
---

# Use the Monitor

The Hugin Monitor is a web dashboard for visualizing agent execution in real-time.

## Starting the Monitor

### Option 1: Run Agent with Monitor

The simplest approach—start both together:

```bash
hugin run --task my_task --task-path ./my_agent --monitor
```

This starts your agent, launches the monitor on port 8000, and opens your browser.

### Option 2: Monitor Existing Storage

Monitor a previously run or currently running agent:

```bash
# Terminal 1: Run agent with storage
hugin run --task my_task --task-path ./my_agent --storage-path ./data/my_agent

# Terminal 2: Start monitor
hugin monitor --storage-path ./data/my_agent
```

### Options

| Option | Description |
|--------|-------------|
| `-s, --storage-path` | Path to agent storage directory |
| `-p, --port` | Server port (default: 8000) |
| `--no-browser` | Don't automatically open browser |

## Using the Dashboard

The interface is straightforward:

- **Left panel**: Select sessions and agents
- **Center**: Timeline showing interactions (LLM calls, tool calls, results)
- **Right**: Details of selected interaction

Click any interaction to inspect it. The dashboard updates live as your agent runs.

## Troubleshooting

**Agent not showing?**
Verify `--storage-path` matches between `hugin run` and `hugin monitor`.

**Port already in use?**
```bash
hugin monitor -s ./storage -p 8001
```

**Monitor multiple agents?**
Run multiple instances on different ports:
```bash
hugin monitor -s ./storage/agent1 -p 8001
hugin monitor -s ./storage/agent2 -p 8002
```

## Next Steps

- [Create an Agent](/how-to/create-agent/) - Build agents to monitor
- [Stacks & Interactions](/concepts/stacks/) - Understand the interaction model
