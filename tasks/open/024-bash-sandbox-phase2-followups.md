---
title: Bash sandbox — phase 2 design items and deferred hardening
state: OPEN
labels: [enhancement, security, tech-debt]
priority: medium
---

# Bash sandbox — phase 2 design items and deferred hardening

Follow-ups deferred from the Phase 1 hardening pass (task 023). A four-judge
panel review of the Phase 1 implementation (security / framework architecture /
agent-usability / SRE) surfaced these; the load-bearing "real on local today"
findings were fixed before the Phase 1 PR, and the items below — genuinely
phase-2 design decisions or low-severity polish — were deferred here so they are
tracked rather than lost.

## Status (2026-07-20) — most items shipped

The substantive items landed across six focused PRs:

- **PR #61** — per-spec ownership, backend registry, storage-derived root.
- **PR #72** — thread-safe `SandboxManager.get()`, audit counters emitted at
  `Session.close`, `audit.jsonl` size-bounded.
- **PR #73** — consistent `rm`-target deny, `from_dict` policy-key hint.
- **PR #74** — one-time environment affordance on first bash use.
- **PR #75** — unique, absolute per-command spill path (also task 030).
- **PR #76** — `put_file`/`get_file` confined to the agent's workspace.
- **This PR** — `Session.close()` wired into the create-run-local entry points
  (`hugin create`, `data_analyst`, `baby_hugin`).

**Deferred (with pointers):**
- **`_resolve_cwd` realpath** — belongs in each backend's path model (realpath is
  host-relative; the tool sees container/remote paths), not the shared resolver;
  local exec is unconfined anyway. Do with the per-backend confinement work.
- **`Session.close()` for the escaping-session apps** (`financial_newspaper`,
  `rap_machine`, `the_hugins`) — they return the session to an orchestrator with
  monitor threads / loops; wire `with Session(...)` at that boundary when the app
  first adopts bash (a no-op until then).
- **"Earlier output elided" marker** — lives in the core `stack.py` render loop
  and is generic to any `context_window` tool (LOW; the tool description already
  tells the model to persist to files).
- **Remote lifecycle + secrets seam** — cross-backend phase-2; tracked in task
  030 (secret seam + reaper generalization).
- **bash-vs-structured-tools routing guidance** (LOW) — doc polish.

## Phase 2 design (do before docker/ssh backends land)

**Status:** the three de-risking foundation items — per-spec ownership, the
backend registry, and the storage-derived sandbox root — landed together on
branch `bash_sandbox_phase2_foundation`. The remaining items below are still
open.

- [x] **Per-spec (or per-agent) sandbox ownership.** *(architect, HIGH for
  phase 2)* ~~Today `session.sandbox` is a single manager built first-writer-wins
  from whichever agent runs bash first; a second agent's differing spec
  (`backend: docker`, `network: false`, cpu/memory caps) is silently ignored, so
  an agent's isolation is decided by call order.~~ **Done** (branch
  `bash_sandbox_phase2_foundation`): `session.sandboxes: Dict[SandboxSpec,
  SandboxManager]`; the tool resolves the manager for the calling agent's own
  spec, same-spec agents share a backend, all are torn down in `Session.close`.
- [x] **Backend selection via a registry, not a hardcoded enum + if/elif.**
  *(architect, MEDIUM)* ~~`create_sandbox` / `SandboxSpec.backend`
  `Literal["local","docker","ssh"]` bypass the framework's `Registry` idiom; a
  third-party backend can't be added without editing core.~~ **Done** (branch
  `bash_sandbox_phase2_foundation`): backends are registered as lazy-import
  loader thunks keyed by name (`register_backend` / `registered_backends`);
  `SandboxSpec.backend` is a free `str` validated against the registry.
