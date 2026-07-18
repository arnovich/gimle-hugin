# Background exec + statefulness — design note (Phase 2)

**Status: SIGNED OFF + PANEL-REVIEWED (2026-07-16).** Decisions:
**(1) automatic deferral is the default** — `bash` runs on a worker, waits a
short grace, and auto-backgrounds if the command is still running (siblings never
freeze regardless of what the model guesses); **(2) keep an explicit
`background:true` hint** — skip the grace, return a job handle immediately for
"start a long command, do other work", collected by a `bash_output` tool;
**(3) defer the persistent shell** to its own task (ship the honest-stateless
mitigation now). A three-judge design panel (concurrency-correctness /
framework-fit / agent-usability) then reviewed this note; its load-bearing
findings are folded in below (see "Panel review"). Source of truth: task 023
`spec.md` §4/§7/§9, `plan.md` Phase 2, and a precise map of the scheduler.

## The problem, precisely

`Session.run()` is a single-threaded round-robin: one `for agent in
self.agents: agent.step()` pass per tick, and `execute_tool` calls the tool
function **synchronously on that one thread** (`tool.py:381`). A `bash` call that
blocks in `sandbox.exec()` for 120s blocks the scheduler thread for 120s, which
freezes *every* sibling agent and branch. Phase 1 only bounded the damage with a
short default `timeout_s` (15s). Secondary gap: each call is a fresh shell, so
`cd`/`export`/`source` don't persist.

## What the framework already gives us

- **The deferral seam.** A tool returns `ToolResponse(response_interaction=<an
  Interaction>)`; `ToolResult.step()` splices it onto the branch. Live
  precedents: `AskHuman` and `AgentCall`+`Waiting`.
- **A poll-based resume.** `Waiting(condition=Condition(evaluator, params))`:
  each tick the parked branch is visited, `Condition.evaluate` runs once, returns
  `True` (keep waiting) or `False` (proceed). `wait_for_seconds`/`wait_for_ticks`
  are this shape. A parked `Waiting.step()` returns `True` every tick, which
  keeps the round-robin loop alive **while siblings run**.

So the freeze fix needs **no new scheduler machinery** — only somewhere to run
the command off the scheduler thread and a condition that polls it. **But** the
naive "resolve via `next_tool`" is wrong (see Panel H1); the resume must produce
a real `tool_result` paired to the model's original call.

## The one load-bearing decision: async lives *above* the Sandbox ABC

`Sandbox.exec()` stays synchronous and unchanged. The async-ness is a thin layer
above the ABC:

- **A per-session job registry** — `session.bash_jobs: Dict[str, BashJob]`,
  in-memory, not serialized (mirrors `session.sandboxes`; excluded from
  `to_dict`, empty after a reload). A **`BashJob` is self-describing**:
  `{future, manager, policy, cwd, command, agent_id, tool_call_id, start_time,
  status}` — it carries its `SandboxManager` so the collect needs no
  re-resolution and teardown/audit are local to it (Panel H2).
- **A lazily-created worker pool** — a session `ThreadPoolExecutor` (created on
  first background use, like sandboxes) runs the existing blocking
  `sandbox.exec(...)`. Each `exec` already spawns its own subprocess + reader
  threads, so it is self-contained; the worker just moves that blocking call off
  the scheduler thread.
- **A `bash_running` condition** (scheduler-thread poll) — reads *serializable*
  session shared-state keyed by `job_id` (the `ExecResult`/error is published
  into shared-state at collection on the scheduler thread, never a raw
  cross-thread `Future` read), matching the `conditions.py` convention. It
  returns `False` (done) when the result key is present **or the job is unknown**
  (lost to a reload — treated as terminal, never `KeyError`; Panel H2/M1).
