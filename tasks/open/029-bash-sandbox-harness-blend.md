---
title: Bash sandbox — the harness blend (Phase 4, design-first)
state: OPEN
labels: [design, sandbox, research]
priority: low
---

# Bash sandbox — the harness blend (Phase 4, design-first)

The open question behind the whole bash effort: **are we moving toward a blend of
a Pi-like harness — markdown files + bash — and the traditional tool-calling
setup?** Phase 1 deliberately did not answer it. This is a **design task, to be
written *after* watching real agents use Phases 1–2** — do not build it blind.

**Design source of truth:** task 023 `notes.md` (the full thinking is parked
there — read it first). This task is the pointer so the idea isn't lost when 023
closes.

## The idea

Treat the filesystem as a shared, inspectable medium between framework and agent,
in two directions, with **one direction of authority per object**:

```
/workspace/
  TASK.md          # projected (read-only) — the task definition
  ENVIRONMENT.md   # projected (read-only) — generated from Policy: what's
                   #   installed and what's allowed (so it can't drift)
  memory/*.md      # projected (read-only) — artifacts, insights (grep instead
                   #   of query_artifacts)
  outbox/          # harvested → Artifacts at a boundary (realpath/O_NOFOLLOW)
  common/          # cross-agent hand-offs
  agents/<id>/     # per-agent cwd
```

- **Down (framework → files):** storage is authoritative; files are a *render*,
  regenerated each turn. The projection mount is genuinely read-only, not
  read-only by convention.
- **Up (files → framework):** the filesystem is authoritative for harvested
  things and nothing else writes them.

The invariant (**one writer per object**) is what prevents a month of
storage↔disk reconciliation. Enforce it structurally.

## Open questions to resolve in the design (from notes.md)

- [ ] Does the projection regenerate every turn or only on storage change?
      (Every turn is simpler; measure before optimizing.)
- [ ] Is `ENVIRONMENT.md` generated from the `Policy` object so the agent's map
      of what it may run can't drift from what it actually may run? (Likely yes —
      a hand-written allowlist description will rot.)
- [ ] Does harvest run at the tool-call boundary (faster feedback) or the agent
      boundary (cleaner semantics)?
- [ ] What does the **system prompt** say? The projection and the prompt should
      share a source, or the agent wastes turns on `which`. (Ties to task 024's
      "environment affordance" item.)

## The boundary this must preserve

> **bash for exploration and mechanical work; structured tools wherever the
> framework needs to observe, validate, or persist the result.**

Structured tools keep two advantages bash never gets: typed arguments the model
can't fumble, and results that land in the stack as inspectable interactions
(not an opaque stdout blob `hugin monitor` can't visualize). The end state is NOT
"replace tools with bash". This line should also drive the follow-up to task 005
(which builtins are still worth having).

## Success criteria

- [ ] A written design (in this task folder) answering the open questions, backed
      by observations of real Phase 1–2 agent runs.
- [ ] A decision on scope before any implementation.
