# Human escalation — design note (Phase 3)

**Status: SIGNED OFF (2026-07-19).** Decisions: **(A) a dedicated `BashApproval`
interaction — approve auto-runs the exact command, deny refuses; a real approval
gate, no model re-issue**; **interactivity = `config.interactive`** (escalate
when true, clean `deny` when false). Wiring `on_violation: ask_human` so an
out-of-policy `bash` command **asks a human** and (on approval) actually runs,
degrading to a clean `deny` when no human can answer. Source of truth: task 023
`spec.md` §4 (deferral contract), the 028 description, and a precise map of the
HITL machinery (below). Same deferral seam as background exec (027):
`ToolResponse(response_interaction=...)`.

## What the machinery gives us (and what it doesn't)

- **The deferral seam** — a tool returns `ToolResponse(response_interaction=<an
  Interaction>)`; `ToolResult.step()` splices it on. Proven by `ask_user`
  (`AskHuman`), `BashWaiting`, `bash_output`.
- **`AskHuman` parking** — `AskHuman.step()` returns `False` forever until a
  `HumanResponse` supersedes it; the human's answer is rendered back to the
  **model** as a `tool_result` bound to the original tool's `tool_call_id`.
- **The TUI answer flow** — `cli/interactive/state.py` detects "last interaction
  is `AskHuman`" and injects a `HumanResponse`; `cli/ui.py`'s plain-run loop does
  the same via `input()`. Both string-match the literal type name `"AskHuman"`.
- **`BashWaiting`'s branch-filtered `tool_call_id` recovery + never-raise
  `_collect`** — the correct pattern for binding a resumed result to the model's
  original `bash` call without wedging the stack.

**Genuinely missing:** (a) a resume that *runs the command* on approval instead
of delivering text to the model; (b) a structured approve/deny decision (today
the human answer is free text); (c) a "can a human answer this session?" signal —
none exists, and a headless `Session.run()` (the apps) *silently stalls* a parked
branch, so headless must degrade to deny; (d) surfacing a non-`AskHuman` pending
approval in the TUI/monitor (every site special-cases the literal type names).

## Decision 1 — interactivity signal: `config.interactive`, else deny

There is no runtime "human attached" signal. The honest, available signal is the
per-agent **`config.interactive`** flag (today it gates whether `is_interactive`
tools are *offered*; we broaden it to "this agent runs with a human"). So:

- `config.interactive == False` (the default — apps, headless `hugin run`,
  `financial_newspaper`) → an escalated command is a **clean `deny`** (no park,
  no stall). This is the safe default and covers every real headless call site.
- `config.interactive == True` → escalate (ask the human).

Residual risk: `interactive: true` *and* run headless (no TUI) → the ask parks
and `Session.run()` stops with it unresolved. That is an explicit operator
contract violation (declared interactive, provided no human); documented, and the
default path is safe. (A future real presence signal is a follow-up.)

## Decision 2 — the resume: dedicated `BashApproval` vs. reuse `AskHuman` (SIGN-OFF)

**The load-bearing fork**, because it shapes both UX and scope:

### Option A — dedicated `BashApproval` interaction (a real approval *gate*)

`bash`'s `Escalate` branch returns
`ToolResponse(response_interaction=BashApproval(command, cwd, timeout, reason,
command_hash))`. It parks while undecided; on **approve** it runs *its own stored
command* (escalation treated as allow for exactly that invocation) and delivers
the `ExecResult` as a `tool_result` (branch-filtered `tool_call_id`, never-raise —
the `BashWaiting` pattern); on **deny** it returns a "denied by a human"
`tool_result`. The human's decision **directly gates execution** — the model
cannot bypass it and does not re-issue anything.

- *Pro:* correct approval-gate semantics (the security point); clean UX
  (approve → it just runs); isolated to bash's own code — touches no shared
  interaction machinery.
- *Con:* needs a small TUI change to *answer* it — `_check_awaiting_input`
  recognizes `BashApproval` (show the command + reason), and `submit_human_response`
  writes its `decision` instead of a `HumanResponse` (~2 focused spots in
  `state.py`). Read-only `hugin monitor` rendering (color/detail, `monitor.js`) is
  deferred — a new type renders as a generic node meanwhile.

### Option B — reuse `AskHuman` + a session approved-hash set (advisory to the model)

`bash` escalates via `AskHuman` (inherits all TUI/monitor surfacing for free); the
human's approve/deny goes to the **model** as text; on "approve" the exact
command-hash is recorded in a session approved-set (a hook on the `AskHuman`→
`HumanResponse` resolution), and the **model re-issues** the command — which
`bash` now runs because the hash is approved.

- *Pro:* zero new UI plumbing (reuses `AskHuman`/`HumanResponse` verbatim).
- *Con:* the model is in the loop (must re-issue after approval); "deny" is only
  advisory to the model (the gate still blocks, but the flow is clunky); and it
  **modifies shared interaction code** (`AskHuman`/`HumanResponse`/`AskOracle`
  resolution) that also serves `ask_user` — higher blast radius.

