---
title: Bash sandbox — per-agent persistent shell (deferred from 027)
state: OPEN
labels: [enhancement, sandbox, usability]
priority: medium
---

# Bash sandbox — per-agent persistent shell

Deferred out of task 027 (background exec). v1 ships the **honest-stateless**
contract: each `bash` call is a fresh shell, so `cd`/`export`/`source` and a
background job's cwd/env do **not** persist — the tool description says so in
bold, and `cd` is never an allowed silent no-op. This task makes state actually
persist within an agent's session.

**Source of truth:** task 023 `spec.md` §9 (Statefulness); the 027 design note
(`tasks/closed/027-.../design.md`, "Statefulness — defer the persistent shell").

## Why it was deferred (the crux to resolve)

A persistent shell (a pexpect/coprocess long-lived shell, one per
`workspace_for(agent, branch)`, *inside* the disposable container/remote) makes
`cd`/`export`/`source` behave as the model expects — resolving the
security-vs-usability tension (persistent shell, disposable runtime). But it has
a **real tension with background exec** that must be designed for, not bolted on:

- A persistent shell is **serial** — one ordered command at a time.
- Background exec (027) wants **concurrent** commands from one agent (start a
  build, keep working).
- So a backgrounded command *in* the persistent shell holds the shell until it
  finishes; the agent can't run a second command meanwhile.

**The central design question:** how do the persistent (stateful, serial)
foreground shell and the (concurrent, one-shot) background jobs coexist? Likely
answer to evaluate: a persistent shell for foreground/stateful commands + a
separate pool of one-shot execs for `background:true` jobs (which then do NOT see
the persistent shell's cd/env — document that clearly). Decide and sign off
before building, like 026/027.

## Tasks (to refine in a design note first)

- [ ] Design note: the serial-shell-vs-concurrent-background reconciliation;
      per-backend feasibility (local coprocess; docker `docker exec` into a
      persistent shell process; ssh a persistent remote shell over the
      ControlMaster); shell-death recovery; output framing (knowing where one
      command's output ends); lifecycle in the reaper; sign-off.
- [ ] Per-agent persistent shell inside the runtime; `cd`/`export`/`source`
      persist across foreground calls.
- [ ] Reconcile with background exec per the design (state whether a background
      job inherits the persistent shell's state, or is a clean one-shot).
- [ ] Output framing / robustness (a sentinel between commands, like the ssh
      backend already uses; recover if the shell dies).
- [ ] Update the tool description: which state persists and which does not.
- [ ] Tests against `FakeSandbox` (state persists across calls) + a real-backend
      gate.

## Success criteria

- [ ] Within one agent's session, `cd foo` then a later `bash` call runs in `foo`
      (and `export X=1` is visible later), on at least the `local` backend.
- [ ] The background-exec contract (027) still holds — a long backgrounded
      command does not freeze siblings, and the foreground/background state
      relationship is documented and tested.
- [ ] The stateless-vs-stateful contract in the tool description is accurate.

## Cross-refs

Background exec (027, PR #65) — the tension source. Design in the 023 folder
(`tasks/closed/023-bash-tool/spec.md` §9). The ssh backend's completion sentinel
(`tasks/closed/026-.../design.md`) is a reusable pattern for output framing.
