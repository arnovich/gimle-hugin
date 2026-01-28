# RapMachine - AI Agent Rap Battle Arena

RapMachine is a multi-agent rap battle app built on the Hugin framework. Two AI rapper agents, each powered by a different LLM, take turns dropping verses while a judge agent orchestrates the battle and declares a winner. A live XKCD-style dashboard lets you watch it unfold in real time.

## Quick Start

```bash
# Random rapper personalities, each with their own model
uv run hugin app rap_machine -- --random-agents

# Custom topic
uv run hugin app rap_machine -- --random-agents --topic "Space vs Ocean"

# Custom rapper names (uses generic rapper config)
uv run hugin app rap_machine -- --rapper1-name "Cosmic Flow" --rapper2-name "Star Bars"

# With agent monitor for debugging
uv run hugin app rap_machine -- --random-agents --monitor --port 8080

# Override all models
uv run hugin app rap_machine -- --random-agents --model sonnet-latest

# Override individual models
uv run hugin app rap_machine -- \
  --rapper1-model gpt-4o --rapper2-model sonnet-latest --judge-model opus-latest
```

A live dashboard opens automatically in your browser at `http://localhost:8888`. Pass `--no-web` to disable this.

## How a Battle Works

```
CLI invocation
  |
  v
create_battle_session()
  - Loads environment (configs, tasks, templates, tools)
  - Creates Judge agent (only agent created upfront)
  - Stores Battle object + metadata in shared session state
  |
  v
run_battle_simulation() loop
  |
  v
Judge: set_battle_topic (if no --topic given)
  |
  v
Judge: call_rapper(rapper_number=1)  -->  Rapper 1 created on demand
  |                                        via AgentCall interaction
  v
Rapper 1: spit_bars(verse)  -->  verse added to Battle, turn switches
  |
  v
Judge: call_rapper(rapper_number=2)  -->  Rapper 2 created on demand
  |
  v
Rapper 2: spit_bars(verse)  -->  verse added, turn switches, round increments
  |
  v
  ... alternates until max_rounds reached ...
  |
  v
Judge: get_battle_state  -->  sees reached_max_rounds = TRUE
  |
  v
Judge: declare_winner(winner, reasoning)  -->  battle status = FINISHED
  |
  v
Judge: generate_battle_report  -->  static HTML saved to data/rap_battles/reports/
```

After each step the battle state is saved to `storage/rap_machine/live/battle.json`, which the live dashboard polls every 2 seconds.

## Architecture

### Agents

Only the **Judge** agent is created at session start. Rapper agents are created **on demand** when the judge calls the `call_rapper` tool, which returns an `AgentCall` interaction. On subsequent calls to the same rapper, the existing agent is reused so it keeps conversational context.

### Shared State

All agents share battle state through session state namespaces:

- `battles` — the `Battle` object (status, verses, turns, result)
- `battle_metadata` — rapper styles, descriptions, config names

Tools read and write battle state via `get_battle(stack, battle_id)` which retrieves the Battle from the shared namespace.

### Turn Management

The `Battle` class (`arena/battle.py`) is a state machine:

- **WAITING** — initial state, before any verses
- **IN_PROGRESS** — rappers alternate turns (RAPPER_1 / RAPPER_2)
- **FINISHED** — winner declared

`spit_bars` enforces turn order: it checks `battle.is_rapper_turn(agent_id)` before accepting a verse. After each verse, the turn switches. The round counter (`turn_number`) increments when the turn returns from Rapper 2 to Rapper 1.

## Rapper Personalities and Models

When using `--random-agents`, two personalities are randomly selected from the pool below. Each personality has its own default LLM model, creating cross-model battles:

| Personality | Style | Default Model |
|-------------|-------|---------------|
| MC Flow | Smooth, melodic flow with clever wordplay | `sonnet-latest` |
| Rhyme Fire | Aggressive, hard-hitting with powerful metaphors | `gpt-4o-mini` |
| Verse Viper | Lightning-fast delivery with intricate wordplay | `haiku-latest` |
| Beat Boss | Old-school style with rhythm and storytelling | `gpt-4o` |
| Lyric Legend | Conscious rap with philosophical themes | `gpt-4.1-nano` |
| Mic Master | Technical perfectionist with mathematical precision | `gpt-4.1-mini` |

The **Judge** always uses `opus-latest` by default.

