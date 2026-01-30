# BabyHugin

A Hugin version of [BabyAGI](https://babyagi.org/) - the autonomous AI agent framework.

BabyHugin is an interactive assistant that runs in a continuous loop, completing tasks directly or delegating complex work to specialized agents it creates on-the-fly using Hugin's agent building capabilities.

## Features

- **Interactive Loop**: Continuously asks what you want to do next
- **Agent Delegation**: Creates specialized agents for complex tasks using `agent_builder`
- **File System Access**: Can read files, list directories, and search for patterns
- **Memory**: Saves and retrieves insights across the session

## Running BabyHugin

```bash
# Using the app command (recommended)
uv run hugin app baby_hugin

# With options
uv run hugin app baby_hugin -- --model haiku-latest --monitor

# Or using the standard run command
uv run hugin run --task main --task-path apps/baby_hugin
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--model` | sonnet-latest | LLM model to use |
| `--monitor` | false | Open the agent monitor dashboard |
| `--port` | 8080 | Monitor dashboard port |
| `--max-steps` | 100 | Maximum steps before stopping |
| `--log-level` | WARNING | Logging level (DEBUG, INFO, WARNING, ERROR) |

## How It Works

1. BabyHugin starts by asking what you want to accomplish
2. For simple tasks (reading files, searching, etc.), it handles them directly
3. For complex tasks (data analysis, multi-step workflows), it:
   - Checks if a suitable agent already exists
   - If not, launches `agent_builder` to create one
   - Runs the new agent to complete your task
4. Reports results and asks what you want to do next
5. Continues until you say goodbye

## Example Session

```
BabyHugin: Hello! I'm BabyHugin. What would you like me to help you with today?

You: Analyze the sales data in sales.csv and create a report

BabyHugin: That sounds like a complex analysis task. Let me create a
specialized data analyst agent for this...
[Creates agent via agent_builder]
[Runs data_analyst agent]
Here's the analysis report: ...

What would you like me to do next?

You: Find all Python files that import pandas

BabyHugin: I can do that directly with my search tools.
[Uses search_files]
Found 12 files that import pandas: ...

What would you like me to do next?

You: That's all for now, thanks!

BabyHugin: You're welcome! Goodbye!
[Finishes]
```

## Available Tools

| Tool | Purpose |
|------|---------|
| `ask_user` | Get input from the user |
| `list_agents` | See available agents |
| `launch_agent` | Run a specialized agent |
| `read_file` | Read file contents |
| `list_files` | List directory contents |
| `search_files` | Search for patterns in files |
| `open_file` | Open a file with system default app (browser, viewer, etc.) |
| `save_insight` | Save findings for later |
| `query_artifacts` | Retrieve saved insights |
| `finish` | End the session |
