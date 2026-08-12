---
github_issue: 2
title: Make agent config state branch-aware
state: OPEN
labels: [enhancement]
priority: medium
author: arnovich
created: 2026-01-28
audited: 2026-08-12
---

# Make agent config state branch-aware

## Audit (2026-08-12)

Still relevant. Branches have separate interactions, tasks, and context, but an
`Agent` still owns one global `config`, `_current_state`, `_state_machine`, and
`_config_history`. `Agent.step()` advances active branches and then evaluates a
single transition against that shared state. A transition caused by one branch
therefore changes the configuration seen by every branch.

## Required design

- Define branch-local current config/state and transition history, including
  what a newly created branch inherits from its parent.
- Evaluate `tool_call`, `step_count`, and `state_pattern` triggers against the
  branch that produced the interaction.
- Make rewind/restore operate on the selected branch without changing siblings.
- Preserve branch-local state through storage serialization and session resume.
- Decide how the monitor exposes different config states on sibling branches.

Do not implement this as a second branch system beside `Stack`; the config-state
mapping should use the existing branch identifiers and lifecycle.

## Success criteria

- Two active sibling branches can be in different config states.
- A transition on one branch does not alter a sibling.
- Branch creation, rewind, persistence/resume, and monitor rendering are tested.
