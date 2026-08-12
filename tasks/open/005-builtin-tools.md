---
github_issue: 5
title: Promote proven example tools to builtins
state: OPEN
labels: [enhancement]
priority: low
author: arnovich
created: 2026-01-28
audited: 2026-08-12
---

# Promote proven example tools to builtins

## Audit (2026-08-12)

Relevant only as a small, evidence-driven maintenance task. Hugin already ships
builtins for file inspection, artifacts/memory, bash, agent launch/listing,
human input, ratings, and completion. A repository scan found one concrete
duplicated example pattern: `create_branch`. There is not yet evidence for a
broad batch of new builtins.

## Promotion rule

Promote a tool only when it:

- appears in multiple real agents/examples or recurring user code;
- has stable semantics that do not depend on one app;
- benefits from typed arguments, framework observability, validation, or
  persistence beyond what a short bash command provides; and
- can be documented and tested without pulling app-specific dependencies into
  core.

## Current candidate

- [ ] Extract and reconcile the existing `create_branch` implementations as a
  builtin, or record why their semantics are intentionally example-specific.
- [ ] Search again for duplication when a real example/tool corpus has grown;
  file focused follow-up tasks for candidates rather than adding speculative
  helpers here.

## Success criteria

- Every promoted builtin has at least two proven callers, contract tests, and a
  migration note for the duplicated implementations it replaces.
