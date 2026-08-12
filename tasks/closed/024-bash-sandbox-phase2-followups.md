---
title: Bash sandbox — phase 2 design items and deferred hardening
state: CLOSED
labels: [enhancement, security, tech-debt]
priority: medium
closed: 2026-08-12
---

# Bash sandbox — phase 2 design items and deferred hardening

## Resolution

Closed during the 2026-08-12 backlog audit. PR #77 was already titled and
implemented as the close-out for this task, but the task file was never moved.
The substantive Phase 2 follow-ups shipped across PRs #61 and #72–#77:

- per-spec sandbox ownership, backend registry, and storage-derived roots;
- thread-safe manager creation, bounded audit logs, and close-time counters;
- consistent denied targets and actionable config errors;
- a one-time, spec-derived environment note;
- unique absolute spill paths;
- agent/branch-confined `put_file` and `get_file`; and
- `Session.close()` in create-run-finish entry points.

The remaining work was either backend-specific or too small to justify a second
overlapping sandbox backlog. It is consolidated into task 030:

- backend-owned lifecycle/reaping and a short-lived secret-injection seam;
- per-backend path confinement against intermediate symlink swaps;
- closing sessions returned to long-running orchestrators when those apps adopt
  bash;
- per-agent/branch workspace accounting and reaping;
- a generic "earlier output elided" marker; and
- guidance for choosing bash versus structured tools.
