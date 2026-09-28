# Agent Messaging Example

Demonstrates direct agent-to-agent communication using `agent.message_agent()`.

## Concept

This example shows how agents can send messages directly to each other. When an agent calls `message_agent()` on another agent, it queues durable external input for the target's next model turn. Multiple pending messages reach that turn together, alongside its original task or tool result.

## Key Features

- **Direct messaging**: Agents send messages using `message_agent()`
- **Ping-pong pattern**: Two agents passing messages back and forth
- **Asynchronous communication**: Messages are processed on the next model turn
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
    target.message_agent(message, source=f"agent:{stack.agent.id}")
```

Pending messages survive session save/reload. A completed agent wakes on its
next session step; a child, tool, human, or condition wait finishes before
messages are delivered. Each message is fenced as untrusted data with its source
label. The label is provenance supplied by the caller, not authentication.

By default, external text stays in context for five model turns, including the
delivery turn. Set `context_window=1` to include it only in the delivery turn;
the full history remains persisted. Use `branch="name"` to target an existing
named branch; omitting it targets the main branch. Unknown branches and windows
that are not positive integers are rejected.
