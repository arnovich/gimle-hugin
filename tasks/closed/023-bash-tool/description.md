---
title: Bash tool with pluggable execution sandbox
state: CLOSED
labels: [enhancement, tools, security]
priority: high
created: 2026-07-13
closed: 2026-07-15
---

> **Status (2026-07-15):** Phase 0 (one-tool-call guard, PR #58) and Phase 1
> (core vertical on the `local` backend) are **shipped and merged** (PR #59),
> hardened after a 4-judge implementation panel review (see `review.md`). The
> remaining phases are tracked as their own open tasks —
> `tasks/open/024`–`029` and `tasks/open/README-bash-sandbox-roadmap.md`. This
> folder is retained as the design source of truth (`spec.md`/`plan.md`/
> `notes.md`/`review.md`) that those tasks point back to.

# Bash tool with pluggable execution sandbox

Give Hugin agents the ability to run shell commands, with the execution
backend pluggable: directly on the host, in a local container, or on a
remote machine. Nothing in `src/gimle/hugin` currently shells out — no
`subprocess`, no docker, no ssh — so this is greenfield.

## Why

A shell is the universal escape hatch. Today every capability an agent needs
must be anticipated and hand-built as a tool (`read_file`, `list_files`,
`search_files`, ...). With `bash`, capable models can explore, inspect,
transform and build without the tool registry having to predict what they
will want. It also unlocks the whole class of agents Hugin currently cannot
express: anything that touches a repo, a build, a data file, or a CLI.

The cost is that a shell is also the universal footgun, so the isolation and
policy story has to be part of the design from the first commit rather than
bolted on later.

## The core framing: bash is three features, not one

Keeping these orthogonal is the single most important design decision.
Conflating them is what turns this into a mess.

1. **Execution backend — *where* the process runs.** A narrow `Sandbox`
   protocol (`exec` / `put_file` / `get_file` / `start` / `stop`), mirroring
   the existing `Storage` ABC, with `LocalSandbox`, `DockerSandbox` and
   `SSHSandbox` as implementations. Nothing above this layer knows which
   backend it got.

2. **Policy — *what* is allowed.** Allow/deny lists, path scoping, network
   on/off, timeouts, output caps, and escalation-to-human. A pure function
   over a parsed command: `evaluate(command, policy) -> Allow | Deny | Escalate`.

3. **Workspace — *what is on the filesystem* when the command runs.** Image
   contents, directory layout, what (if anything) Hugin projects into it.
   This is the only genuinely novel piece; see `notes.md`.

## Decisions taken

> These were revised after a four-role panel review. See `review.md` for the
> findings and why each decision landed where it did.

- **The isolation boundary is whichever backend you choose — not the allowlist.**
  A command-word allowlist stops meaning anything the moment an interpreter is on
  it (`python3 -c '...'`, `awk 'BEGIN{system()}'`, `git -c core.pager='!sh'`),
  and the command is composed by the LLM from untrusted input, so injection walks
  straight through it. The allowlist is therefore never *sold* as isolation on
  any backend. What actually contains a confused-or-injected agent is the runtime
  you picked: a container, a disposable remote machine, or — if you chose
  `local` — nothing, stated plainly.

- **The three backends are peers; none is privileged and there is no Docker
  dependency.** The package installs and `bash` works with `bashlex` alone. The
  `docker` SDK is an optional extra pulled only when you select that backend;
  `ssh` shells out to the `ssh` binary and needs no library. A config must name
  its backend — there is no silent default that decides *where your agent's shell
  runs* for you.
  - `local` — runs on the host. **No isolation boundary.** The policy is an
    accident-guard only, and the knobs a bare subprocess can't enforce
    (`network`, `cpu`, `memory`) *raise* rather than silently no-op — a control
    that lies is worse than an absent one. Legitimate for iterating and trusted
    tasks; `examples/bash_agent` uses it so the example needs zero infra.
  - `docker` — a local container boundary (`--network=none`, `--cap-drop=ALL`,
    `no-new-privileges`, read-only root, `noexec` tmpfs, userns-remap, caps).
  - `ssh` — the **remote machine itself is the boundary**; the design steers you
    to a disposable VPS you don't mind the agent breaking, ideally a container on
    it. First-class, not an afterthought to Docker.

- Inside a real boundary (container or disposable remote) the policy can be
  *permissive* — a blunt denylist for accidents — because the runtime, not the
  wordlist, is what contains the agent.

- **Sandbox scope: worktree hybrid.** One sandbox per `Session`; one working
  directory per `(agent, branch)` inside it, plus a shared `/workspace/common/`
  for deliberate hand-offs. (Keying by agent alone collides concurrent branches
  and starves delegated sub-agents — see `review.md`.) This is the worktree
  pattern `CLAUDE.md` already prescribes for parallel Claude agents, applied one
  level down. Note the honest limit: all agents in a session share one container
  uid and filesystem, so they share a trust level.

- **`Session` owns the sandbox, and teardown is Phase 1.** A typed, lazily-created
  `session.sandbox` (not an `env_vars` convention a builtin can't satisfy),
  with `Session.close()` and out-of-band reaping landing in Phase 1 — the local
  backend already leaks process groups and workspace dirs, and a remote box
  leaks orphaned jobs, so cleanup can't wait for a later backend.

- **v1 is bash-only against a plain workspace — but the tool description carries
  the environment.** The task, memory and results reach the agent as they do
  today. The Pi-style projection/harvest layer is deferred (parked in
  `notes.md`). But the ~10-line "what's on this box, what's allowed, the shell is
  stateless" text goes in the tool description from day one — it's the cheapest,
  highest-value thing in the whole design and needs none of the phase-5 machinery.

## Threat model (be honest about it)

A deny-list matched against a bash *string* is not a security boundary. Neither
is an *allowlist* once an interpreter is on it: `python3 -c`, `uv run`,
`awk 'BEGIN{system()}'`, `find -exec`, `git -c core.pager='!sh'`,
`sed` with the `e` flag, `curl file://` all reach arbitrary execution or file
access without ever using `eval`/`$()`/`bash -c`. And because the command is
composed by the LLM from untrusted content (repo files, `curl` output), a
prompt-injected instruction reaches execution *entirely within policy*. So:

- **The runtime you choose is the boundary — a container or a disposable remote,
  or none.** The `docker` backend hardens the container (`--network=none`,
  `--cap-drop=ALL`, `--security-opt=no-new-privileges`, read-only root, `noexec`
  tmpfs, non-root + userns-remap, cpu/mem/pid caps, no docker socket, no host
  mounts beyond the workspace, `HOME`=workspace, no secrets in the env). The
  `ssh` backend leans on the remote machine being disposable. Injection is
  contained by *whichever* of these you picked — or, on `local`, not at all.
- **The policy engine is a guardrail against accidents, not a boundary.** It's
  permissive-by-default (blunt denylist: `rm -rf`, `git push --force`, raw writes
  to `/dev`) and is never sold as isolation on any backend.
- **The `local` backend has no boundary at all** and says so — no Docker required
  to run it, and no pretence that it isolates anything.

Consequences for the design: policy is enforced against a *parsed* command (AST
walk), fails closed on parse failure, is enforced *inside* `Sandbox.exec` (not
only in the tool) so every caller is checked by construction, and the command is
run through the same dialect it was parsed as (`bash -c`, not `/bin/sh`).

## Success criteria

- [ ] The package installs and `bash` runs with **no Docker present** (local
      backend, `bashlex` only); selecting `backend: docker` or `ssh` is an
      additive choice, not a prerequisite
- [ ] A config must name its backend; there is no silent default deciding where
      the agent's shell runs
- [ ] With `backend: docker`, an agent runs `bash` with no network and no host
      filesystem access beyond the workspace; a denied command is a clean
      `ToolResponse` it can recover from
- [ ] `python3 -c 'os.system("id")'`, `awk 'BEGIN{system(...)}'` and
      `git -c core.pager='!sh'` are contained by the chosen runtime (container or
      disposable remote), *not* by the allowlist, and the design nowhere claims
      the allowlist stopped them
- [ ] The `local` backend's unenforceable knobs (`network`/`cpu`/`memory`) raise
      rather than silently no-op, and it is documented as offering no isolation
- [ ] Two agents in one session get isolated `(agent, branch)` working
      directories and can hand off through `/workspace/common/`; two branches of
      one agent do not collide
- [ ] Policy engine is a pure function with table-driven tests, including the
      interpreter bypasses (`python3 -c`, `find -exec`, `awk system()`,
      `git -c`), wrapper binaries (`timeout`/`env`/`xargs`), assignment prefixes
      (`LD_PRELOAD`), path escape, and parse failure
- [ ] Command output cannot blow up the context window — verified against the
      *actual* knob (`include_only_in_context_window`, not `reduced_context_window`,
      which does not drop stdout)
- [ ] The tool description tells the agent the workspace layout, installed tools,
      "no network", the stateless-shell contract, and the policy-derived
      allow/deny line — generated from the `Policy` so it cannot drift
- [ ] Sandboxes self-heal: every non-clean exit (SIGTERM, SIGKILL, sleep) is
      reaped within one TTL by a dead-owner-scoped reaper, and `Session.close()`
      lands with the local backend in Phase 1
- [ ] A structured command audit log + counters exist from Phase 1

## Relationship to other tasks

- **005-builtin-tools** — `bash` subsumes several of the candidates there. Once
  this lands, revisit which file-oriented builtins are still worth having.
  (Current position: keep structured tools where the framework needs to
  *observe, validate or persist* a result; use bash for exploration and
  mechanical work.)
