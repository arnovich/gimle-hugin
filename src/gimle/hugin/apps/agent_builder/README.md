# Agent Builder

A meta-agent that helps you create new Hugin agents through an interactive CLI wizard.

## Quick Start

```bash
# Run the interactive wizard
uv run hugin create
```

The wizard will ask you:
1. Agent name (snake_case)
2. Description (be as detailed as you like)
3. Which LLM model to use
4. Output directory path

Then the Agent Builder (powered by sonnet-latest) will:
- Analyze your requirements
- Design appropriate tools for your agent
- Generate a complete, runnable agent

## How It Works

1. **CLI Wizard** collects your requirements
2. **Agent Builder agent** designs and generates:
   - Config file (`configs/agent_name.yaml`)
   - System template (`templates/agent_name_system.yaml`)
   - Main task (`tasks/main.yaml`)
   - Custom tools (`tools/*.py` + `tools/*.yaml`) - determined by the builder
3. **Output** is written to your specified directory

## Example

```bash
$ uv run hugin create

============================================================
  Hugin Agent Builder - Create a new agent
============================================================

Agent name (snake_case): weather_reporter

Describe what this agent should do:
(Be as detailed as you like - what tasks, goals, behaviors?)
Description: Fetches current weather data for cities and provides human-friendly
summaries. Should be able to get temperature, conditions, and forecasts.

LLM model for the generated agent [haiku-latest]:
Output directory path [./agents/weather_reporter]:

----------------------------------------
Agent Configuration Summary:
----------------------------------------
  Name: weather_reporter
  Description: Fetches current weather data for cities and provides...
  LLM Model: haiku-latest
  Output: ./agents/weather_reporter
----------------------------------------

(The builder will determine what tools are needed)

Proceed with agent creation? [Y/n]: y

Starting agent builder...
...
Agent creation complete!

Your new agent is at: /path/to/agents/weather_reporter

Run it with:
  uv run hugin run --task main --task-path ./agents/weather_reporter
```

## CLI Options

```bash
uv run hugin create --help

Options:
  --max-steps MAX_STEPS  Maximum steps for builder agent (default: 30)
  --log-level {DEBUG,INFO,WARNING,ERROR}  Logging level (default: INFO)
```

## Architecture

The Agent Builder uses these tools to generate your agent:

| Tool | Purpose |
|------|---------|
| `generate_config` | Creates the agent configuration YAML |
| `generate_template` | Creates the system prompt template |
| `generate_task` | Creates the main task definition |
| `generate_tool` | Creates tool implementations (Python + YAML) |
| `preview_files` | Shows all generated files for review |
| `write_agent_files` | Writes files to the output directory |

## Notes

- The builder uses **sonnet-latest** for high-quality code generation
- The builder automatically determines what tools your agent needs
- Generated tools include Python syntax validation
- All generated files follow Hugin framework conventions
- Generated agents are immediately runnable
