# Panel review — verdict and resolutions

A four-role panel (security engineer, framework architect, agent/harness
designer, SRE/ops) reviewed the v1 design. The architecture survived; five
load-bearing claims did not. This file records what they found and how the
design changed in response. `description.md`, `spec.md` and `plan.md` have been
revised to match; this file is the "why".

## What survived

Backend / policy / workspace as three orthogonal features; the `Sandbox` ABC
mirroring `Storage`; fail-closed command parsing; deferring the harness blend
until an agent has been observed using bash.

## The keystone reframe: the container is the boundary, not the allowlist

Three of four judges independently found that `DEFAULT_ALLOW` was security
theatre. It contained `python3 uv git awk sed find curl` — each a general
code-execution or network hatch the AST walk never looks inside — so
`python3 -c 'os.system(...)'` passed cleanly while `mkdir` was denied. The
allowlist was *inverted safety*: maximal friction on harmless commands, zero
protection on harmful ones. And nothing modelled that the command is composed
by the LLM from untrusted input (files, `curl` output), so an allowlisted
interpreter is a direct pipe from an injected instruction to execution.

Resolution, which collapses the security *and* usability critiques together:

- **The isolation boundary is the runtime you choose, not the allowlist.** The
  allowlist is never sold as isolation on any backend. What contains a
  confused-or-injected agent is a container, a disposable remote machine, or —
  on `local` — nothing, stated plainly.
- **Inside a real boundary, policy is permissive by default** (a blunt denylist
  for accidents + resource caps), because the runtime contains it. This also
  ends the allowlist thrash the harness judge documented.
- **Prompt injection is contained by the runtime invariants** — `network=none`,
  no secrets in env or on disk, `HOME`=workspace, disposable filesystem — and
  the design says so explicitly. The allowlist and the human-escalation flow
  are *not* claimed as injection defenses.

> **Correction (post-review, per direction).** The panel's resolution was
> originally written as "Docker is the *default* backend and the local backend
> is a demoted `unsafe_host` opt-in." That over-rotated: it conflated two
> separable things — *don't claim isolation you don't have* (the real finding)
> with *you must use Docker* (not a finding). Docker is only one way to get a
> boundary; a disposable VPS over SSH is another, equally first-class, and
> running `local` with no isolation is a legitimate choice for trusted/iterative
> work. So the three backends are **peers with no privileged default and no
> Docker dependency** (the package installs and `bash` runs on `bashlex`
> alone). The honesty requirement is backend-*neutral*: every backend declares
> exactly what boundary it does and doesn't provide. The allowlist-isn't-a-
> boundary finding stands unchanged — it was always about not lying, not about
> mandating containers.

## Structural findings (design claims that were false)

- **"Return type stays open for phase 6" — false.** `ToolCall.step`
  (`interaction/tool_call.py:54-60`) special-cases only `AgentCall`; any other
  bare `Interaction` raises `ValueError`. And `include_reason: true` makes
  `execute_tool` (`tools/tool.py:391-395`) raise unless the result is a
  `ToolResponse`. → Drop `include_reason` for bash; route every deferral
  (long-running `Waiting`, escalation `AskHuman`) through
  `ToolResponse.response_interaction`, which `ToolResult.step`
  (`tool_result.py:107-108`) already honors.

- **A builtin has no owner for `env_vars["sandbox"]`.** The `worlds` analogy
  fails: an app (`the_hugins/run.py`) builds and drives `worlds`, but a generic
  `hugin run` has no session-creation hook that instantiates a framework
  service. → Give `Session` a typed, lazily-created `session.sandbox`
  (`SandboxManager`), read by the tool via `stack.agent.session.sandbox`, torn
  down by `Session.close()`. "No framework change needed" was the root error.

- **Teardown must be Phase 1, not Phase 2.** The *local* backend already leaks
  process groups (on timeout) and never-GC'd `storage/sandboxes/<id>/` dirs.
  And `atexit`/`finally` do not run on SIGTERM (CPython's default disposition
  terminates without raising), SIGKILL, OOM-kill, or laptop-sleep — i.e. every
  non-clean exit, which is the common case. → Out-of-band reaping is the
  **primary** lifecycle mechanism: stamp each sandbox with
  `hugin.session` / `hugin.owner_pid` / `hugin.ttl` / heartbeat; a reaper runs
  at the start of every `hugin` invocation and kills only dead-owner or stale
  sandboxes (never by session label alone — that races live peers). `close()`
  + a `SIGTERM`/`SIGINT` handler + `atexit` are the second/third lines.

- **Synchronous `execute_tool` freezes every sibling agent and branch.**
  `Session.run` (`session.py:170-195`) is single-threaded round-robin;
  `execute_tool` (`tool.py:381`) calls the tool synchronously. One 120s
  `uv sync` stalls the whole `financial_newspaper` edition — session time
  becomes `sum` of command durations, not `max`, and the monitor looks hung
  because `save_session` is after the step loop. → Pull background exec forward
  to phase 2/3 (`Waiting` via `response_interaction` + a `bash_output` poll
  tool); until then ship a *short* interactive default timeout (10–20s), a
  separate policy `max_timeout_s`, and a loud doc note.

