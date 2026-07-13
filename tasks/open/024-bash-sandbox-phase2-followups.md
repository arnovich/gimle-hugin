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

## Phase 2 design (do before docker/ssh backends land)

- [ ] **Per-spec (or per-agent) sandbox ownership.** *(architect, HIGH for
  phase 2)* Today `session.sandbox` is a single manager built first-writer-wins
  from whichever agent runs bash first; a second agent's differing spec
  (`backend: docker`, `network: false`, cpu/memory caps) is silently ignored, so
  an agent's isolation is decided by call order. Move to
  `session.sandboxes: Dict[SandboxSpec, SandboxManager]` (or per-agent), all torn
  down in `Session.close`. Cheap interim guard: reject a second, differing spec
  with a clear error instead of silently reusing the first.
- [ ] **Backend selection via a registry, not a hardcoded enum + if/elif.**
  *(architect, MEDIUM)* `create_sandbox` / `SandboxSpec.backend`
  `Literal["local","docker","ssh"]` bypass the framework's `Registry` idiom; a
  third-party backend can't be added without editing core. Register backends
  (lazy-import thunks) keyed by name.
- [ ] **`put_file`/`get_file` need agent context.** *(architect, MEDIUM)* They
  take no agent/branch and `_confine` resolves against the *session* root, while
  `exec` cwd is agent-scoped — three confinement scopes under one "workspace"
  word. Docker will need per-agent host↔container path mapping. Give the file
  methods an explicit workspace/agent argument, or drop them until a caller
  exists (currently unused speculative API).
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
- [ ] **Wire `Session.close()` into app entry points and `hugin create`.**
  *(SRE/architect)* Phase 1 wired the two `hugin run` paths; `apps/*/run.py` and
  `create_agent.py` still don't call it (they don't use bash yet, so nothing
  leaks today). Convert to `with Session(...)` / try-finally when phase-2 stop()
  becomes non-trivial.
- [ ] **Thread-safety.** *(architect, latent)* `SandboxManager.get()` (check-
  then-act) and the audit (`counters += 1`, JSONL append) are unguarded; correct
  only because the step loop is single-threaded and `Tool.execute_tool` is sync.
  Add a lock, or document the single-threaded-scheduler precondition loudly,
  before anyone parallelizes stepping.

## Observability / ops

- [ ] **Emit the audit counters somewhere.** *(SRE, HIGH)* `run / denied /
  timed_out / infra_error / escalated / sandbox_starts / sandbox_start_failures`
  live only in memory and are discarded at exit — no alerting surface for a
  misbehaving agent (e.g. a loop of timeouts). Emit them at `Session.close` as a
  structured log line/metric; consider a "hot" WARN threshold. Add the per-
  session commands view to `hugin monitor` / `hugin interactive` (spec §8).
- [ ] **Bound `audit.jsonl` and workspace growth.** *(SRE, MEDIUM)* The audit
  file is append-only with no rotation; per-`(agent,branch)` workspaces and spill
  files accumulate for the session lifetime (reaper is session-granularity).
  Rotate the audit by size; reap idle agent/branch subdirs or at least account
  their size.
- [ ] **Derive the sandbox root from session storage.** *(SRE/architect,
  MEDIUM)* `"./storage/sandboxes"` is duplicated in four places and is cwd-
  relative, decoupled from `--storage-path`; run from a different dir or with a
  custom storage path and the self-heal reaper never finds the workspaces. Thread
  one root from `Environment`/storage config.

## Usability / low severity

- [ ] **"Here is your environment" affordance.** *(harness, MEDIUM)* The agent
  discovers OS / available binaries / whether network works by trial and error
  (`sed` GNU-vs-BSD, `rg` may be absent). Inject a short probe (uname, key binary
  presence, workspace path, network-permitted) on first use or in the system
  prompt; don't recommend tools in the template the backend may lack.
- [ ] **"Earlier output elided" marker.** *(harness, LOW)* `context_window: 5`
  silently drops whole older bash interactions with no trace; the model re-runs
  or hallucinates. (Description now tells it to persist what it needs — a marker
  would still help.)
- [ ] **bash-vs-structured-tools routing guidance** when bash is composed with
  other tools. *(harness, LOW)*
- [ ] **`rm` denied-target set is inconsistent** (`/` denied, `/etc` `/usr`
  allowed). *(security, LOW)* Either match any absolute non-workspace top-level
  target or rely on confinement once it's real.
- [ ] **`from_dict` misplaced-key error** — a valid policy key at the top level
  of `options.bash` (not nested under `policy:`) reports "unknown sandbox keys";
  a targeted hint would help. *(architect, LOW)*
- [ ] **Spill file is single/overwritten and follows `cwd`.** *(harness,
  MEDIUM)* A later truncated command overwrites `.hugin/last_output.txt`, so a
  deferred read gets the wrong output; and with `cwd: subdir` it lands under the
  subdir. Consider a unique per-call spill name returned in the response.