**Recommendation: Option A.** It is the real approval gate (the security intent),
has the cleaner UX, and stays isolated to the sandbox code; the TUI cost is small
and bounded. Option B trades a real gate + clean UX for saving ~2 `state.py`
edits, at the cost of touching shared machinery.

## The rest (independent of the fork)

- **Scoping — one-shot by construction.** Approval runs *this exact stored
  command*, nothing else; it never widens to "allow this binary." No durable
  grant. (A session-scoped exact-hash allow — don't re-ask an identical command —
  is a possible extension, explicitly not "allow this binary".)
- **Capability summary (v1).** The human sees the **command verbatim + the policy
  reason it was flagged + the cwd/backend it would run in** — enough to decide.
  `Escalate` currently carries only `reason: str`; a richer AST effect-breakdown
  (writes-outside-workspace, network, …) needs new plumbing and is a follow-up.
- **Remove the Phase-1 "approval unavailable, do not retry" note** — replaced by
  a real ask (interactive) or a plain policy `deny` (non-interactive).
- **Audit** — record `escalated` at ask time and the eventual `run`/`denied`
  outcome (via the same guarded collect).
- **Never-raise + branch-filtered binding** — mirror `BashWaiting` exactly (an
  exception escaping the resume wedges `Stack._step_lock`).

## What v1 ships vs. defers

**Ships (Option A):** the `BashApproval` interaction (park → approve-runs /
deny-refuses, guarded, branch-bound); `bash` escalation returns it when
`config.interactive`, else denies; the TUI answer-flow addition; one-shot
approval; the v1 capability summary; tests (defer-in-interactive,
degrade-to-deny-when-not, approve-runs-the-exact-command, deny-refuses) against
`FakeSandbox`.

**Defers:** read-only `hugin monitor`/`monitor.js` rendering of a pending
approval (renders generic meanwhile); a richer AST capability breakdown; a
session exact-hash allow-once; a real runtime "human attached" presence signal.

## Implementation note — a critical bypass found + fixed

The first cut ran an approved command by calling `bash(command, _approved=True)`.
**That was a policy-bypass hole:** `Tool.execute_tool` passes a tool_call's args
straight to the function without stripping undeclared keys, so a model emitting
`{"command": "rm -rf /", "_approved": true}` would have run it unrestricted (a
leading underscore does not protect a `**kwargs`-passed arg). Fixed by removing
`_approved` entirely and moving the run into `run_approved(...)` — a **plain
function only `BashApproval` calls**, unreachable by the model. Regression tests:
a model-supplied `_approved` kwarg fails closed (the command never runs), and
`bash` has neither the param nor `**kwargs`. (Filed the general
`execute_tool`-passes-undeclared-kwargs fragility as an observation for 024/030.)

## Security review (2026-07-19)

A focused adversarial security review found **no bypass** — no path for the model
(or any non-human) to run an unapproved command, and no way to run a command
different from the one the human saw (`decision`/`command` are set only by the
human via the CLI; `run_approved` is unreachable by the model; the `unrestricted`
run still fails-closed on parse errors and preserves backend isolation, cwd
confinement, and timeouts). **Safe to merge.** Fixed here from its findings:

- **M2 (audit)** — the approved run is now tagged `reason="human-approved"` and a
  human *denial* is recorded as `denied_by_human` (was: an approved run looked
  like an ordinary `run`, and a denial wasn't audited at all — bad observability
  for a policy-bypass feature).
- **L1** — the approval prompt now shows the `cwd` and the backend, warning
  loudly when it's `local` (runs unconfined on the host).

Deferred (filed as follow-ups):

- **M1 (framework hardening)** — `execute_tool` passes a tool_call's undeclared
  args straight to the function; the schema is not enforced as a kwarg allowlist
  (this is the class of bug that produced the `_approved` hole). No current
  offender, but it should filter kwargs to `{declared} ∪ {stack, branch, reason}`
  before calling the function. Cross-cutting — its own task (024-class).
- **M3 (availability)** — a `BashApproval` parked on a *non-last* branch (parallel
  branches) or in a headless `interactive:true` run is not surfaced to a human,
  so the task stalls (fail-safe: the command never runs, but the run ends
  unresolved). v1's answer surface is the plain interactive CLI on the last
  interaction; a per-branch scan + a real human-channel presence signal is the
  follow-up (with the Textual-TUI/monitor answer surface).
- **L2** — a crash after `decision` persists but before the result is written
  could re-run the (human-approved) command on reload; same idempotency shape as
  `BashWaiting`. A resolved-guard would close it.

## Open questions for sign-off

1. **Option A (dedicated `BashApproval`, approve→auto-run) vs Option B (reuse
   `AskHuman`, model re-issues).** Recommendation: A.
2. **Interactivity = `config.interactive`** (deny when false) — confirm, versus
   wanting a new dedicated bash-config knob.