## Framework facts that broke stated safeguards (grounded in code)

- **The framework executes exactly ONE tool call per turn.**
  `anthropic.py:125` has a `# TODO support multiple tool calls` and keeps only
  the *last* `tool_use` block. Bash agents are the heaviest batchers
  (`ls` + `cat a` + `cat b` in one turn) → the earlier calls silently never
  run and the model believes it saw their output. This is close to a
  prerequisite. → At minimum, detect >1 `tool_use` and return an explicit error
  for the dropped ones so the model doesn't proceed on phantom results. Flag
  multi-tool-call support (task 006) as a hard dependency.

- **`reduced_context_window` does not drop stdout.** In reduced mode the
  renderer only reformats DataFrames (`renderer.py:82-89`); string stdout is
  kept verbatim, and the `ignore_list` blanking applies to the assistant's
  `tool_use` args, never the tool_result. So 30 commands accumulate ~½ MB of
  stdout permanently — exactly the blow-up the design claimed to prevent. →
  Use `include_only_in_context_window: true` with a small `context_window`
  (`stack.py:254-261` actually drops older ones).

- **The host-filesystem builtins see a different world than bash.**
  `read_file`/`search_files` call `Path(path).resolve()` on the *host*
  (`read_file.py:58`); bash runs in the sandbox workspace (a different
  filesystem under Docker). A model that reads `config.yaml` with `read_file`
  then edits it with bash edits two different files. → Drop
  `read_file`/`list_files`/`search_files` from any bash-enabled non-local
  config; keep only structured tools the framework must observe/persist
  (`save_insight`, `save_file`→Artifact, `finish`). Enforce per-config, not by
  trusting the model to choose.

## Agent-usability findings (cheap wins wrongly deferred)

- **The agent is told nothing about the box.** The fix is not the phase-5
  projection machinery — it's ~10 lines in the tool *description* (the one
  thing the model always sees, `anthropic.py:56`): workspace layout, installed
  toolchain, "no network", the stateless-shell warning, and the exact
  allow/deny line **generated from the `Policy` object** so it can't drift from
  enforcement. In v1.

- **Stateless-per-call breaks the model's mental model, and `cd` on the
  allowlist actively lies** — it returns exit 0 and silently no-ops next call,
  reinforcing the wrong model. → Persistent shell per agent (pexpect/coprocess,
  one per `workspace_for(agent.id)`) *inside* the disposable container. This
  also resolves the only real tension between judges: security wants ephemeral,
  harness wants stateful → a persistent shell inside a disposable container is
  both.

- **`is_error = exit_code != 0` mislabels normal exits.** `grep`/`rg` no-match
  and `diff`-with-differences exit 1; flagged as errors, the model retries or
  apologizes. → Reserve `is_error=True` for denial / timeout / infra failure;
  a process that ran to completion is `is_error=False` with `exit_code` +
  explicit `timed_out` / `denied` fields in content.

- **head+tail truncation corrupts the important outputs** — it hands the model
  syntactically invalid JSON and elides the pytest traceback that lives in the
  middle. → Tail-biased truncation (the actionable error is usually last),
  spill full output to `/workspace/.hugin/last_output.txt`, and tell the model
  how to read more; never claim structured output survived truncation.

- **`include_reason: true` is a token tax** on a tool called dozens of times,
  producing restated intent ("I am listing the directory"). Also forbidden by
  finding above. → `include_reason: false`; reserve a justification for the
  escalation path where a human actually reads it.

- **Don't expose `timeout` to the model** while the cap is hidden and execution
  is synchronous — it sets 600, gets clamped to 120, is confused. Hide it until
  background exec exists.

## Docker defense-in-depth (was under-specified)

Required, not optional: `--cap-drop=ALL`,
`--security-opt=no-new-privileges:true`, `--tmpfs /tmp:rw,noexec,nosuid,size=`,
`--ulimit nproc/nofile`, `--init`, keep (never disable) the default
seccomp+apparmor profiles, userns-remap. `HOME`=workspace on every backend
(else `cat ~/.aws/credentials` defeats env-scrubbing entirely). `network:true`
must block link-local / metadata (`169.254.0.0/16`) and RFC1918 by default,
ideally via an egress-allowlist proxy — otherwise it's SSRF to cloud IAM
credentials. Execute via `bash -c` so the validated dialect matches the run
dialect (`subprocess(shell=True)` uses `/bin/sh`=dash, not the bash bashlex
parses). The AST walk must also reject dangerous assignment prefixes
(`LD_PRELOAD`, `BASH_ENV`, `IFS`, `GIT_*`) and descend into wrapper binaries
that run their argument (`timeout env xargs nice nohup setsid`). Image pinned
by digest (not a mutable tag), scanned, signed. Symlink TOCTOU defeats static
path scoping, so harvest/`get_file` must `realpath`-confine and open
`O_NOFOLLOW`.

