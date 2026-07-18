---
title: Bash sandbox — background exec + per-agent statefulness (Phase 2)
state: IN_PROGRESS
labels: [enhancement, sandbox, concurrency]
priority: high
---

# Bash sandbox — background exec + per-agent statefulness (Phase 2)

> **Status (2026-07-16):** background execution is implemented and merged behind
> the design in `design.md` (signed off + panel-reviewed). **Shipped:** commands
> run off the scheduler thread (a session worker pool above the Sandbox ABC);
> automatic deferral (default) + explicit `background:true` + the `bash_output`
> collect tool; the parked branch resolves into a real `tool_result` bound to the
> original `tool_call_id`; guarded collect (never wedges the stack); worker-side
> audit (once) + audit lock; ordered `Session.close`; `LocalSandbox.stop` kills
> lingering process groups; docker `start()` re-entry guard; the honest-stateless
> `cd` contract in the tool description. **Deferred (own follow-ups, see
> design.md):** the persistent shell (§ statefulness — serial-vs-concurrent
> crux); a scheduler idle-sleep for the single-parked-agent busy-spin; a
> monitor/interactive surface for a parked-on-background agent; `inherit_workspace`;
> automatic-threshold tuning after measurement.

Fix the bash tool's **worst operational property**: `Session.run` is
single-threaded round-robin and `execute_tool` is synchronous, so one long
`bash` command (a 120s build/test) **freezes every sibling agent and branch** in
the session. Plus the related usability gap: each call is a fresh shell, so
`cd`/`export`/`source` don't persist. These are grouped because both change the
execution model.

**Design source of truth:** task 023 `spec.md` §4 (Return type / deferral —
"the real contract"), §7 (Concurrency), §9 (Statefulness); `plan.md` Phase 2.
Phase 1 mitigated the freeze only with a short 15s default timeout + a doc note.

## The deferral mechanism (already load-bearing)

`ToolCall.step` accepts **only** `ToolResponse` or `AgentCall`; a bare
`Waiting`/`AskHuman` raises. So all deferral MUST route through
`ToolResponse.response_interaction` (which `ToolResult.step` already honors).
Background exec and Phase 3 human escalation (task 028) both use this one path —
do not invent a second.

## Tasks

### Background execution (the freeze fix)

- [ ] Run the subprocess **off the step thread** so a long command doesn't block
      the round-robin scheduler. This is the real work — "return a `Waiting`" is
      not free; it requires the exec to actually run asynchronously.
- [ ] For a long/backgrounded command, `bash` returns
      `ToolResponse(response_interaction=Waiting)` and the parent agent yields so
      siblings run.
- [ ] Add a `bash_output` poll tool: the agent checks on / collects the result of
      a still-running command, and the `Waiting` resolves when it completes.
- [ ] Decide the trigger: an explicit `background: true` arg, or automatic when a
      command exceeds a threshold. (Prefer explicit first; measure.)
- [ ] Ensure the audit + truncation + spill machinery still applies to a
      background command's eventual result.

### Per-agent statefulness (persistent shell)

- [ ] Per-agent **persistent shell** (pexpect/coprocess, one per
      `workspace_for(agent, branch)`) *inside* the disposable container/remote, so
      `cd`/`export`/`source` behave as the model expects. This resolves the
      security-vs-usability tension: persistent shell, disposable runtime.
- [ ] If persistent shell is NOT shipped: **remove `cd` from any allowlist** and
      state the stateless contract in bold in the tool description — an
      allowed-but-silently-ineffective `cd` is worse than a denied one. (Phase 1's
      description already says each call is a fresh shell.)

### Related workspace item

- [ ] `AgentCall` gains an `inherit_workspace` option so a delegated child starts
      in a populated dir (or a pointer to `common/`) instead of an empty one.

## Success criteria

- [ ] A long `bash` command (e.g. a real build in `financial_newspaper`) does
      **not** freeze sibling agents/branches; the edition still makes progress.
- [ ] The agent can start a long command, do other work, and collect the result
      via `bash_output`.
- [ ] Either `cd`/`export` persist within an agent's session, or the tool makes
      the stateless contract unmistakable and `cd` is not a silent no-op.
- [ ] Tests cover the deferral path (`response_interaction=Waiting` +
      `bash_output` resolution) against `FakeSandbox` — no real subprocess needed.
