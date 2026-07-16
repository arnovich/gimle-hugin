---
title: Bash sandbox — serious end-to-end test harness across all backends
state: OPEN
labels: [testing, sandbox]
priority: high
---

# Bash sandbox — end-to-end test harness across all backends

**Do not start until the backends are finished** (local ✓, docker ✓, ssh pending
— task 026; background exec — task 027). Placeholder to capture the intent now so
it isn't lost. Deferred by explicit decision (2026-07-16).

## Why

Each backend has its own tests, but the payoff is a **single behavioural
contract test** run against *every* backend (`local`, `docker`, `ssh`) so they
are provably interchangeable — the whole thesis is "the runtime you choose is the
boundary; the config doesn't otherwise change." Today the docker containment
tests and the local tests are written separately; there is no one suite that
asserts identical agent-visible behaviour across backends, nor a realistic
full-loop (agent → tool → sandbox → result) drive on each.

## Scope to plan (when picked up)

- **A backend-parametrized contract suite** — one set of behaviour tests
  (`pytest.mark.parametrize` over available backends, each skipped if its runtime
  is absent): command runs, non-zero exit is data, timeout is an error, output
  truncation + spill, per-agent/branch workspace isolation, `common/` hand-off,
  policy denial, the **containment gate** (`python3 -c 'os.system("id")'` runs but
  is contained — asserted per backend's boundary), file put/get confinement.
- **Full-loop E2E** — drive a real `Session`/`Agent` with a scripted model
  (like `test_bash_example.py`) on each backend, not just the sandbox in
  isolation, so `execute_tool` injection, per-spec ownership, and `Session.close`
  teardown are exercised end to end.
- **Lifecycle/leak assertions** — after each run assert no leaked containers /
  remote jobs / workspaces (clean AND simulated-abrupt exit), and that the reaper
  self-heals an abandoned resource for every backend.
- **Multi-agent / multi-spec** — two agents with different specs in one session
  get the isolation each asked for; branches don't collide.
- **CI story** — docker/ssh gates need a daemon / a disposable box; decide
  matrix vs. nightly vs. manual-gated, and make the default `local` path always
  run. (See task 025's daemon-gated pattern and task 026's containment gate.)
- **Fault injection** — daemon down / image missing / network partition
  (ssh) all surface as a clean, non-retryable `infra_error` to the model, not a
  hang or crash (regression coverage for the panel findings).

## Cross-refs

Backends: local (shipped), docker (task 025, PR #62), ssh (task 026). Reaper
generalization (024/030). Panel findings the harness should guard against live in
tasks 024 and 030.