- **A dedicated resolve** — on completion the parked branch must yield a proper
  `tool_result` carrying the model's **original** `bash_output`/`bash`
  `tool_call_id`, exactly like `AgentResult` (`get_last_tool_call_interaction()`
  → `Prompt(type="tool_result", tool_use_id=…)`), **not** a `next_tool` chain
  (which fires an id-less `ToolCall` that renders as plain text → an orphaned
  `tool_use` → Anthropic 400). This is the single most important correction from
  the panel (H1). Concretely: a small interaction that, on the scheduler thread,
  (a) sees the job done via the condition, (b) collects the `ExecResult` **fully
  guarded** (a worker exception or missing job maps to `infra_error`, never
  raises — `Stack.step()` has no `try/finally` and a raise permanently wedges the
  agent), (c) renders it through the existing `_record`/`_to_response`
  truncation/spill/audit path as a `tool_result` bound to the stored
  `tool_call_id`.

Why above the ABC: no `Sandbox` interface change, no per-backend async
reimplementation, uniform across `local`/`docker`/`ssh`.

## Agent-facing surface

- **`bash(command, cwd?)` — automatic (default).** Start on the worker with the
  interactive `policy.timeout_s` (15s), wait up to a short grace `defer_after_s`
  (default ~2s, configurable):
  - finishes within the grace → return the result **inline** (a normal
    `ToolResponse`, no deferral plumbing on the stack — the fast common case is
    unchanged for the model).
  - still running after the grace → return
    `ToolResponse(response_interaction=<the resolve Waiting>)`; the agent parks
    (**siblings run**) and resumes with a single normal `tool_result` when the
    command finishes. No new tool, no `job_id`, no model prediction — the freeze
    is fixed whether or not the model expected the command to be slow.
  - Because the automatic path uses the 15s interactive timeout, a genuinely long
    command (a build) times out at 15s with a hint to use `background:true`.
- **`bash(command, background=true)` — explicit long/interleave.** Skip the grace;
  run with the generous `policy.max_timeout_s` (600s) budget; return
  **immediately** `is_error=False, content={job_id, status:"running", next:"call
  bash_output with this job_id to get the result"}`. The agent does other work;
  **siblings run**. This is the "start a long build, keep working" path and the
  way a >15s command gets a long budget.
- **`bash_output(job_id)`** (new tool, `builtins.bash_output:bash_output`):
  - job **done** → the full `ExecResult` through the normal
    truncation/spill/audit path (same content keys as foreground; `is_error` only
    for timeout/oom).
  - job **still running** → the resolve `Waiting`; the agent **parks until done**
    then auto-collects as one `tool_result` (no model-side spin-poll).
  - **unknown / stale / already-collected `job_id`** → `is_error=True,
    {error:"unknown or already-collected job_id: …", note:"start a new command;
    do not retry this id"}` so the model recovers instead of looping. A collected
    result stays re-readable until branch/session end (friendlier than one-shot
    consume).
- **Denials fire at launch**, never deferred: a policy/parse/infra failure comes
  back from `bash(...)` immediately (with `denied`/`unparseable`/`infra_error`
  and **no** `job_id`) — an error is never split across two tools (Panel M3).

## Statefulness — defer the persistent shell (confirmed)

Ship the honest-stateless mitigation: the (policy-derived, always-visible)
description states in bold that **each call is a fresh shell** — `cd`/`export`/
`source` and a background job's cwd/env do **not** persist; persist state by
writing files under the workspace — and `cd` is never an allowed silent no-op.
The persistent shell (pexpect/coprocess per `workspace_for(agent, branch)`) is
its own follow-up task, with its crux being the tension between a **serial**
persistent shell (one command at a time) and **concurrent** background exec.

## Thread-safety & lifecycle (from the concurrency panel)

- **Guarded collect (Panel H1/H2).** Never call `future.result()` unguarded and
  never index `session.bash_jobs[job_id]` bare — a worker exception or a
  reload-lost job must render as `infra_error`, because any exception escaping a
  tool leaves `Stack._step_lock=True` and kills the agent for the rest of the
  session.
