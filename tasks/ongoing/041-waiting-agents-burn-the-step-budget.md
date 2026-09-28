---
title: A waiting agent spins the session loop and rewrites all storage each pass
state: ongoing
claimed_by: codex/task041
claimed_at: 2026-09-28T10:44:00Z
branch: task/041_waiting_scheduler
priority: high
labels: [bug, runtime, performance]
related: ["038"]
---

# A waiting agent spins the session loop and rewrites all storage each pass

## Context

`Session.run` (`agent/session.py:207-231`) is an uncapped loop: step every
agent, then `self.storage.save_session(self)`, then repeat. There is no sleep
and no backoff anywhere in `agent/` — `grep sleep` finds only the interactive
paths in `cli/run_agent.py`, and `--step-delay` defaults to `0.0`
(`cli/run_agent.py:736-740`).

`Waiting.step()` returns `True` while its condition holds
(`interaction/waiting.py:72-77`). `Session.run` reads any `True` as activity,
so a waiting agent keeps the loop hot and increments `step_count` on every
pass (`:220`).

Two consequences, both bad, and both currently reachable with the `heartbeat`
example and any `wait_for_seconds` condition:

**Storage write amplification.** `save_session` cascades to `save_agent` per
agent, which saves **every interaction in the stack** (`storage/storage.py:219-227`,
`:254-264`), each a separate `json.dump` in `LocalStorage`
(`storage/local.py:192-196`). Twenty agents carrying two hundred interactions
each is on the order of four thousand object writes per loop iteration, run
flat out for the duration of the wait. On a local disk this is merely wasteful;
on any network-backed or shared storage it is a sustained write storm and, on
metered object storage, a real bill for an agent doing nothing.

**The step budget measures the wrong thing.** `--max-steps` defaults to 100
(`cli/run_agent.py:729-733`) and counts loop iterations, not LLM calls. A
wait of any realistic duration exhausts the entire budget in milliseconds, and
the run exits reporting "maximum steps reached" before the thing being waited
on could physically have happened. A run's step count therefore means something
different depending on how much it waited, which makes it useless as a cost
control.

Found during the panel review of task 038, where a wall-clock deadline on a
parked agent is load-bearing — but neither defect is specific to that task.

## Outcome

- [x] A parked agent does not keep the session loop hot: with every agent
      waiting, the loop sleeps until the nearest wake time rather than spinning.
- [x] A waiting agent performs no storage writes per pass. A test asserts that
      an agent waiting N seconds performs fewer than a stated small number of
      storage operations and zero LLM calls.
- [x] A wait longer than the default `--max-steps` completes rather than
      terminating the run.
- [x] `save_session` does not rewrite unchanged agents and interactions.
- [x] The budget that bounds cost counts LLM calls; any iteration counter is a
      separate, clearly-named guard.

## Notes

- A likely shape: a third outcome from `step()` — "idle, earliest wake at T" —
  distinct from both "did work" and "done", which `Session.run` can aggregate
  into a sleep. That also gives a scheduler somewhere to read a deadline from
  without evaluating a condition.
- Task 038 depends on this. Its board-polling design is only affordable if a
  parked agent is cheap, and its `(n, deadline)` completion policy cannot be
  demonstrated at realistic deadlines until this is fixed.
- Any test written for a wait must use a realistic deadline; a sub-second
  deadline passes green while hiding exactly this defect.

## Plan

- Preserve the boolean stepping API, expose condition wake deadlines, and let
  session and CLI runners sleep when a pass contains only parked branches.
  Poll custom conditions at a bounded interval; never evaluate a condition
  twice merely to inspect scheduling state. Persist completed waits so they
  cannot restart after another branch continues.
- Deduplicate serialized storage records, including nested mutations and
  deletion/recreation, while preserving cascaded saves of changed children.
- Count LLM attempts immediately before provider execution and enforce a
  session-wide call limit across all agents and branches. Make max_steps a
  compatibility alias for max_llm_calls; expose max_iterations separately.
  Allow deterministic completion after the last permitted model call.
- Cover realistic waits, nearest deadlines, zero idle writes/model calls,
  nested storage mutations, failed writes and deletion, exact call limits,
  multiple agents/branches, and the delegated builder path. Run focused tests,
  full pytest and pre-commit checks before an independent review panel.

## Integration verification

The PR branch includes the reviewed 039 and 040 branches. Merge PR #140,
then #141, then this scheduler PR. The two runtime conflicts preserve inbox
wake/successor progress and the per-call budget guard.

Combined full suite: **1,814 passed, 53 skipped**. Independent integration
review passed all 53 focused tests, including a 120-second wait with three
queued messages, a zero-call budget, fresh disk reload, and one-call resumed
delivery. Changed-file/commit hooks passed; all-file hooks retain unrelated
baseline findings. The final branch source and tests exactly match the tested
integration tree.

## Conversation

### note · codex/task041 · 2026-09-28T10:44:00Z

Claimed to implement, test, and panel-review a separate PR; merge awaits owner review.


## Validation

- Full suite: `TMPDIR=/private/tmp uv run pytest -x -q` — 1780 passed,
  53 skipped. Includes a real two-second wait, simulated 120/180-second
  deadlines, bounded background/custom polling, unchanged storage writes,
  nested mutations and pandas inputs, and exact shared call limits.
- Public CLI dispatch preserves zero-call budgets and forwards the separate
  iteration guard. TUI tests cover generated children, exact budgets,
  pause/single-step, paused siblings/descendants, and runner ownership.
- Changed-file pre-commit checks pass after formatting. All-file checks retain
  pre-existing failures in unrelated files (flake8 docstrings, the missing
  return annotation in `scripts/sync_packaged_examples.py`, and four existing
  detect-secrets test fixtures); no checks were bypassed.

## Review

The independent correctness/security, compatibility, and maintainability panel
found two initial blockers and three compatibility gaps. All were fixed:

- Scope TUI execution to the selected root and descendants, preserve individual
  pause controls, and reject a second session runner without replacing its
  budget. Log an actionable warning when another controller already owns it.
- Compare canonical persisted JSON snapshots instead of arbitrary-object
  equality, including unchanged and mutated pandas DataFrames.
- Expose the new budget flags through the public CLI and preserve zero values.
- Include background bash waits in idle scheduling and bounded polling.
- Drain ready deterministic work after the final permitted call while leaving
  budget-blocked oracle branches resumable.

The judges approved the revised implementation with no remaining blockers.
The task stays ongoing pending its PR and integration with tasks 039 and 040.

### note · codex/task041 · 2026-09-28T11:45:09Z

Integration and independent panel complete; preparing the stacked PR after #140 and #141.
