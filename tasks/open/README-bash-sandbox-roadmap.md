# Bash sandbox — roadmap index

The bash tool lets a Hugin agent run shell commands through a pluggable
execution sandbox. It ships in phases so each is independently reviewable. The
full design lives in the **task 023 folder** (`spec.md` / `plan.md` / `notes.md`
/ `review.md`) — read that for rationale; the tasks below are the actionable,
self-contained pieces.

Guiding thesis: **the runtime you choose is the boundary, not the allowlist.**
The policy engine is a guardrail against accidents; isolation comes from the
`docker`/`ssh` runtime. `local`/`docker`/`ssh` are peers — no Docker dependency.

## Status

| Task | What | Status |
|------|------|--------|
| 023 | **Phase 0 + 1** — one-tool-call guard; core vertical on the `local` backend (policy engine, LocalSandbox, manager, reaper, audit, `Session.close`, `hugin sandbox`, `bash` tool, example) | **In PR #59** (arnovich/gimle-hugin); hardened after a 4-judge implementation review |
| 024 | Deferred hardening + phase-2 design items from the Phase 1 implementation review | OPEN |
| 025 | **Phase 2** — Docker backend (container isolation) | OPEN |
| 026 | **Phase 2** — SSH / remote (VPS) backend | OPEN (design note first) |
| 027 | **Phase 2** — background exec (freeze fix) + per-agent statefulness | OPEN |
| 028 | **Phase 3** — human escalation (`on_violation: ask_human`) | OPEN |
| 029 | **Phase 4** — the harness blend (markdown projection + outbox harvest) | OPEN (design-first, after watching real agents) |

## Ordering & dependencies

- **023 merges first** (Phase 1 is the foundation everything builds on).
- **024** items are mostly independent cleanups; several are prerequisites for
  Phase 2 (per-spec sandbox ownership, backend registry, reaper generalization to
  non-local resources, sandbox root from storage config). Do those before/with 025.
- **025 (docker)** and **026 (ssh)** are peers; either can go first. Both share
  the reaper generalization from 024 and the containment acceptance gate:
  `python3 -c 'os.system("id")'` must be **provably contained by the runtime**,
  not merely denied.
- **027 (background exec)** is independent of the isolation backends but is the
  worst *operational* property (a long command freezes the whole session), so
  it's high priority. It and **028 (escalation)** share the one deferral
  mechanism: `ToolResponse(response_interaction=...)` — never a bare
  `Waiting`/`AskHuman`.
- **029 (harness blend)** is design-first and should wait until real agents have
  used Phases 1–2.

## Cross-cutting notes

- **Blocking dependency for good bash UX:** full multi-tool-call support
  (task 006). Phase 0 shipped only the >1-`tool_use` *detection*; batched bash
  calls are otherwise a silent-data-loss risk.
- **Every isolation backend merges behind `/panel-review`** with the security
  judge's containment test as the gate (see `plan.md` "Review").