- **Local teardown backstop (Panel H4).** `LocalSandbox.stop()` is currently a
  no-op, and its kill-on-timeout lives on the worker thread — so a local
  background subprocess **leaks** on `close()`. Fix: `LocalSandbox` tracks its
  active exec process-groups (thread-safe set) and `stop()` `killpg`s them.
  docker/ssh already kill the exec in `stop()`.
- **`close()` order (Panel H2/H4/M4).** Stopping a sandbox is what interrupts a
  blocking `exec()`. Sequence: mark closing → `manager.close()`/`stop()` each
  sandbox (kills running execs → workers unblock, bounded by each backend's
  host-deadline) → `executor.shutdown(wait=True, timeout=grace)` to join the
  now-unblocking workers. `close()` stays idempotent and never raises. Lazy
  executor so a session that never backgrounds spawns no threads.
- **Audit on the worker (Panel H3/M3).** Record the command outcome
  (`run`/`timed_out`/`oom`/`infra`) **when `exec` returns on the worker**, so a
  fire-and-forget job that is never collected still leaves a complete audit
  trail; guard `CommandAudit.record`'s file append + counter with a lock (it now
  has multiple writers).
- **docker `start()` re-entry (Panel M3).** `SandboxManager.get()` calls
  `start()` on every command; docker's `start()` is not a no-op (re-stamps,
  `images.get`, can reassign `self._container`) and races a worker reading
  `self._container`. Guard docker `start()` with a process-level "started" flag
  (like ssh) so a re-`get()` is cheap and non-mutating; bound the docker client
  pool for concurrent execs.
- **Registry hygiene (Panel M5).** `job_id` is scoped to the owning `agent_id`
  (reject cross-agent collects); cap the number of outstanding background jobs
  per session (reject past the cap with a clear error); GC finished-and-collected
  (and old finished-uncollected) entries so a long session doesn't grow
  unbounded. One in-flight *parked* job per (agent, branch) — the branch is a
  single `Waiting` slot; multiple concurrent parks is deferred (a stack-shape
  change, not purely additive).
- **Busy-spin (Panel M2).** A sole parked agent hot-loops the condition, and the
  GIL contention can *slow the very command it waits on* (starving the worker's
  pipe drain). Because automatic deferral makes parking the common case, add a
  **scheduler idle-sleep**: when a full `Session.run` pass made no progress other
  than condition-parked `Waiting`s returning `True`, sleep briefly (~10–20ms)
  before the next pass. It must be keyed on "no runnable siblings" (a
  condition-local sleep would freeze siblings) — hence it lives in the scheduler.

## Monitor / interactive surface (Panel M2, framework)

A `Waiting(condition=bash_running)` is neither "finished" (no-condition Waiting)
nor "awaiting human", so today it reads as ambiguously *active* / seemingly
stuck, and the tools read from storage where only `job_id` is visible. Mirror job
metadata (`command`, `start_time`, `status`) into serializable shared-state and
add a `bash_running`-aware branch to the monitor/interactive state so a long
build renders as e.g. "running `make` (0:45)".

## `inherit_workspace` on `AgentCall`

Minor and orthogonal. **Defer** to keep this change focused on the execution
model.

## What v1 ships vs. defers

**Ships:** the session job registry + lazy worker pool; automatic grace-then-
defer on `bash` (transparent freeze fix); explicit `background:true` +
`bash_output` (interleave / long budget); the `bash_running` condition over
serializable state; the dedicated guarded resolve that emits a correct
`tool_result`; local process-group kill + ordered `close()`; worker-side audit +
lock; docker `start()` guard; registry hygiene (agent-scoped ids, cap, GC); the
scheduler idle-sleep; the monitor/interactive surface; the honest-stateless `cd`
mitigation. Tests drive the full parked→resume path against a **gated
`FakeSandbox`** whose `exec()` blocks on an `Event` the test releases (today's
returns instantly, so the interleaving would go untested), plus a real-model
assertion that the assembled message list has **no orphaned `tool_use`** (Panel
H1 — `FakeSandbox`+`MockModel` alone cannot catch it).

