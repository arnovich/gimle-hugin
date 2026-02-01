---
github_issue: 11
title: Track config changes
state: OPEN
labels: [enhancement]
author: arnovich
created: 2026-01-28
---

# Track config changes

For debugging and playback, we should track the history of config changes in the config state machine.

One option would be a list of the history, where each step of the history is related to an interaction uuid (when it happened).

Then in monitor we should display on each interaction if the config changes at that point, similar to the branching display.
