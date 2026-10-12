# Bash sandbox — roadmap index

The bash tool runs agent commands through pluggable local, Docker, and SSH
backends. The full rationale and Phase 1 contract live in
`tasks/closed/023-bash-tool/`. The runtime is the containment boundary; the
policy engine is an accident guardrail.

Last audited: **2026-08-12**.

## Status

| Task | What | Status |
|------|------|--------|
| 023 | Core local vertical: policy, manager, reaper, audit, CLI, bash tool | **MERGED** (PR #59) |
| 024 | Phase 2 foundation and implementation-review follow-ups | **CLOSED** (implemented across PRs #61/#72–#77; remainder consolidated into 030) |
| 025 | Docker containment backend | **MERGED** (PR #62) |
| 026 | SSH/disposable-host backend | **MERGED** (PR #63) |
| 027 | Background execution; persistent shell split to 032 | **MERGED** (PR #65) |
| 028 | Human approval for policy violations | **MERGED** (PR #69) |
| 029 | Filesystem projection/outbox “harness blend” | OPEN (low, evidence then design) |
| 030 | Remaining cross-backend containment, lifecycle, and ops hardening | OPEN (high for untrusted-at-scale slices) |
| 031 | Cross-backend E2E harness and local real-backend runner | **MERGED** (PRs #64/#66) |
| 032 | Per-agent persistent foreground shell | OPEN (medium, evidence then design) |
| 033 | Filtered Docker egress proxy for allowlisted `network: true` | **CLOSED** (PR #70; close-out PR #71) |

## What remains

- **030 is the implementation backlog.** The highest-risk remaining work for
  untrusted workloads at scale is Docker userns/image provenance/total quota,
  stronger path-walk confinement, SSH `remote_docker`, and generic lifecycle +
  secret handling. It also owns the small unshipped items from task 024.
- **Filtered egress is shipped.** `network: false` remains the default;
  allowlisted `network: true` uses task 033's proxy. Only the explicitly named
  `allow_unrestricted_egress` escape hatch permits unfiltered egress.
- **032 is a product decision, not assumed roadmap work.** Collect evidence that
  persistent `cd`/environment state is worth the three-backend lifecycle and
  concurrency cost before building it.
- **029 remains parked** until concrete agent runs demonstrate projection,
  discovery, or artifact hand-off problems that the proposed filesystem blend
  would solve.

## Cross-cutting dependency

Full batched tool-call support (task 006) is still important for good bash and
general tool UX. PR #58 prevents silent loss by disabling provider parallelism
and warning on violations; it does not execute multiple calls from one assistant
response.
