---
layout: base.njk
title: Dreaming
---

# Dreaming — agents that wake up smarter

Dreaming is Hugin's offline **memory consolidation** loop. An agent runs
normally and saves what it learns as artifacts (episodic memory). Later, a
separate *dream* pass replays those scattered artifacts and distils them into
**`Learning` artifacts** — durable, prose lessons scoped to the config/task
that produced them. On the agent's next run, the relevant learnings are
injected straight into its system prompt.

No retraining; the agent improves by consolidating its own memory, the way
sleep turns the day's experiences into lasting knowledge.

```
  run  ──────▶  episodic memory  ──────▶  dream  ──────▶  learnings
   ▲            (insights it saved)    (consolidate)    (scoped to the config)
   │                                                          │
   └──────────────  injected into the next prompt  ◀──────────┘
```

## The three pieces

### 1. `Learning` artifact

A new artifact type that represents *semantic* memory — the consolidated
takeaway rather than the raw experience. It carries:

| Field | Purpose |
|-------|---------|
| `content` | The lesson, written as prose ready to drop into a prompt |
| `scope_config` / `scope_task` | Who the lesson applies to |
| `source_artifact_ids` | The episodic artifacts it was distilled from (evidence) |
| `confidence` | The dream's self-assessed confidence in the lesson |
| `derived_from` | Marker (`"dream"`) used to keep dreams from eating their own output |

It's registered alongside `Text`/`Code` and stored like any other artifact, so
the existing query/feedback machinery works on it for free.

### 2. The dream

A specialised Hugin agent that reads episodic artifacts grouped by their
producing `(config, task)`, finds patterns, and writes new `Learning` artifacts
back to storage. It runs offline, triggered by the `hugin dream` CLI command —
not as part of the hot path, so it never slows down a normal run.

The dream provenance-resolves artifacts by walking persisted agents *forward*
(each agent record holds its config and its ordered interaction UUIDs), so it
works **retroactively** on every artifact already in storage — not just ones
created after dreaming shipped.

### 3. Render-time injection

The prompt renderer exposes a `{{ learnings }}` template variable. At render
time it fetches the `Learning` artifacts scoped to the current agent's config
(and current task, if scoped that narrowly), and substitutes them in. The
injected text is treated as a literal value, so a learning that happens to
contain `{{ … }}` is rendered verbatim rather than re-evaluated.

A template that doesn't reference `{{ learnings }}` is **byte-for-byte
unchanged** — opting in is local to a single template.

## Opting a config in

Add `{{ learnings }}` somewhere in your system template:

```yaml
# templates/assistant_system.yaml
name: assistant_system
template: |
  You are a personal travel concierge for one returning traveler.

  ## What you've learned about this traveler
  {{ learnings }}

  Whenever the traveler reveals a durable preference, record it with
  `save_insight` so you can serve them better next time.
```

On the agent's first run the section is empty. After a dream pass over its
saved insights, the next run renders something like:

```
## What you've learned about this traveler
- The traveler prefers window seats; book a window seat by default.
- The traveler is vegetarian; request a vegetarian meal by default.
```

## Running a dream

```bash
# Consolidate every config scope found in a storage path
uv run hugin dream --storage-path ./storage

# Just one config, without persisting (preview)
uv run hugin dream --storage-path ./storage --config assistant --dry-run

# Just one task
uv run hugin dream --storage-path ./storage --task assist
```

The dream itself is bounded by `--max-steps` and picks an LLM via `--model`,
exactly like `hugin run`. Because it reuses the existing storage layer, the
same `--storage-path` you pass to a run is what the dream consolidates over —
and what the next run injects from.

## Seeing the loop work

Set `HUGIN_CAPTURE_RENDERED_PROMPTS=1` on a run and the rendered system prompt
(injection and all) is captured into each `OracleResponse` and visible in the
monitor:

```bash
HUGIN_CAPTURE_RENDERED_PROMPTS=1 uv run hugin run \
  --task assist --task-path examples/dreaming \
  --storage-path ./storage/dreaming

uv run hugin monitor --storage-path ./storage/dreaming
```

That's the audit trail for the closed loop: you can see, turn by turn, exactly
which learnings reached the model.

## Scope

Learnings are **scoped** to where they came from, not global:

- A learning whose source artifacts were produced by config `assistant` is
  injected into future runs of `assistant`. It will not affect any other
  config.
- A learning can be narrowed further to a specific `task`, so it only applies
  when that task is being executed.

This keeps the blast radius of any individual learning small, which matters
because the loop is autonomous — there is no human-in-the-loop step between
"the dream produced this learning" and "the next run sees it in its prompt".

## Guardrails

The autonomy is bounded by three mechanical guardrails, not by approval steps:

- **No dreams-eating-dreams.** Each dream excludes prior `Learning` artifacts
  from its input. Consolidation runs on real experience, not on its own past
  conclusions — otherwise small errors would amplify across cycles.
- **Injection budget.** The selector caps how many learnings can land in a
  prompt (top-N by rating and recency), so prompts can't grow unboundedly
  across dream cycles.
- **Scope.** Per-config / per-task scoping keeps a bad learning from
  contaminating unrelated agents.

The dream also self-rates each learning it produces (via `ArtifactFeedback`,
`source="agent"`), creating a quality signal that the selector can use. A
correction loop that gates injection on independent ratings is a natural next
step but isn't part of v1.

## See also

- The working [`examples/dreaming`](https://github.com/gimlelabs/gimle-hugin/tree/main/examples/dreaming)
  example — a travel concierge that learns about a returning traveler across
  runs.
- [Stacks & Interactions](/concepts/stacks/) — the episodic memory dreaming
  consolidates over.
- [Tools](/concepts/tools/) — `save_insight` is how an agent contributes to
  episodic memory; `save_learning` is how the dream contributes to semantic
  memory.
