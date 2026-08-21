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

## From a report to a change

`hugin analyze` tells you what happened. `hugin improve` reads the same runs,
reads the agent's own files, and proposes changes:

```bash
uv run hugin improve ./agents/price_agent --storage-path ./storage/price_agent
```

```
2 proposal(s) for ./agents/price_agent:

1. tools/fetch_prices.py  [edit_tool]
   evidence: tools.fetch_prices.error_rate = 1.0
   Every call fails with a 503. The implementation returns a hardcoded
   error rather than fetching anything.

2. templates/price_system.yaml  [edit_template]
   evidence: loops_detected = [{'value': 'fetch_prices', 'count': 3}]
   The template says "if a call fails, try again a couple of times",
   which turns a permanently broken tool into a loop.
```

**It proposes; it never writes.** The task it runs has no write tool at all, so
that is a property of the wiring rather than of the model having behaved. To
act on a proposal, use edit mode — and bound it to the file in question:

```bash
uv run hugin create --edit ./agents/price_agent --only tools/fetch_prices.py \
  --instruction "fetch real prices instead of returning a hardcoded error"
```

### Every proposal has to cite a number

A proposal names a metric from the report, and the citation is checked against
it. A metric that does not exist, or a value that does not match, is rejected
and never recorded — so "cite your evidence" is a constraint rather than a
request. If nothing can be cited, you get no proposals, which is a real answer.

### Why it will not propose "raise the success rate"

`self_reported_success_rate` is refused as evidence even when quoted
accurately. It comes from the agent's own `finish_type`, so the cheapest way to
raise it is for the agent to declare success sooner or do less work. It is
worth reading as a symptom — a run that self-reports failure is worth
investigating — and it is never a target.

### Applying a proposal

`--apply` acts on the proposals and then checks the result:

```bash
uv run hugin improve ./agents/price_agent -s ./storage/price_agent --apply
```

It records how the agent behaves now, makes each edit, replays the same inputs
again, and **reverts everything if any input stopped finishing**:

```
REGRESSED 3008a2061c58  success -> None

Reverted: 1 input(s) stopped finishing.
    restored tasks/check.yaml
```

Five things it will not do:

| | |
|---|---|
| Apply without a baseline | No run history means no way to tell if a change made things worse. It refuses. |
| Apply without showing you | Each edit goes through `hugin create --edit`, which prints a diff and asks. |
| Touch files it did not propose | Each edit is bounded with `--only`. |
| Leave a regression in place | It reverts from a snapshot, which works for unversioned agents too. |
| Call "nothing changed" a success | It hashes the agent, so an edit that wrote no bytes is reported as such. |

**It is deliberately not unattended.** The edit instruction is built from the
model's rationale, which was written while reading trace text that someone
outside your team may have influenced. A human between that prose and a code
change is the point, not an inconvenience.

### Treat the report as data

Traces contain text the agent read, which can include text someone else wrote —
a fetched page, a filename, an error from a remote service. The improve task is
told to treat all of it as quoted data rather than instructions, and it reports
anything that looks like an instruction rather than acting on it.

## Check an edit against real inputs

`hugin replay` re-runs an agent on the task inputs its past runs actually used,
so you can tell whether an edit broke something before your users do.

```bash
# Record how the agent behaves today
uv run hugin replay ./agents/price_agent -s ./storage/price_agent --out before.json

# ... make a change, by hand or with hugin create --edit ...

uv run hugin replay ./agents/price_agent -s ./storage/price_agent --baseline before.json
```

```
738790ad6a03  check                success        2 turns
32352468798e  check                unfinished     7 turns

finished 1/2   self-reported ok 1/2
compared 2 input(s)
REGRESSED 32352468798e  success -> None
```

Inputs are matched by fingerprint, so a comparison across different input sets
tells you what it could not match rather than quietly comparing totals of
different things.

### The verdict is deliberately coarse

An input either finished or it did not. `finish_type` is the agent's own
verdict on itself, so reading it more finely would be reading a self-grade —
and turn counts are shown beside the verdict rather than being part of it,
because "fewer turns" can just mean "did less work".

### A provider outage is not a regression

A run that never reached the agent — an expired key, a rate limit, an
exhausted balance — is excluded from the rates rather than counted as a
failure, and reported separately. Without that, a billing lapse looks
identical to the agent collapsing.

### The harvested inputs are your real data

Replay needs the actual values your users supplied, so unlike `hugin analyze`
it does not redact them. The values stay on your machine: reports quote a short
fingerprint instead, and nothing harvested is ever put into a model's context.
Treat `--workdir` as you would any directory holding production inputs.
