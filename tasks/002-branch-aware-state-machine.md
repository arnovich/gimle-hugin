---
github_issue: 2
title: Make agent config state machine branch aware
state: OPEN
labels: [enhancement]
author: arnovich
created: 2026-01-28
---

# Make agent config state machine branch aware

Currently the agent state machine does not take branches into account when transition agent config states.
This also means that all branches within an agent always have the same config.
Instead each branch should have its own config and the state machine transitions should happen according to the context of each branch.
