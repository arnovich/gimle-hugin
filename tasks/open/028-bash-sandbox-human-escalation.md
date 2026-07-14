---
title: Bash sandbox — human escalation (Phase 3)
state: OPEN
labels: [enhancement, sandbox, human-in-the-loop]
priority: medium
---

# Bash sandbox — human escalation (Phase 3)

Make `on_violation: ask_human` actually ask a human, instead of failing cleanly.
Phase 1 accepts the config knob but, until this lands, an escalated command
returns a `needs_approval` error with a note that says approval is unavailable
(so a model doesn't loop). This task wires the real approval path.

**Design source of truth:** task 023 `spec.md` §4 (deferral contract), `plan.md`
Phase 3. The `Policy.on_violation` field, `Escalate` decision, and the tool's
escalation branch already exist from Phase 1.

## The deferral mechanism

Route through `ToolResponse(response_interaction=AskHuman)` — a **bare
`AskHuman` raises** (`ToolCall.step` only accepts `ToolResponse`/`AgentCall`).
Same single deferral path as background exec (task 027).

## Tasks

- [ ] `on_violation: ask_human` → `ToolResponse(response_interaction=AskHuman)`
      carrying the pending command for approval.
- [ ] **Degrade to `deny` when the session is non-interactive** — otherwise the
      agent parks forever waiting for an approval that can never come. Detect
      interactivity from the session/run context.
- [ ] The escalation prompt shows the command's **capabilities/effects**, not a
      raw base64/opaque string — a human approving must understand what they're
      approving.
- [ ] Approve-once is scoped to an **exact command hash**, never "allow this
      binary" (which would be a durable capability grant the operator didn't
      intend).
- [ ] Surface the pending command in `hugin interactive` / `hugin monitor` so a
      human can see and act on it.
- [ ] Reject `on_violation: ask_human` at config-parse time only if we choose NOT
      to support it; otherwise this task removes the Phase 1 "not available" note.
- [ ] Tests: escalation defers via `response_interaction=AskHuman` in an
      interactive session; degrades to `deny` in a non-interactive one; approval
      is scoped to the exact command.

## Success criteria

- [ ] An out-of-policy command **asks** rather than fails, in an interactive run.
- [ ] A non-interactive run degrades cleanly to `deny` (no infinite park).
- [ ] Approval never silently widens to "allow this binary going forward".