- [x] **`put_file`/`get_file` need agent context.** *(architect, MEDIUM)* **Done
  (PR #76):** the file methods now take `(agent_id, branch, path)` and confine to
  the agent's own workspace like `exec`'s cwd (a shared pure `_agent_root` per
  backend; docker maps the container path to the host bind-mount first) — a
  traversal into a sibling agent's tree is refused, proven by a cross-backend
  contract test.
- [ ] **Remote lifecycle + secrets seam.** *(SRE, MEDIUM)* Liveness is a host
  PID and the workspace is a local dir — neither transfers to a container/VM on
  another host; the reaper is local-only (can't reap containers/SSH). Phase 2
  needs backend-owned resource handles + TTL/heartbeat that `close()`/reaper act
  on generically, and a secret-provisioning hook on `SandboxSpec`/`Policy`
  (rather than the hardcoded PATH/HOME/LANG/TERM env in `LocalSandbox`).
- [ ] **`_resolve_cwd` should realpath, not just normpath.** *(security,
  MEDIUM, latent)* It catches lexical `..` but follows symlinks; on local `exec`
  is unconfined anyway, but this is the backend-agnostic cwd gate the docker/ssh
  backends will inherit. Mirror `LocalSandbox._confine`'s realpath check (share
  a helper) — but realpath is host-relative, so it belongs with the isolating
  backend's path model.
- [~] **Wire `Session.close()` into app entry points and `hugin create`.**
  *(SRE/architect)* **Partly done:** `hugin create`, `data_analyst`, and
  `baby_hugin` (create-run-finish locally) now close via try/finally. Deferred:
  the apps that *return* the session to an orchestrator with monitors/loops
  (`financial_newspaper`, `rap_machine`, `the_hugins`) — wire at that boundary
  when they first adopt bash (a no-op until then).
- [x] **Thread-safety.** *(architect, latent)* **Done (PR #72):**
  `SandboxManager.get()` serializes first-creation with double-checked locking,
  and the lifecycle counters go through the audit lock (`audit.bump`) instead of
  a raw `Counter += 1`; the JSONL append was already lock-guarded (PR #65).

## Observability / ops

- [x] **Emit the audit counters somewhere.** *(SRE, HIGH)* **Done (PR #72):**
  `Session.close` logs each sandbox's outcome counters (INFO), plus a WARNING
  naming the "hot" failing outcomes (`denied`/`timed_out`/`infra_error`/
  `sandbox_start_failures`). The `hugin monitor`/`interactive` per-session
  commands view (spec §8) is still open.
- [~] **Bound `audit.jsonl` and workspace growth.** *(SRE, MEDIUM)* **Partly done
  (PR #72):** the audit file rotates to one `.1` backup past a size cap. Still
  open: per-`(agent,branch)` workspaces and spill files accumulate for the
  session lifetime (reaper is session-granularity) — reap/account idle subdirs.
- [x] **Derive the sandbox root from session storage.** *(SRE/architect,
  MEDIUM)* ~~`"./storage/sandboxes"` is duplicated in four places and is cwd-
  relative, decoupled from `--storage-path`; run from a different dir or with a
  custom storage path and the self-heal reaper never finds the workspaces.~~
  **Done** (branch `bash_sandbox_phase2_foundation`): a single
  `sandbox_root_for(storage_base)` derives `<base>/sandboxes` from the session's
  storage base path; the bash tool and the CLI reaper both call it, so a custom
  `--storage-path` run keeps its sandboxes with its sessions and the reaper
  finds them.

## Usability / low severity

- [x] **"Here is your environment" affordance.** *(harness, MEDIUM)* **Done
  (PR #74):** the first successful bash result per agent carries an `environment`
  note rendered from the resolved spec — backend, network on/off-and-how,
  workspace path, fresh-shell reminder. Spec-derived (no probe) so it can't
  drift. (A binary-presence probe could still be layered on later.)
- [ ] **"Earlier output elided" marker.** *(harness, LOW)* `context_window: 5`
  silently drops whole older bash interactions with no trace; the model re-runs
  or hallucinates. (Description now tells it to persist what it needs — a marker
  would still help.)
- [ ] **bash-vs-structured-tools routing guidance** when bash is composed with
  other tools. *(harness, LOW)*
- [x] **`rm` denied-target set is inconsistent** (`/` denied, `/etc` `/usr`
  allowed). *(security, LOW)* **Done (PR #73):** a recursive-force `rm` of any
  system top-level dir is now denied too; relative/deep/non-recursive stay
  allowed.
- [x] **`from_dict` misplaced-key error** — a valid policy key at the top level
  of `options.bash` (not nested under `policy:`) reports "unknown sandbox keys";
  a targeted hint would help. *(architect, LOW)* **Done (PR #73):** the error now
  names the misplaced policy keys and points at `options.bash.policy`.
- [x] **Spill file is single/overwritten and follows `cwd`.** *(harness,
  MEDIUM)* **Done (PR #75):** each truncated command spills to a unique file and
  `ExecResult.spill_path` carries its absolute path (host/container/remote),
  reported as `full_output` — no overwrite, findable from any cwd.
