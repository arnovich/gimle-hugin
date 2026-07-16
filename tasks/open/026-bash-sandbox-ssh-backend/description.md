---
title: Bash sandbox — SSH / remote (VPS) backend (Phase 2)
state: OPEN
labels: [enhancement, security, sandbox]
priority: medium
---

# Bash sandbox — SSH / remote (VPS) backend (Phase 2)

Add the `ssh` execution backend: the boundary is a **disposable remote machine**
(a throwaway VPS the operator doesn't mind the agent breaking). A peer to the
`docker` backend (task 025), not a footnote — for many users a throwaway box is
the most natural isolation story. Selectable with `backend: ssh`. No Docker
dependency; shell out to `ssh`/`scp` (no `paramiko` dependency).

**Design source of truth:** task 023 `spec.md` §1 (SSHSandbox), `plan.md`
Phase 2/3 note, `review.md` "SSH / VPS" section. Phase 1's `create_sandbox`
raises `NotImplementedError("phase 2")` for ssh today.

## Prerequisite (write BEFORE building)

The plan is explicit: the **secrets / provisioning / ownership / cost story must
be written up first, not during the code.** Deliver a short design note
(`design.md` in this task folder) covering:

- **Provisioning** — who creates the box, when, from what image; is it per-session
  ephemeral or a reused pool; how is it torn down (and who pays if teardown fails).
- **Secrets** — the agent will need scoped credentials to do real work; where do
  they come from, how are they injected, revoked, and rotated (there is no
  secret-injection seam in Phase 1 — see task 024). Never ship long-lived creds
  to a box the agent controls.
- **Cost / ownership** — a leaked VM bills money; the reaper must reap remote
  resources by ID + TTL/heartbeat, not host PID (Phase 1 reaper is local-only).
- **Idempotency** — a remote command interrupted by a network partition is NOT
  safe to blindly retry; how is a mid-command partition handled.

## Tasks

- [ ] Write and get sign-off on the design note above.
- [ ] `sandbox/ssh.py` — `SSHSandbox(Sandbox)`, shelling out to `ssh`/`scp`.
  - Dedicated **throwaway key per session**; `-o ForwardAgent=no -o
    BatchMode=yes -o ConnectTimeout=... -o ServerAliveInterval=...` (a network
    partition must not hang the client while the remote command runs on).
  - Run the remote command under `systemd-run --scope` / `timeout` / a named
    tmux so Hugin can kill the **remote** job, not just the local client.
  - Own the `ControlMaster` socket path; clean it in `stop()`.
  - Prefer targeting a **hardened container on the remote** (`ssh host docker
    run …`) over the bare host.
  - `put_file`/`get_file` via `scp` with the same workspace confinement contract.
- [ ] Extend the reaper for remote resources (by session/owner + TTL/heartbeat) —
      shared with the docker reaper generalization in task 024/025.
- [ ] `Session.close()`/`SandboxManager.close()` closes the SSH connection,
      kills the remote job, and (if this backend provisioned the box) tears it
      down; reaper is the backstop.
- [ ] Tests: connection/command-kill mocked where a real host isn't available;
      the containment gate (below) run against a real disposable box in CI or a
      documented manual gate.

## Success criteria

- [ ] The same config runs unchanged with `backend: ssh` on a disposable remote.
- [ ] `python3 -c 'os.system("id")'` is contained by the remote machine, provably.
- [ ] A mid-command network partition does not hang Hugin and does not silently
      double-execute; the remote job is killable.
- [ ] No leaked remote VM / connection / key on clean OR abrupt exit.
- [ ] The secrets/provisioning/cost design note exists and was reviewed.
