# Plan

Re-sliced after panel review (`review.md`), then adjusted per direction:
**no Docker dependency — the three backends (`local`, `docker`, `ssh`) are
peers and none is privileged.** So Phase 1 ships the whole vertical on the
zero-dependency `local` backend (installs and runs with `bashlex` alone), and
the isolation backends (`docker`, `ssh`) follow in Phase 2 as additive choices.
The moves that survived the review unchanged: **lifecycle, reaping and
observability are in Phase 1** (the local backend leaks process groups and
workspace dirs from the first commit), and **background exec moves up to
Phase 2** (the synchronous freeze is the worst operational property, not a
phase-6 nicety). Work each phase in its own worktree per `CLAUDE.md`.

> **Residual risk to weigh:** the first shippable backend (`local`) has no
> isolation. That's acceptable only while bash is used for examples and trusted
> tasks. If bash needs to run untrusted work before Phase 2 lands, pull the
> `docker` backend forward into Phase 1. Flagged for a call.

## Phase 0 — Prerequisite check: one tool call per turn

`anthropic.py:125` keeps only the last `tool_use` block. Bash agents batch, so
this silently drops calls.

- [ ] Land the >1-`tool_use` detection + explicit error for dropped calls (a
      small, safe change) OR confirm task 006 lands first
- [ ] Decide whether full multi-tool-call support (006) blocks bash GA — it
      strongly shapes bash UX

**Rationale:** without this, every bash exploration step is a silent-data-loss
risk. It's cheap; do it first.

## Phase 1 — Core vertical on the zero-dependency `local` backend

The whole feature end-to-end with no Docker and no daemon — the package installs
and `bash` runs with `bashlex` alone. Honest labeling throughout: no allowlist
theatre, the `local` backend documented as offering no isolation.

- [ ] `sandbox/sandbox.py` — `Sandbox` ABC, `ExecResult`, `SandboxSpec`
      (backend has **no default — must be named**), `create_sandbox()` with
      up-front backend validation and a remediation error
- [ ] `sandbox/policy.py` — `Policy` (denylist default, permissive because the
      boundary is the runtime), `evaluate()`, `Policy.from_dict` (reject unknown
      keys, fail loud); bashlex AST walk that descends into wrapper binaries and
      rejects dangerous assignment prefixes; fail closed on parse failure;
      enforcement raises `PolicyDenied`
- [ ] `sandbox/local.py` — `LocalSandbox`; boundary-only knobs
      (`network`/`cpu`/`memory`/`pids`) raise; `HOME`=workspace; env scrubbed;
      process-group kill on timeout; documented as no-isolation
- [ ] `sandbox/manager.py` — `SandboxManager`; `workspace_for(agent, branch)`;
      config→Policy/Spec resolution with key-level-merge precedence
- [ ] `sandbox/reaper.py` — dead-owner/stale reaping at every `hugin`
      invocation; workspace-dir GC; never kills a live peer
- [ ] `sandbox/audit.py` — append-only command log + counters
- [ ] **`Session.close()` + `Session.__enter__/__exit__`** — the teardown seam
      that doesn't exist today; SIGTERM/SIGINT handler; wired into CLI, TUI, and
      app `finally`s
- [ ] `sandbox/fake.py` — `FakeSandbox`
- [ ] `tools/builtins/bash.py` — the tool; policy-derived description carrying
      the environment; tail-biased truncation + spill file; `is_error` only for
      denial/timeout/infra; `include_only_in_context_window`; no `include_reason`,
      no `timeout` param; deferral via `response_interaction`
- [ ] `hugin sandbox list|prune` CLI (dead-owner-scoped)
- [ ] Tests: policy bypasses (interpreter/wrapper/assignment/path/parse);
      tool against `FakeSandbox`; reaper; local process-group kill; env scrub;
      multi-agent/multi-branch workspaces
- [ ] `bashlex` → core deps; CLAUDE.md bash section
- [ ] `examples/bash_agent/` — smallest working agent, `backend: local`, with a
      comment stating the example accepts no isolation