**Defers (own tasks):** the persistent shell (§9, serial-vs-concurrent crux);
`inherit_workspace`; multiple concurrent parked jobs per branch; a policy
`allow_background`/`max_background_jobs` ceiling (nice-to-have).

## Panel review (2026-07-16)

Three judges. The core architecture (async above the ABC; a session registry +
worker pool; a `bash_running` poll condition; results through
`_record`/`_to_response`) was judged sound by all three. Load-bearing findings,
all folded in above:

- **H1 (correctness, unanimous):** the `next_tool` resume renders an id-less
  `tool_result` → orphaned `tool_use` → Anthropic 400. Resolve like
  `AgentResult`/`AskHuman` with the original `tool_call_id`. Both the framework
  and usability judges independently traced this; confirmed against
  `ask_oracle.py:147-154` vs `agent_result.py:50-58`.
- **Stack-wedge:** `Stack.step()` lacks `try/finally` and `ToolCall.step()`
  catches only `TypeError`; the collect must be fully guarded.
- **H2 job↔manager binding + `close()` ordering; H3 worker-side audit; H4 local
  process-group kill;** M1 serializable-state condition; M2 busy-spin/GIL
  starvation → scheduler idle-sleep; M3 docker `start()` race; M5 registry
  hygiene; the monitor surface; the gated `FakeSandbox`.
- **Trigger re-decision:** the usability judge argued explicit-only ships the
  cost without the benefit (the freeze-fix is invisible to the model and depends
  on it predicting "slow"); the framework judge confirmed automatic reuses the
  same machinery. Re-surfaced to the owner → **automatic default + keep the
  `background:true` hint** (this note's decision 1+2).
- On **polling-condition vs AgentCall-style resume**, the framework judge was
  explicit: the polling condition is the correct fit — a bash job is not an
  `Agent` (no stack/config/LLM to step), so a pseudo-child would be strictly more
  machinery. Keep the condition; fix only the *rendering* (H1).

## Implementation review (2026-07-16)

A concurrency-correctness code review of the built feature confirmed the core
sound — the executor, the audit-exactly-once flag, the lock discipline (no nested
`self._lock`↔`audit._lock`), and the `close()` ordering all hold, and no
HIGH crash/hang/deadlock. Two MEDIUMs fixed before merge:

- **Multi-branch `tool_call_id` mis-binding** — `get_last_tool_call_interaction`
  scans a flat cross-branch list, so a `BashWaiting` on branch A could bind its
  resumed `tool_result` to a sibling branch's call id (absent from A's context →
  a 400 that wedges the stack). Now a **branch-filtered** lookup + a `None`-id →
  text fallback. Covered by a new multi-branch test.
- **Unbounded `_jobs` growth** — every bash call (incl. fast inline ones) added a
  job that was never evicted. Now a collected job is evicted on `collect`, and a
  submit-time GC bounds finished-but-never-collected (fire-and-forget) jobs.

Cheap LOW also taken: an explicit `CancelledError` catch in `_record_completion`
so a queued job cancelled at shutdown is not miscounted as `infra_error` and
cannot (on a hypothetical stdlib) crash `shutdown`.

Deferred LOWs (noted, not blocking): docker `exec` reads `self._container` while
`stop()` nulls it (teardown-only, surfaces a misleading `infra_error`, no
wedge/hang); local `stop()` has microscopic miss/PID-reuse windows (bounded, the
same as the pre-existing `_kill_group`); the grace-block is additive across
siblings firing slow commands in one tick (bounded by the grace per call, per the
design).

## Sign-off (2026-07-16)

1. **Automatic deferral default** — CONFIRMED (owner chose "automatic + keep
   background hint").
2. **Keep explicit `background:true` + `bash_output`** — CONFIRMED.
3. **Defer the persistent shell** — CONFIRMED (honest-stateless mitigation now).
