# SSH / remote backend — design note (provisioning, secrets, cost, idempotency)

**Status: DRAFT, awaiting sign-off.** Task 026 makes this note a hard
prerequisite: the provisioning / secrets / ownership / cost / idempotency story
is written and signed off *before* any backend code. This is that note.

## Thesis

`backend: ssh` runs each command on a **remote machine, and the remote machine
is the boundary**. Unlike `docker` (where we construct the container and own
every hardening flag), here the isolation is a property of *where* the command
runs: a throwaway box the operator doesn't mind the agent breaking. Our job is
to (a) reach it safely, (b) run commands so a network partition can't hang us or
double-execute, (c) never leave secrets or a running job behind, and (d) not
leak money.

## The one load-bearing decision: who provisions the box?

Everything else (secrets, cost, teardown, reaper) follows from this. Two models:

### Option A — BYO host (operator-provisioned). **Recommended for v1.**

The operator stands up the disposable box (a VPS, a lab VM, a container host)
and configures SSH access; Hugin *connects* to it via `host:` and runs each
session in an isolated remote workspace. Hugin owns its own remote footprint
(workspace dir, running jobs, the ControlMaster socket) and cleans that up, but
it does **not** create or destroy the machine.

- **Provisioning:** none by Hugin. The operator's responsibility; the box's
  "disposability" is their hygiene (recreate/snapshot-reset periodically). We
  document this loudly and recommend targeting `ssh host docker run …` — a
  hardened container *on* the remote — so the box itself is never the last line
  of defence (Option A + docker-on-remote = defence in depth with no cloud API).
- **Secrets:** the operator decides what (if any) scoped, short-lived
  credentials live on / are injected into the box. Hugin ships **none** by
  default (v1 does network-limited work). A secret-injection seam is out of
  scope here (tracked in task 024); until it exists, the contract is: *never put
  long-lived credentials on a box the agent controls.*
- **Cost / ownership:** the operator owns the machine and its bill. Hugin cannot
  leak a VM because it never created one. It **can** leak a remote workspace or a
  runaway remote job, so those are what our teardown + reaper target.
- **Teardown:** `stop()` kills this session's remote jobs, removes the
  ControlMaster socket (local), and GCs the session's remote workspace
  (best-effort). The machine stays up for the operator to reuse or destroy.

Why v1: no cloud-provider coupling, no billing integration, no VM-lifecycle
reaper, shippable and genuinely useful, and it *is* the spec's framing ("a
throwaway box you don't mind the agent breaking"). It leaves a clean seam for B.

### Option B — Managed ephemeral VMs (Hugin provisions). **Future (task 030-class).**

Hugin calls a cloud/provisioner API to create a fresh VM per session, waits for
boot, injects a throwaway key, runs, then destroys it. Strongest isolation
(every session a clean box) but drags in: a provisioner abstraction (which
cloud?), **billing/cost-leak risk** (a failed teardown bills real money, so the
reaper MUST reap VMs by provider-ID + TTL via the cloud API — a whole subsystem),
30–90s provisioning latency per session, and a full cloud-credential story.

**Decision:** ship **A** now; design the SSHSandbox so a `provisioner` seam
(create/destroy hooks + a resource-id the reaper understands) can be added later
without reshaping the backend. Do **not** build B in this task.

## Idempotency / network partition (a correctness requirement, not polish)

A remote command interrupted by a partition is **not** safe to blindly retry —
it may have already run (half-run `rm -rf`, a `git push`, a `terraform apply`).
Rules:

