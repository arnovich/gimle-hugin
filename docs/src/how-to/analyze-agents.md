---
layout: base.njk
title: Analyze an Agent's Runs
---

# Analyze an Agent's Runs

`hugin analyze` reads runs an agent has already done and reports what went
wrong. It reads storage only — **no model is called**, so it costs nothing to
run and works on any agent, generated or hand-written.

```bash
hugin analyze --storage-path ./storage/financial_newspaper
```

Or point it at an agent directory and let it guess:

```bash
hugin analyze ./agents/my_agent
```

## What it reports

| | |
|---|---|
| **finished / unfinished** | Runs whose root task reached a terminal `TaskResult` versus ones that just stopped. A branch finishing or a task chaining onward is not the whole run finishing. |
| **self-reported ok** | The share of finished runs the agent called a success. |
| **model turns** | p50 / p90 / max. A rising p90 usually means the agent is flailing rather than working. |
| **output tokens** | Total and per run. |
| **unrendered `{{ }}`** | Turns whose prompt still contained Jinja — a template reference that never resolved. Only visible if the run had `HUGIN_CAPTURE_RENDERED_PROMPTS=1`. |
| **per-tool** | Calls, errors, error rate, largest result, and the most common error signatures. |
| **never called** | Tools the config granted that no run ever used. |
| **looping** | A tool called with identical arguments repeatedly on one branch of a run. |
| **oversized results** | Tool results large enough to be a design problem — every byte is re-sent to the model on every later turn. |

## Reading the numbers honestly

**`self-reported ok` is the agent's own verdict.** It comes from the
`finish_type` the agent passed to `finish`, not from any independent check of
its output. Anything that optimises this number can win by declaring success
more readily, so treat it as a signal, not a score. The report says so in its
own output.

**A small sample proves little.** In particular, "never called" over a handful
of runs is not evidence a tool is dead — it may serve a rare branch. Deleting on
that basis is a regression with no signal behind it.

## What it does not include

Traces are stored verbatim: raw tool arguments, raw error strings, and — with
`HUGIN_CAPTURE_RENDERED_PROMPTS=1` — the full rendered prompts. That makes a
storage directory sensitive.

So the report deliberately never contains tool argument values (they are hashed,
which is all loop detection needs), never contains result bodies (only their
size), and reduces error messages to *signatures*: the exception shape with
values masked out. Masking is what makes identical failures countable, and the
values are exactly where credentials live. Credential-shaped strings are
additionally redacted before anything is printed.

`--json` emits the same report as JSON, for feeding somewhere else.