**Done when:** the package installs with no Docker, an agent runs bash on the
local backend, a denial is a recoverable `ToolResponse`, nothing claims the
allowlist is a boundary, and any non-clean exit self-heals within one TTL.

## Phase 2 — Isolation backends + the freeze fix

The additive isolation choices, plus the concurrency fix. Any of these can be
pulled into Phase 1 if bash must run untrusted work sooner (see residual risk).

- [ ] `sandbox/docker.py` — `docker` backend, **lazy `docker`-SDK import** so it's
      never needed unless selected; **all** hardening flags (`--cap-drop=ALL`,
      `--security-opt=no-new-privileges`, `noexec` tmpfs, `--init`, userns-remap,
      caps, session-keyed volume, `HOME`=workspace, empty env, labels + heartbeat)
- [ ] `docker/sandbox.Dockerfile` — pinned-by-digest thick image; scanned;
      built once; no credentials, no Hugin source; `docker` → `sandbox` extra
- [ ] `sandbox/ssh.py` — `ssh` backend (shell-out, no `paramiko`); throwaway key;
      `ForwardAgent=no`/`BatchMode=yes`/`ConnectTimeout`/`ServerAliveInterval`;
      remote command under `systemd-run`/`timeout`/tmux so Hugin kills the remote
      job; ControlMaster socket owned + cleaned in `stop()`. (Secrets /
      provisioning / cost story written first.)
- [ ] Background exec: `bash` returns `ToolResponse(response_interaction=Waiting)`
      for long commands; `bash_output` poll tool; subprocess runs off the step
      thread so a 120s build stops freezing siblings
- [ ] `AgentCall` `inherit_workspace` option so delegated children start
      populated
- [ ] `network: true` egress control (block link-local/metadata/RFC1918; proxy
      allowlist)
- [ ] Persistent shell per agent (pexpect) so `cd`/`export`/`source` persist —
      or, if deferred, remove `cd` from allowlist and bold the stateless contract
- [ ] Tests: docker hardening asserted + containment of
      `python3 -c 'os.system(...)'` (`slow`, skipped without a daemon)

**Done when:** the same config runs unchanged with `backend: docker` (contained,
no network) or `backend: ssh` (disposable remote), and `financial_newspaper`
runs a real build without freezing the edition.

## Phase 3 — Human escalation

- [ ] `on_violation: ask_human` → `ToolResponse(response_interaction=AskHuman)`
      (the correct pattern; a bare `AskHuman` raises)
- [ ] Degrade to `deny` when the session is non-interactive (else the agent
      parks forever)
- [ ] Escalation shows *capabilities/effects*, not a raw base64 string;
      approve-once is scoped to an exact command hash, never "allow this binary"
- [ ] Surface pending command in `hugin interactive` / `monitor`

**Done when:** an out-of-policy command asks rather than fails, and a
non-interactive run degrades cleanly.

> The `ssh`/remote backend lives in Phase 2 alongside `docker` (both are
> additive isolation choices). Its harder sub-problems — idempotency across a
> mid-command partition, and the secrets/provisioning/ownership/cost story —
> must be written up before that code is built, not during.

## Phase 4 — The harness blend (spin out as its own task)

Projection down (`TASK.md`, `ENVIRONMENT.md` — generated from `Policy` —,
`memory/*.md`, read-only) and harvest up (`outbox/` → `Artifact`s, with
`realpath`/`O_NOFOLLOW` confinement). Design task, written *after* watching
real agents use phases 1–2. Parked in `notes.md`.

## Review

Per `CLAUDE.md`, re-run `/panel-review` on the Phase 1 *implementation* before
merge — this is security-sensitive and the policy engine is exactly the kind of
thing that looks right and isn't. For Phase 2, the security judge's containment
test is the acceptance gate for each isolation backend: `python3 -c
'os.system("id")'` must be *contained by the runtime* (the container, or the
disposable remote) — provably, not merely denied — while the docs never claim
the allowlist stopped it.
