---
github_issue: 13
title: Agent Builder reference and example access
state: OPEN
labels: [enhancement]
priority: medium
author: arnovich
created: 2026-01-28
audited: 2026-08-12
---

# Agent Builder reference and example access

## Audit (2026-08-12)

Still open, but now owned by the Agent Creator v2 programme (task 034) and
should not be implemented independently.

- `list_examples` and `read_example` already exist, but are not wired into the
  builder on `main`. Task 034 PR 1.2 / PR #83 adds that wiring.
- General `read_file`/`list_files` builtins exist, but granting unrestricted
  local access is not the intended solution. Task 034 PR 2.4 introduces an
  explicit `reference_files` input with confinement and untrusted-content
  wrapping.
- Task 034 Phase 2 also defines the packaged knowledge/reference source and
  searchable example index needed outside a source checkout.

## Closure rule

Close this task when task 034 PR 2.4 (or an equivalent scoped implementation)
has merged and verifies both:

- the builder can study packaged examples in an installed distribution; and
- a user can explicitly provide confined local reference files without giving
  generated instructions arbitrary filesystem access.
