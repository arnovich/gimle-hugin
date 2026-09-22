---
title: A waiting agent spins the session loop and rewrites all storage each pass
state: open
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

- [ ] A parked agent does not keep the session loop hot: with every agent
      waiting, the loop sleeps until the nearest wake time rather than spinning.
- [ ] A waiting agent performs no storage writes per pass. A test asserts that
      an agent waiting N seconds performs fewer than a stated small number of
      storage operations and zero LLM calls.
- [ ] A wait longer than the default `--max-steps` completes rather than
      terminating the run.
- [ ] `save_session` does not rewrite unchanged agents and interactions.
- [ ] The budget that bounds cost counts LLM calls; any iteration counter is a
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
