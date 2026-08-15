---
layout: base.njk
title: Use the Agent Creator
---

# Use the Agent Creator

The Agent Creator is an interactive wizard that generates a complete agent for you. Instead of manually creating files, you describe what you want and let AI design the tools and configuration.

## What is the Agent Creator?

The creator is a meta-agent that:
1. Takes your description of what you want the agent to do
2. Designs appropriate tools for that purpose
3. Generates all the necessary files (config, task, template, tools)
4. Creates a ready-to-run agent directory

It uses `sonnet-latest` by default for generation, as this model excels at code generation tasks.

## Step 1: Start the Wizard

```bash
hugin create
```

The wizard will guide you through several prompts.

### Running it without prompts

Every prompt has a flag, so a build can be scripted or run in CI:

```bash
hugin create --yes \
  --name weather_assistant \
  --description "Look up forecasts and advise on what to wear" \
  --output ./agents/weather_assistant
```

`--yes` requires `--name` and `--description`; everything else falls back to a
default. Other flags: `--model` (the generated agent's model),
`--builder-model` (the model that does the building), and `--stub-tools`,
which emits tool signatures raising `NotImplementedError` instead of generated
bodies — better than plausible-looking code for anything that needs an API key
you have to wire in yourself.

### What you get

Alongside `configs/`, `tasks/`, `templates/` and `tools/`, the generated
directory contains:

- `BUILD_REPORT.md` — what was asked for, the tools and tasks that were built,
  the exact command to run it, and any validator warnings.
- `requirements.txt` — third-party imports read out of the generated code, if
  there were any. They are *observed*, not verified: the names come from
  generated code, so check them before installing.

If a build fails validation, nothing is written to the target directory.
The payload is instead written to `<output>.rejected/` with a
`VALIDATION_REPORT.md` explaining what was wrong; fix it and re-check with
`hugin validate <path>`.


## Step 2: Enter Agent Name

```
? Agent name: weather_assistant
```

**Requirements:**
- Must use `snake_case` (lowercase with underscores)
- Should be descriptive of what the agent does
- Examples: `code_reviewer`, `data_analyst`, `email_helper`

## Step 3: Describe What Your Agent Should Do

```
? What should this agent do?
> Help users check weather forecasts. It should be able to look up current
> weather and forecasts for any city, and provide helpful advice about
> what to wear or whether to bring an umbrella.
```

**Tips for good descriptions:**
- Be specific about the agent's purpose
- Mention what actions/capabilities it needs
- Include any constraints or personality traits

| Vague | Better |
|-------|--------|
| "Help with weather" | "Look up current weather and 5-day forecasts for any city, provide clothing recommendations" |
| "Do data stuff" | "Read CSV files, calculate statistics, generate summary reports with charts" |
| "Research agent" | "Search the web for information, summarize findings, cite sources" |

## Step 4: Choose the LLM Model

```
? LLM model for the agent: haiku-latest
```

The model your *created agent* will use (not the creator itself).

Hugin supports models from three providers:

| Provider | Requires |
|----------|----------|
| **Anthropic** | `ANTHROPIC_API_KEY` |
| **OpenAI** | `OPENAI_API_KEY` |
| **Ollama** | Local Ollama installation |

The wizard lists the models it actually has, read from
`model_registry.py` at the time you run it. This page used to restate that
list, which meant it was wrong from the first model anyone added — so it no
longer does. The default is `haiku-latest`: fast, and good enough for most
agents.

**See all available models:** Check [`src/gimle/hugin/llm/models/model_registry.py`](https://github.com/gimlelabs/gimle-hugin/blob/main/src/gimle/hugin/llm/models/model_registry.py) for the complete list of pre-configured models.

**Adding custom models:** To add a new model, edit `model_registry.py` and register it with the appropriate provider class (`AnthropicModel`, `OpenAIModel`, or `OllamaModel`).

## Step 5: Choose Output Directory

```
? Output directory: ./agents/weather_assistant
```

The default pattern is `./agents/{agent_name}`. You can change this to any path.

## Step 6: Review and Confirm

The wizard shows a summary:

```
Summary:
  Name: weather_assistant
  Description: Help users check weather forecasts...
  Model: haiku-latest
  Output: ./agents/weather_assistant

? Create this agent? Yes
```

Review the details and confirm to start generation.

## Step 7: Wait for Generation

```
Creating agent 'weather_assistant'...
  Designing tools...
  Generating tool implementations...
  Creating configuration files...
  Writing files...
Done!
```

The creator:
1. Analyzes your description to determine needed tools
2. Designs tool parameters and implementations
3. Creates a system template with appropriate instructions
4. Generates config and task files
5. Writes everything to the output directory

## Step 8: Run Your New Agent

After generation completes, the wizard asks if you want to run the agent immediately:

```
Agent created successfully!

? Run the agent now? Yes
```

If you select **Yes**, the wizard will prompt you for any required task parameters and then start the agent. No need to copy-paste commands.

To run the agent later:
```bash
hugin run --task main --task-path ./agents/weather_assistant
```

## Understanding the Generated Files

The creator produces a standard agent directory:

```
weather_assistant/
├── configs/
│   └── weather_assistant.yaml    # Agent configuration
├── tasks/
│   └── main.yaml                 # Default task
├── templates/
│   └── weather_assistant.yaml    # System prompt
└── tools/
    ├── get_weather.py            # Tool implementation
    ├── get_weather.yaml          # Tool definition
    ├── get_forecast.py
    └── get_forecast.yaml
```

## Customizing the Generated Agent

The generated files are a starting point. Common customizations:

### Change the System Prompt

Edit `templates/{name}.yaml` to adjust personality or add instructions:

```yaml
template: |
  You are a friendly weather assistant.

  Always include temperature in both Celsius and Fahrenheit.
  Be encouraging about outdoor activities when weather permits.
  ...
```

### Modify Tool Behavior

Edit the Python files in `tools/` to change how tools work:

```python
def get_weather(stack, city: str) -> str:
    # Replace simulated data with real API calls
    response = requests.get(f"https://api.weather.com/{city}")
    return response.json()
```

### Add More Tools

Create new `.py` and `.yaml` pairs in `tools/`, then add them to the config:

```yaml
tools:
  - builtins.finish:finish
  - get_weather:get_weather
  - get_forecast:get_forecast
  - new_tool:new_tool  # Add your new tool
```

### Change the Default Task

Edit `tasks/main.yaml` to change the initial prompt or add parameters:

```yaml
name: main
description: Check weather for a location
parameters:
  location:
    type: string
    description: City to check weather for
    required: true
prompt: |
  Check the weather for {{ location }} and give me a summary.
```

## Next Steps

- [Create an Agent](/how-to/create-agent/) - Learn manual agent creation for full control
- [Use the Monitor](/how-to/use-monitor/) - Debug your agent's execution
- [Tools](/concepts/tools/) - Understand tool development in depth
