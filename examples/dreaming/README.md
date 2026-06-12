# Dreaming — an agent that wakes up smarter

This example shows the **dreaming** loop: an agent saves what it learns during a
run, an offline "dream" consolidates those scattered notes into durable
**learnings**, and those learnings are injected back into the agent's prompt on
its next run. No retraining — the agent improves by consolidating its own
memory, the way sleep turns the day's experiences into lasting knowledge.

```
  run  ──────▶  episodic memory  ──────▶  dream  ──────▶  learnings
   ▲            (insights it saved)    (consolidate)    (scoped to the config)
   │                                                          │
   └──────────────  injected into the next prompt  ◀──────────┘
```

The agent here is a **travel concierge** for one returning traveler. On its
first run it knows nothing about them. It learns their preferences, dreams, and
on the next run it already knows them.

## The pieces

- **Episodic memory** — the concierge calls `save_insight` whenever the traveler
  reveals a durable preference ("window seats only", "vegetarian"). These are
  ordinary artifacts, scoped by who produced them.
- **The dream** — `hugin dream` replays those insights and distils them into
  `Learning` artifacts, scoped to the `assistant` config.
- **Injection** — the system prompt
  ([templates/assistant_system.yaml](templates/assistant_system.yaml)) contains a
  `{{ learnings }}` block. Any config/task whose template references it receives
  its scoped learnings at render time; one that doesn't is unchanged.

## Try it (needs `ANTHROPIC_API_KEY`)

From the repo root. We keep everything in one storage path so the dream and the
next run can see the first run's memory.

**1. First run — the concierge meets the traveler (and learns).**

```bash
uv run hugin run \
  --task assist --task-path examples/dreaming \
  --storage-path ./storage/dreaming
```

It will handle the request and `save_insight` the preferences it heard. At this
point its system prompt's "What you've learned" section is **empty**.

**2. Dream — consolidate the day's memory into learnings.**

```bash
# Preview without writing anything:
uv run hugin dream --storage-path ./storage/dreaming --config assistant --dry-run

# Then for real:
uv run hugin dream --storage-path ./storage/dreaming --config assistant
```

**3. Next run — the concierge already knows the traveler.**

```bash
HUGIN_CAPTURE_RENDERED_PROMPTS=1 uv run hugin run \
  --task assist --task-path examples/dreaming \
  --storage-path ./storage/dreaming \
  --parameters '{"request": "Plan me a weekend in Rome."}'
```

This time the request says nothing about seats or meals — but the concierge
books a window seat and a vegetarian meal anyway, because the learning is now in
its prompt.

## See the learning land in the prompt

`HUGIN_CAPTURE_RENDERED_PROMPTS=1` records the exact system prompt sent to the
model each turn. Open the run and look at the "What you've learned about this
traveler" section before vs. after the dream:

```bash
uv run hugin monitor --storage-path ./storage/dreaming
# or the terminal browser:
uv run hugin interactive --storage-path ./storage/dreaming
```

You'll see it go from empty to something like:

```
## What you've learned about this traveler
- The traveler prefers window seats; book a window seat by default.
- The traveler is vegetarian; request a vegetarian meal by default.
```

## How the scope works

Learnings are scoped to the **config** that produced the source memories (here,
`assistant`), so they're injected into that config's future runs — not globally.
A learning can also be narrowed to a specific task. Dreaming deliberately
excludes its own past learnings from each new dream, so it consolidates real
experience rather than re-consolidating its own conclusions.

## What's deliberately left out (v1)

The dream self-rates each learning, but those ratings don't yet gate injection
(no correction loop), and the injection budget is a simple top-N. Those are the
natural next steps; the closed loop above is the foundation.

See `tasks/closed/021-dreaming-memory-consolidation.md` for the full design.