## Config validation

`Policy.from_dict` / `SandboxSpec.from_dict` must reject unknown keys, validate
every `Literal`, and fail **loud** if `options.bash` exists but is malformed —
never silently fall back to the permissive-inside-container default when a
typo'd key (`mode: allowlst`, a mis-indented `policy:` block) drops the policy.
Precedence between config / session / default is explicit key-level merge.

## Enforcement location

Enforce policy inside `Sandbox.exec` (fail-closed, raises), not only in the
tool — so any future caller (a `git` tool, the phase-5 harvest layer, a test)
is checked by construction. The tool additionally calls `evaluate()` only to
render a friendly `ToolResponse` / escalation.

## Observability (into Phase 1)

A structured, append-only command audit log (session, agent, command, decision,
exit code, duration, `truncated`/`timed_out`/`oom` flags) plus counters
(run / denied / timed-out / container-starts / start-failures). `hugin monitor`
and `hugin interactive` get a per-session "commands" view rendering denials and
timeouts distinctly. This is table stakes for debugging a security-sensitive
feature, not polish.

## Per-agent isolation

cwd must be keyed by `(agent.id, branch)`, not `agent.id` alone — branches
share one `agent.id` and would collide (two branches running `git checkout` in
one dir). `AgentCall` needs an explicit workspace-inheritance option so a
delegated child can start in a populated dir instead of an empty one. One
container per session means all agents share a uid and filesystem — document
that agents in a session share a trust level, or offer per-agent containers.

## SSH / VPS (phase 4, story rewritten before build)

Dedicated throwaway key per session, `ForwardAgent no`, `BatchMode yes`,
`ConnectTimeout` + `ServerAliveInterval` (else a network partition hangs the
client while the remote command runs on). Run the remote command under
`systemd-run --scope` / `timeout` / a named tmux so Hugin can kill the *remote*
job, not just the local client — remote commands are not idempotent to retry.
Own the `ControlMaster` socket path and clean it in `stop()`. Better: target a
hardened container on the remote (`ssh host docker run …`) rather than the bare
host. Provisioning / ownership / cost / secrets must be written before phase 4,
not during it.

---

# Implementation panel review (Phase 1, post-build)

A second four-judge panel (security / framework architecture / agent-usability /
SRE) reviewed the **implemented** Phase 1 code before the PR. Findings that were
real on the local backend today, plus the cheap honesty/robustness set, were
fixed in the branch; genuine phase-2 design items were deferred to
`tasks/open/024-bash-sandbox-phase2-followups.md`.

## Fixed before the Phase 1 PR

- **Wrapper-prefix bypass** — `env dd`, `timeout 60 dd`, `nice -n 19 dd`,
  `xargs … reboot`, `sudo reboot`, `command reboot`, `find -exec shutdown` all
  passed the denylist/allowlist/strict mode (the AST walk saw only the first
  word; `_WRAPPERS` was dead code). Now peels wrappers to the command they run,
  in every mode, without false-denying data-position names.
- **Unbounded output → orchestrator OOM** — `communicate()` buffered the whole
  child output in parent memory before truncation. Now streamed with a 2MB
  ceiling; past it the group is killed and the model sees an "output exceeded"
  note.
- **Timeout escape hang** — a `setsid`-escaped child holding the stdout pipe made
  the post-kill `communicate()` block until it exited (defeating the timeout).
  Now a bounded drain + kill by saved pgid.
- **Reaper deleted a live session's workspace** — the owner stamp was written
  once, so a resumed session kept the dead PID and a concurrent reaper deleted
  the running workspace. Now re-stamped on every start with a process start-time
  token (PID-reuse safe), plus per-entry crash guards (vanished dir / null pid).
- **Audit dropped pre-backend denials** — the audit was built with the manager on
  the allow path, so a denied first command recorded nothing. Manager (hence
  audit) now resolved before the policy check.
- **Model UX** — parse failures surfaced as `unparseable` (rephrase) vs `denied`;
  `timeout_s` lever added (max_timeout_s was dead config); `oom_killed` → is_error;
  spill path returned on truncation; clearer escalation note.
- **Honesty** — `workspace_only`/`network` docstrings corrected (no code enforces
  them); one-shot runtime warning that the local backend has no isolation.
- **Lifecycle** — `Session.close()` wired into both `hugin run` paths (had no
  production caller).

## Deferred (tracked in task 024)

Per-spec/per-agent sandbox ownership; backend registry; `put_file`/`get_file`
agent context; remote lifecycle + secrets seam; `_resolve_cwd` realpath (latent,
phase-2 path model); counter emission/alerting + monitor commands view; audit &
workspace growth bounds; sandbox root from storage config; thread-safety;
environment-probe affordance; elided-output marker; spill-file uniqueness;
minor policy/error polish.
