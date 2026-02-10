# Heartbeat Example

A **heartbeat agent** wakes up at regular intervals, checks a sensor for
changes, acts on anything new, and goes back to sleep. This pattern is
useful for any periodic monitoring task:

- Watching a folder for new files (this example)
- Polling an API for new events
- Checking a database for pending work
- Monitoring an inbox for new messages

## How it works

```
    ┌──────────────────────────────────┐
    │         check_folder             │
    │  (the "sensor" — swap this out)  │
    ├──────────────────────────────────┤
    │                                  │
    │  New files? ─── YES ──► LLM analyzes files
    │       │                     │
    │       NO                    │ LLM calls
    │       │                     ▼
    │       │            sleep_until_next_check
    │       │                     │
    │       ▼                     ▼
    │    Waiting              Waiting
    │  (N ticks)            (N ticks)
    │       │                     │
    │       └─────────┬───────────┘
    │                 ▼
    │           check_folder  (loop restarts)
    │                 ·
    │                 ·
    │  LLM can call `finish` at any time to stop
    └──────────────────────────────────┘
```

The key mechanism is the `wait_for_ticks` condition. When a tool returns
a `Waiting` interaction with this condition, the agent **pauses for N
session steps** before continuing — creating a periodic heartbeat without
wasting LLM calls on empty checks.

There are two paths back to `check_folder`:

1. **Nothing new** — `check_folder` directly returns a `Waiting` that
   loops back to itself. The LLM is never called. This is the silent
   heartbeat.

2. **Something new** — `check_folder` returns the new data to the LLM.
   The LLM analyzes it, then calls `sleep_until_next_check` to resume
   the heartbeat loop.

The agent keeps running indefinitely until the LLM decides to call
`finish`.

## Running

```bash
# Create the folder to watch
mkdir -p /tmp/watched_folder

# Start the heartbeat agent
uv run hugin run -t monitor_folder -p examples/heartbeat --max-steps 50

# In another terminal, add files while it runs:
touch /tmp/watched_folder/report.csv
touch /tmp/watched_folder/data.json
```

### Custom interval and folder

```bash
uv run hugin run -t monitor_folder -p examples/heartbeat \
  --parameters '{"folder_path": "/tmp/my_inbox", "heartbeat_interval": 5}' \
  --max-steps 100
```

## Adapting the sensor

The `check_folder` tool is just one example of a sensor. To adapt this
pattern for your own use case:

1. **Replace `check_folder`** with your own sensor tool that checks
   whatever you care about (an API, a database, a queue, etc.)
2. Your sensor should follow the same two-path pattern:
   - **Nothing interesting**: return a `Waiting` with `wait_for_ticks`
     that loops back to your sensor (silent heartbeat)
   - **Something to report**: return the data with no
     `response_interaction` so the LLM can act on it
3. Keep `sleep_until_next_check` (or rename it) — it's the generic
   "go back to sleep" tool that the LLM calls after acting.
4. Update the system prompt to describe what your agent monitors and
   how it should respond to changes.

## Files

```
examples/heartbeat/
├── configs/heartbeat.yaml              # Agent config
├── tasks/monitor_folder.yaml           # Task with configurable interval
├── templates/heartbeat_system.yaml     # System prompt
├── tools/
│   ├── check_folder.py + .yaml         # Sensor (swap this out)
│   └── sleep_until_next_check.py + .yaml  # Resume heartbeat loop
└── README.md
```
