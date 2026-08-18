# Golden-set evaluation of the agent builder

A **maintainer's tool**, not a user's. It measures whether *the agent builder*
generates good agents, which is why it lives here rather than in
`src/gimle/hugin/` — shipping it would put fifteen hardcoded descriptions and a
subprocess driver into every install of Hugin for nobody's benefit.

It exists because every other test in this repo pins *mechanics*: that a check
fires, that a gate refuses, that a file lands. The builder is fundamentally a
model following a prompt, and without this a prompt change cannot be shown to
have helped or hurt.

## Running it

```bash
uv run python -m tests.evals.run --list       # see the cases
uv run python -m tests.evals.run --tag cheap  # smoke test, one case
uv run python -m tests.evals.run --out before.json
```

**It costs real money.** Each case is one complete multi-stage build, so run a
subset unless you mean it.

## Gating a prompt change

The workflow this is built for:

```bash
uv run python -m tests.evals.run --out before.json
# ... change templates/builder_system.yaml ...
uv run python -m tests.evals.run --out after.json --baseline before.json
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
| `built` | The builder produced a directory at all. A refused build leaves nothing — a distinct outcome from a broken one. |
| `validates` | The generated agent passes the same checks as `hugin validate`, i.e. it would actually load. |
| `tools` | How many tools were generated, and whether that meets what the case asked for. |
| `has_task_sequence` | Whether the agent chains tasks — a structural proxy for "is this a pipeline". |
| tokens / elapsed | Read from the builder's *own* traces, via the reader behind `hugin analyze`. |
| `failing_checks` | Which validator checks failed across the run — this is what points at the fix. |

Scoring calls `validate_files` and `analyze_traces` rather than counting
independently, so there stays one definition of "is this agent loadable", and a
scored run also exercises both on real data.

## What it does not score yet

`expect_architecture` is recorded on every case but **not scored**. Architecture
selection is later work and the builder cannot yet be asked for a shape;
`has_task_sequence` is the proxy until then. Recording the intent now means the
golden set will not need rewriting when it lands.

Cost is in **tokens, not currency**. Hugin records what the SDK reported; what a
call actually cost after routing and fallback is the router's to know.

## Layout

| | |
|---|---|
| `golden_set.py` | The fifteen descriptions and what a good answer contains. |
| `harness.py` | Driving one build, scoring it, aggregating, comparing. |
| `run.py` | The CLI wrapper. |
| `test_harness.py` | The cheap parts — scoring, aggregation, comparison — run on every commit. One end-to-end case is marked `slow` and skips without an `ANTHROPIC_API_KEY`. |