1. **Don't hang the client.** Every `ssh` invocation uses `-o BatchMode=yes -o
   ConnectTimeout=<n> -o ServerAliveInterval=<n> -o ServerAliveCountMax=<n>`, so
   a dead peer surfaces as a fast error, not an indefinite block. The client-side
   read is *also* wrapped in the same host-side deadline pattern the docker
   backend uses (a worker-thread join), so nothing can hang the agent's turn.
2. **Kill the remote job, not just the client.** The command runs under a remote
   `timeout` (and, where available, `systemd-run --scope` or a named `tmux`/
   session id) so that when the client goes away the *remote* process is bounded
   and killable by session marker — closing the SSH pipe must not orphan a
   runaway on the box.
3. **A partition is non-retryable, and we say so.** If the connection drops
   mid-command, we return a clean `infra_error` with an explicit *do-not-retry*
   note (the same surface the docker start-failure fix uses), never a silent
   re-exec. Best-effort recovery (a per-command remote exit-code marker file we
   can read on reconnect to learn the real outcome instead of guessing) is a
   nice-to-have, not required for v1 — v1 fails safe by refusing to retry.

## Lifecycle & reaper

- **Remote workspace:** `~/.hugin-sandbox/<session>/agents/<agent>/<branch>/`
  (or an operator-set base), with a remote owner marker (session id + local owner
  PID + start-time token + a TTL) mirroring the local/docker stamp.
- **Local reaper can't reach the remote.** The Phase-1 reaper walks local dirs;
  it cannot SSH out. So remote cleanup is: `stop()` on a clean exit (primary),
  plus a **best-effort SSH sweep** of stale session workspaces/jobs on the *same*
  configured host at startup (only for hosts we already have a live connection
  config for — we do not connect to arbitrary hosts to reap). The general
  remote-resource reaper (by id + TTL/heartbeat, shared with docker) is the
  task 024/030 generalization; this backend plugs into that seam when it lands.
  **Documented gap for v1:** an abrupt local exit may leave a remote workspace
  until the next run against that host reaps it (bounded by TTL); it never leaks
  a VM (Option A creates none).

## Hardening (what "the boundary" means here)

- **Prefer a hardened container on the remote:** `ssh host -- docker run <the
  same hardened flags as the docker backend> …`. This composes the two backends —
  the remote box is the outer boundary, the container the inner — and reuses the
  docker hardening contract. Configurable; when off, the bare remote host is the
  boundary and is only safe if genuinely disposable (documented).
- **Connection hygiene:** `-o ForwardAgent=no` (never forward the operator's
  agent to a box the agent controls), `BatchMode=yes` (no interactive prompts),
  a **dedicated key** referenced per config (v1: operator supplies the key path;
  per-session throwaway-key *generation* is a provisioner concern → Option B /
  future), `StrictHostKeyChecking` against an operator-managed `known_hosts`,
  and our own `ControlMaster`/`ControlPath` socket (cleaned in `stop()`).
- **No secret inheritance:** the remote command runs with a scrubbed env and
  `HOME` pointed at the workspace, same posture as the other backends.

## Sandbox ABC mapping

| ABC method       | SSH implementation |
|------------------|--------------------|
| `start()`        | open the ControlMaster (`ssh -M -o ControlPersist`), create the remote workspace dir, write the remote owner marker; idempotent |
| `exec()`         | `ssh <opts> <host> -- <remote timeout wrapper> bash -c <cmd>` in the workspace, streamed under the host-side deadline; policy fail-closed first |
| `workspace_for()`| return the remote path `~/.hugin-sandbox/<session>/agents/<agent>/<branch>`, `mkdir -p` it over the control socket |
| `put_file`/`get_file` | `scp` through the control socket, same workspace-confinement contract |
| `stop()`         | kill this session's remote jobs, remove the ControlMaster socket, best-effort GC the remote workspace |

## Config surface (proposed)

```yaml
options:
  bash:
    backend: ssh
    host: user@box.example.com   # or an ssh_config alias
    # optional:
    ssh_key: ~/.ssh/hugin_sandbox        # dedicated key; operator-supplied in v1
    remote_docker: true                  # run each command in `docker run …` on the box
    connect_timeout_s: 10
    server_alive_interval_s: 15
    network: true                        # remote boxes usually need egress; documented
    # cpu/memory/pids apply only when remote_docker: true
```

## What v1 ships vs. defers

**Ships:** Option A (BYO host); connect/exec/workspace/put/get/stop over
ssh/scp with the hardened option set + ControlMaster; remote `timeout`-wrapped,
killable jobs; host-side deadline so a partition can't hang the turn;
non-retryable `infra_error` on partition; best-effort remote-workspace GC at
`stop()` + a same-host startup sweep; optional `remote_docker` composition;
mocked tests + a documented manual containment gate against a real box.

**Defers (task 030-class / 024 seams):** Option B managed provisioning + VM
reaper by cloud id; per-session throwaway-key *generation*; the secret-injection
seam; the general remote-resource reaper; the exit-code-marker partition-recovery
nicety.

## Open question for sign-off

Confirm **Option A (BYO host) for v1**, with the provisioner seam left for a
future Option B — versus wanting managed ephemeral VMs now (Option B), which is a
substantially larger build (cloud API, billing-aware VM reaper, secrets). The
recommendation is A.