Without `--random-agents`, both rappers use the generic `rapper` config with whatever `--model` specifies (default `haiku-latest`).

## Tools

### Rapper Tools

| Tool | Description |
|------|-------------|
| `spit_bars` | Deliver a verse. Enforces turn order, adds verse to battle, switches turn. |
| `builtins.finish` | Signal that the rapper's turn is complete. |

### Judge Tools

| Tool | Description |
|------|-------------|
| `set_battle_topic` | Set the battle topic (if not provided via CLI). |
| `call_rapper` | Create or reuse a rapper agent. Returns an `AgentCall` interaction. |
| `get_battle_state` | Query battle status, verses, turn info, and `reached_max_rounds` flag. |
| `declare_winner` | End the battle and declare a winner with reasoning. |
| `generate_battle_report` | Create a static HTML report of the completed battle. |

## Directory Structure

```
apps/rap_machine/
├── run.py                    # CLI entry point and battle orchestration
├── dashboard.py              # Live XKCD-style HTML dashboard
├── README.md
├── arena/
│   └── battle.py             # Battle state machine (status, turns, verses)
├── artifacts/
│   └── battle_artifact.py    # RapBattleArtifact for persistence
├── components/
│   └── battle_component.py   # Battle renderer for agent monitor UI
├── configs/
│   ├── judge.yaml            # Judge config (opus-latest)
│   ├── rapper.yaml           # Generic rapper config (haiku-latest)
│   ├── mc_flow.yaml          # MC Flow (sonnet-latest)
│   ├── rhyme_fire.yaml       # Rhyme Fire (gpt-4o-mini)
│   ├── verse_viper.yaml      # Verse Viper (haiku-latest)
│   ├── beat_boss.yaml        # Beat Boss (gpt-4o)
│   ├── lyric_legend.yaml     # Lyric Legend (gpt-4.1-nano)
│   └── mic_master.yaml       # Mic Master (gpt-4.1-mini)
├── tasks/
│   ├── battle.yaml           # Rapper task (receive context, spit bars, finish)
│   └── judge_battle.yaml     # Judge task (orchestrate, evaluate, declare winner)
├── templates/
│   ├── rapper_system.yaml    # Rapper system prompt (personality, style)
│   └── judge_system.yaml     # Judge system prompt (criteria, pacing rules)
└── tools/
    ├── spit_bars.py/yaml
    ├── call_rapper.py/yaml
    ├── get_battle_state.py/yaml
    ├── set_battle_topic.py/yaml
    ├── declare_winner.py/yaml
    ├── generate_battle_report.py/yaml
    └── battle_utils.py       # Shared helper for retrieving battle state
```

## Live Dashboard

The live dashboard is a comic-style rap arena page.

The dashboard is a self-contained HTML page served from `data/rap_battles/live/` on port 8888.

## CLI Options

```
--topic TOPIC           Battle topic (default: judge decides)
--rounds ROUNDS         Maximum rounds (default: 8)
--random-agents         Use random rapper personalities with their default models
--rapper1-name NAME     Name of rapper 1 (default: MC Flow)
--rapper2-name NAME     Name of rapper 2 (default: Rhyme Fire)
--model MODEL           Model for all agents (default: haiku-latest)
--rapper1-model MODEL   Override model for rapper 1
--rapper2-model MODEL   Override model for rapper 2
--judge-model MODEL     Override model for judge
--monitor               Also start the Hugin agent monitor
--port PORT             Agent monitor port (default: 8080)
--no-web                Don't open the live dashboard in the browser
--log-level LEVEL       DEBUG, INFO, WARNING, ERROR (default: WARNING)
```

Model precedence: `--rapper1-model` > config default (with `--random-agents`) > `--model` > `haiku-latest`.

## Debugging

```bash
# Run with agent monitor
uv run hugin app rap_machine -- --random-agents --monitor

# Standalone monitor (point at session storage)
uv run hugin monitor --storage-path ./data/rap_battles/sessions --port 8002

# Verbose logging
uv run hugin app rap_machine -- --random-agents --log-level DEBUG
```

The agent monitor shows flowcharts of each agent's interactions, tool calls with parameters and results, and LLM prompts and responses.

## Reports

After each battle a static HTML report is saved to:

- `data/rap_battles/reports/battle_{id}_{timestamp}.html`
- `data/rap_battles/reports/latest.html`

Reports are self-contained and can be opened offline or shared.
