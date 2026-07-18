# Bash sandbox — roadmap index

The bash tool lets a Hugin agent run shell commands through a pluggable
execution sandbox. It ships in phases so each is independently reviewable. The
full design lives in the **task 023 folder**, now at
`tasks/closed/023-bash-tool/` (`spec.md` / `plan.md` / `notes.md` / `review.md`)
— read that for rationale; the tasks below are the actionable, self-contained
pieces.

Guiding thesis: **the runtime you choose is the boundary, not the allowlist.**
The policy engine is a guardrail against accidents; isolation comes from the
`docker`/`ssh` runtime. `local`/`docker`/`ssh` are peers — no Docker dependency.

## Status

| Task | What | Status |
|------|------|--------|
| 023 | **Phase 0 + 1** — one-tool-call guard; core vertical on the `local` backend (policy engine, LocalSandbox, manager, reaper, audit, `Session.close`, `hugin sandbox`, `bash` tool, example) | **MERGED** (PR #59); hardened after a 4-judge implementation review. Design docs in `tasks/closed/023-bash-tool/` |
| 024 | Deferred hardening + phase-2 design items from the Phase 1 implementation review | OPEN (medium) |
| 025 | **Phase 2** — Docker backend (container isolation) | **MERGED** (PR #62) |
| 026 | **Phase 2** — SSH / remote (VPS) backend | **MERGED** (PR #63) |
| 027 | **Phase 2** — background exec (freeze fix); persistent shell split to 032 | **MERGED** (PR #65) |
| 028 | **Phase 3** — human escalation (`on_violation: ask_human`) | OPEN (medium) |
| 029 | **Phase 4** — the harness blend (markdown projection + outbox harvest) | OPEN (design-first, after watching real agents) |
| 030 | Docker & SSH backend follow-ups (deferred panel findings; incl. `network:true` egress filtering — the one blocking security item) | OPEN (**high**) |
| 031 | Cross-backend E2E test harness + local real-backend runner (`docker/README.md`) | **MERGED** (PRs #64/#66) |
| 032 | Per-agent persistent shell (`cd`/`export` persist) — deferred from 027 | OPEN (medium) |

## Ordering & dependencies

- **023/025/026/027/031 are merged** — all three backends, the E2E harness, and
  background exec are shipped. The foundation and Phase 2 are done.
- **030 is the highest-priority remaining item** — the deferred docker/ssh panel
  findings, headlined by **`network:true` egress filtering**: until it lands, do
  **not** enable `backend: docker` for untrusted input *with* `network:true` (an
  injected `curl http://169.254.169.254/...` can exfiltrate cloud IAM creds). The
  default `network:false` is safe, so this gates only the network-on path.
- **024** is the remaining phase-2 plumbing (thread-safety, reaper
  generalization, observability) — mostly independent cleanups.
- **028 (escalation)** shares the one deferral mechanism with background exec:
  `ToolResponse(response_interaction=...)` — never a bare `Waiting`/`AskHuman`
  (027 built the `BashWaiting` interaction on exactly this seam).
- **032 (persistent shell)** was split out of 027; its crux is reconciling a
  serial persistent shell with concurrent background exec — design-first.
- **029 (harness blend)** is design-first and should wait until real agents have
  used Phases 1–2.

## Cross-cutting notes

- **Blocking dependency for good bash UX:** full multi-tool-call support
  (task 006). Phase 0 shipped only the >1-`tool_use` *detection*; batched bash
  calls are otherwise a silent-data-loss risk.
- **Every isolation backend merges behind `/panel-review`** with the security
  judge's containment test as the gate (see `plan.md` "Review").
