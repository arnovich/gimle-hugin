# Agent Messaging Example

Demonstrates direct agent-to-agent communication using `agent.message_agent()`.

## Concept

This example shows how agents can send messages directly to each other. When an agent calls `message_agent()` on another agent, it inserts an `ExternalInput` into the target's stack, which the target processes on its next step.

## Key Features

- **Direct messaging**: Agents send messages using `message_agent()`
- **Ping-pong pattern**: Two agents passing messages back and forth
- **Asynchronous communication**: Messages are processed on the next step
- **Independent agents**: This pattern can be used to run agents independently, instead of sub-agents.
You can see how to use a sub-agent pattern instead here in the [sub_agent](../sub_agent/) example.

## Structure

```
agent_messaging/
├── configs/
│   ├── ping.yaml       # Agent that starts the ping-pong
│   └── pong.yaml       # Agent that responds to pings
├── tasks/
│   ├── start_ping.yaml
│   └── wait_pong.yaml
├── templates/
│   ├── ping_system.yaml
│   └── pong_system.yaml
└── tools/
    ├── messaging.py
    └── messaging.yaml
```

## Running

Use the Hugin CLI with multiple `--agent` flags (TASK:CONFIG format):

```bash
uv run hugin run -p examples/agent_messaging -a start_ping:ping -a wait_pong:pong
```

## How It Works

1. Two agents are created: ping and pong
2. Ping agent starts by sending a "ping" message to pong
3. Pong receives the message, processes it, and sends "pong" back
4. This continues for a few rounds
5. Both agents finish after the exchange

## Key Code Pattern

The messaging tool wraps `agent.message_agent()`:

```python
def send_to_agent(target_agent_id: str, message: str, stack: "Stack"):
    session = stack.agent.session
    target = session.get_agent(target_agent_id)
    target.message_agent(message)
```

When called, this inserts an `ExternalInput` interaction into the target agent's stack.
