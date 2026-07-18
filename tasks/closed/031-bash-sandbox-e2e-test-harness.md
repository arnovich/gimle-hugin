---
title: Bash sandbox — serious end-to-end test harness across all backends
state: DONE
labels: [testing, sandbox]
priority: high
---

# Bash sandbox — end-to-end test harness across all backends

**Precondition met (2026-07-16): all three backends are landed** (local ✓,
docker ✓ PR #62, ssh ✓ PR #63). Started. Background exec (task 027) only affects
the persistent-shell scenarios, not the core contract, so the harness does not
wait on it.

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
  truncation + spill, per-agent/branch workspace isolation,
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

## Plan (v1 — this branch)

The centerpiece is one **behaviour contract parametrized over backends**, with
`local` always running and `docker`/`ssh` gated (skipped when the runtime is
absent) and `slow`-marked. Delivered here:

- `tests/test_sandbox_contract.py` — a `contract_backend` fixture parametrized
  `[local, docker(slow), ssh(slow)]`, each param skipped if its runtime is
  unavailable (`local` always; `docker` via a reachable daemon; `ssh` via
  `HUGIN_SSH_TEST_HOST`). One `TestBackendContract` asserting identical
  agent-visible behaviour: a command runs and returns stdout, a non-zero exit is
  *data* (no raise), a wall-clock overrun is `timed_out` (not a raise), output
  truncation sets `truncated` and spills the full output to a cwd-relative
  `.hugin/last_output.txt` the next command can read, two `(agent, branch)` pairs
  get isolated non-colliding workspaces, a policy-denied command raises
  `PolicyDenied` without running, an interpreter (`python3 -c 'os.system("id")'`)
  is **not denied** (the thesis: policy is a seatbelt, not the boundary), and
  `put_file`/`get_file` round-trip while a `..` path is refused. Plus an
  `isolating_backend` fixture (`docker`, `ssh` only) asserting the *containment*
  half of the gate that legitimately differs from `local`: a host secret outside
  the workspace is unreachable.
- `tests/test_bash_e2e_backends.py` — the full loop (real `Session`/`Agent` +
  scripted no-API model, extending `test_bash_example.py`) parametrized over the
  same backends, so `execute_tool` injection, per-spec ownership
  (`session.sandboxes`), and `Session.close` teardown are exercised end to end,
  not just the sandbox in isolation. Includes a local-only two-spec/two-agent
  routing test (each agent gets the isolation its own config asked for).
- Fault injection: a stub backend that raises on `start()` proves the bash tool
  maps a backend-bring-up failure to a clean, non-retryable `infra_error`
  (regression guard for the docker/ssh panel findings) — no runtime needed.

## Panel review (2026-07-16)

Reviewed by a three-judge panel (test-quality / framework-maintainer /
CI-release). Load-bearing findings fixed before merge:

- **Truncation test proved the flag, not the truncation** — a backend that set
  `truncated=True` but returned the full output would have passed. Now asserts
  the returned view is actually shortened (`"x"*300 not in result.stdout`), and
  the generator is coreutils (`head -c … | tr`) not python, so it runs on a
  minimal remote box.
- **`docker_available()` didn't check the image was pulled** — a daemon-up but
  image-absent CI box would *error* at `start()` instead of skipping, breaking
  the "green everywhere" promise. The gate now also requires the image present.
- **`python3` assumed on every backend** — the interpreter-not-denied test now
  probes and skips on a box without python3 (the ssh baseline is bash+coreutils).
- **Marker taxonomy** — both new suites now carry `pytestmark = integration`, so
  `-m integration` no longer silently skips them; `slow` still rides the
  docker/ssh params.
- **`_ScriptedModel` was triplicated** — hoisted one `ScriptedToolModel` into
  `conftest.py`; the two bash suites and `test_bash_example.py` share it.
- Smaller: two-spec test now asserts distinct spec keys + distinct backend
  objects (the real per-spec guarantee) rather than relying on the per-agent
  marker split; fault-injection test asserts `is_error` and the *intent* of the
  note rather than its exact wording; registry registrations moved inside
  `try/finally`; per-backend containment classes point at the contract suite as
  the canonical interchangeable assertion.

The CI crux was verified empirically: 20 docker/ssh params carry `slow`, `0`
leak into a `-m "not slow"` run, and local always runs.

## Deferred (follow-ups, noted not built here)

- Real-container/remote **leak & reaper self-heal** assertions on a
  simulated-abrupt exit already exist per-backend (docker lifecycle tests, ssh
  TTL sweep); a unified cross-backend leak sweep waits on the reaper
  generalization (024/030) so it has one seam to drive.
- **Run all three backends for real — locally (2026-07-16).** A coverage audit
  showed CI was only truly exercising the `local` backend: `docker.py` sat at
  41% in CI (its container-boundary tests are daemon-gated and the self-hosted
  Hetzner runner has **no docker** — `docker: command not found`), and ssh's real
  remote path was 0% automated anywhere. Landed a **reusable local harness** so a
  developer with docker runs all three for real: a throwaway sshd container
  (`docker/ssh-test.Dockerfile`) reached via a new `port` field on the ssh spec,
  wired into the real-host fixture and the contract/e2e opts via
  `HUGIN_SSH_TEST_{HOST,PORT,KEY}`; `docker/README.md` documents the three
  commands. Validated: **1012 passed** with the container up (vs 976 in CI, where
  docker/ssh skip). **Wiring this into CI is deferred** — it needs a runner with
  docker (install docker on the Hetzner runner, or a GitHub-hosted job); the
  mechanism degrades gracefully either way. Also still deferred: a **real
  mid-command partition** test for ssh (kill sshd mid-command → assert
  do-not-retry) — the logic is already unit-tested via the mocked `_run` seam.
- **Per-test wall-clock timeout** (panel, LOW). No `pytest-timeout` is installed,
  so a wedged docker daemon on a `slow` run could hang the job (the sandbox exec
  paths self-bound, but `containers.run` at `start()` does not). Add a
  `pytest-timeout` dev dependency + a timeout on the slow params if docker/ssh
  ever join CI.

## Cross-refs

Backends: local (shipped), docker (task 025, PR #62), ssh (task 026, PR #63).
Reaper generalization (024/030). Panel findings the harness guards against live
in tasks 024 and 030.
