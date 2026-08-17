---
layout: base.njk
title: Measure the Agent Builder
---

# Measure the Agent Builder

`hugin eval` runs the agent builder against a fixed set of descriptions and
scores what it produced. It exists because every other test in this repo pins
*mechanics* — that a check fires, that a gate refuses — while the builder is
fundamentally a model following a prompt. Without this, a prompt change cannot
be shown to have helped or hurt.

```bash
hugin eval --list                  # see the cases
hugin eval --tag cheap             # smoke test, one case
hugin eval --out before.json       # full run, recorded
```

**It costs real money.** Each case is one complete multi-stage build, so run a
subset unless you mean it.

## Gating a prompt change

The workflow the harness is built for:

```bash
hugin eval --out before.json
# ... change templates/builder_system.yaml ...
hugin eval --out after.json --baseline before.json
```

which prints what moved:

```
    vs baseline:
      validation_rate: 0.6 -> 0.9 (+0.3)
      output_tokens: 41200 -> 38100 (-3100)
```

## What it scores

| | |
|---|---|
| **built** | The builder produced a directory at all. A refused build leaves nothing — a distinct outcome from a broken one. |
| **validates** | The generated agent passes `hugin validate`, i.e. it would actually load. |
| **tools** | How many tools were generated, and whether that meets what the case asked for. |
| **has_task_sequence** | Whether the agent chains tasks — a structural proxy for "is this a pipeline". |
| **tokens / elapsed** | Read from the builder's *own* traces via `hugin analyze`. |
| **failing checks** | Which validator checks failed across the run — this is what points at the fix. |

## What it does not score yet

`expect_architecture` is recorded on every case but **not scored**. Architecture
selection is later work, and the builder currently has no way to be asked for a
shape. Capturing the intent now means the golden set will not need rewriting
when it arrives.

Cost is reported in **tokens, not currency**. Hugin records what the SDK
reported; what a call actually cost after routing and fallback is something the
router knows and Hugin does not.
