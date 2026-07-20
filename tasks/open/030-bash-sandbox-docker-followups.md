---
title: Bash sandbox — Docker & SSH backend follow-ups (deferred panel findings)
state: OPEN
labels: [enhancement, security, sandbox, tech-debt]
priority: high
---

# Bash sandbox — Docker & SSH backend follow-ups

Deferred items from the four-judge panel reviews (security / architecture / SRE /
agent-usability) of the Docker backend (task 025) and the SSH backend (task
026). The Docker section is first; the **SSH backend follow-ups** are in their
own section near the end. Where the two overlap (reaper generalization, DRY
extraction across backends, env affordance, spill path), do the work once in
whichever backend is touched first.

## Docker backend

Deferred items from the panel review of the Docker backend (task 025, PR that
added `sandbox/docker.py`). The load-bearing findings were fixed before that PR
merged
— the narrow-`except` escape, the no-host-deadline hang, resume recreating on a
dead owner, fail-fast on a missing image, the 137/OOM mislabel, the root-without-
userns guard, `/dev/shm`/swap hardening, and the `network:true` warning. The
items below are genuine phase-2 design work or lower-severity polish, tracked
here so they aren't lost. Several overlap task 024 (reaper generalization,
observability, `put_file`/`get_file`, env affordance) — do them once, in whichever
task is picked up first.

## Security (do before recommending `docker` for untrusted input at scale)

- [x] **`network: true` egress control — INTERIM DONE (2026-07-16).**
  *(security, HIGH — effectively CRITICAL on a cloud host)* `network:true`
  attaches the default bridge with unrestricted egress; an injected `curl
  http://169.254.169.254/...` exfiltrates cloud IAM credentials. Since the
  container has `cap_drop=ALL` (in-container iptables is out) and real
  destination-IP filtering needs host root or an allowlist proxy — neither fits
  an unprivileged library — `network:true` is now **fail-closed**: it is
  *refused* at `start()` unless `allow_unrestricted_egress: true` explicitly
  accepts the risk (and even then it warns). The default `network:false` (no
  network) is untouched. This converts the silent foot-gun into an explicit,
  informed choice. **Still deferred (the real filter):** an egress-allowlist
  proxy that blocks link-local/metadata (`169.254.0.0/16`) + RFC1918 while
  permitting an allowed set — a whole subsystem (filter at the network/proxy
  layer). A lightweight interim for operators who need filtered egress today:
  run your own HTTP(S) proxy allowlist and pass it into the command env.
- [ ] **True userns-remap.** *(security, HIGH)* The backend runs the container as
  the host uid (non-root *inside* the container) and refuses root-without-userns,
  but it does not itself remap container-root to a subuid — that is a daemon-level
  setting. Document the daemon `userns-remap` requirement prominently and,
  where detectable via `client.info()` SecurityOptions, prefer/require it.
- [ ] **Image supply chain.** *(security, MEDIUM)* `DEFAULT_IMAGE` is a mutable
  `:latest` tag and `containers.run` does no verification; the Dockerfile's
  `FROM` is a tag and it pipes an unpinned `curl | sh` uv installer as root.
  Default to a digest, verify digest/signature on pull (cosign), pin `FROM` by
  digest, replace `curl|sh` with a checksum-verified artifact, and add a
  Trivy/Grype scan + cosign sign step to the image build/publish pipeline.
- [ ] **Workspace disk quota.** *(security, MEDIUM)* cpu/memory/pids are capped
  but the bind-mounted `/workspace` is unquota'd host storage; `yes > f` (not on
  the denylist) fills the host disk and takes down the orchestrator. Mount the
  workspace on a size-limited volume or enforce a quota / `fsize` ulimit (chosen
  generously so legit builds aren't broken).
- [ ] **`put_file`/`get_file` TOCTOU / `O_NOFOLLOW`.** *(security, MEDIUM,
  latent — no production caller yet)* `_confine` realpath-checks then does a
  plain `open`; because the container writes the same tree as the host uid, a
  symlink swap between check and open escapes. Open with `O_NOFOLLOW` /
  `openat2(RESOLVE_NO_SYMLINKS)` walking from a dirfd. Overlaps task 024's
  `put_file`/`get_file` item.

## Architecture / ops

- [~] **Reaper generalization + scoping.** *(architect/SRE, MEDIUM)* **Scoping
  done:** containers/networks are now labelled with `hugin.host` + `hugin.boot`,
  and the reaper only judges an owner PID against the process table it belongs
  to — a *different host*'s container (shared daemon) is never reaped here (its
  own host owns it), and a *prior boot*'s container is abandoned outright (PIDs
  recycle across reboots). Older unlabelled containers fall through to the
  pre-scoping PID/TTL judgment. `boot_id()`/`current_hostname()` in `local.py`.
  **Still open:** the *generalization* — `reap_abandoned_containers` is still a
  bespoke free function; give the backend registry a reap seam so the CLI
  iterates backends (SSH will add a third). Cross-host reaping of a genuinely
  dead host's containers stays out of scope (documented). Overlaps task 024.
- [ ] **Capped / backgrounded exec: explicit state + kill.** *(SRE/architect/
  usability, MEDIUM)* On the output cap or a host-side abandonment the exec'd
  process keeps running in-container until its `timeout` fires, and the next
  command runs as a second concurrent exec competing for pids/cpu. `exit_code`
  is `-1` and `is_error` is `False`, so a capped runaway reads as success. Add an
  explicit `output_capped`/`abandoned` field to `ExecResult` (treat as
  `is_error`) and proactively terminate the lingering exec before returning.
- [ ] **`start()` atomicity.** *(architect/SRE, MEDIUM)* Assign `self._container`
  immediately after `containers.run` and wrap the post-create steps so a failure
  after create stops the container instead of orphaning a live one the manager
  never learned about.
- [ ] **Observability.** *(SRE, MEDIUM)* Differentiate `sandbox_start_failures`
  by exception class (daemon-down vs image-missing vs create-rejected); add
  `sandbox_containers_reaped`, start/pull duration, and a live labelled-container
  gauge to `hugin sandbox`. Overlaps task 024's observability item.
- [ ] **Custom-image `timeout`/`bash` contract.** *(SRE/architect, LOW)* The exec
  wrapper assumes coreutils `timeout` and `bash` on `PATH`; a minimal/distroless
  custom `image:` breaks cryptically. Preflight-probe on `start()` for non-default
  images, or document the contract.
- [ ] **DRY.** *(architect, LOW)* `_write_owner_stamp` is copied from `local.py`
  and the container stop/remove appears in both `docker.py` and `reaper.py`.
  Extract shared `write_owner_stamp(root)` / `remove_container(container)` helpers
  and move the `LABEL_*` constants into a small shared module (also breaks the
  `reaper → docker` import).

## Agent usability

- [ ] **Environment affordance in the tool description.** *(usability, HIGH)*
  The model isn't told its OS, its installed toolset (ripgrep/jq/python3/uv/node),
  or — critically — that `network:false` means `curl`/`uv`/`npm` cannot reach the
  internet, so it discovers by trial and error. Render an "Installed: … / NETWORK
  IS OFF" line from the resolved `Policy`/`SandboxSpec` so it can't drift.
  Overlaps task 024's env-affordance item.
- [ ] **Spill path is cwd-relative.** *(usability, MEDIUM)* On truncation the
  response returns `.hugin/last_output.txt` relative to the command cwd; after a
  `cwd`-scoped call the follow-up (run at the workspace root) can't find it.
  Spill to a stable workspace-root path (`/workspace/.hugin/last_output.txt`, per
  spec §2) and report that. Overlaps task 024's spill item.
- [ ] **Timeout hint.** *(usability, LOW)* A timeout returns `timed_out: true` +
  `exit_code: 124` but no in-band pointer at the `timeout_s` argument; add a hint.
- [ ] **Statefulness / persistent shell.** *(usability)* Cross-ref task 027: each
  `exec` is a fresh shell, so `cd`/`export`/`source` don't persist between calls
  (a single call can still chain `cd foo && cmd`). The description states this;
  the persistent-shell-in-a-disposable-container design lives in task 027.

## SSH backend

Deferred items from the four-judge panel review of the SSH backend (task 026, PR
that added `sandbox/ssh.py`). The load-bearing findings were fixed before that PR
merged — the sentinel-based partition/exit disambiguation (a real transport drop
vs. a command that itself exits 255 vs. a backgrounded child holding the pipe),
the TTL-sweep heartbeat so a live >24h session isn't reaped, `workspace_for`
path-traversal sanitization, `get_file` raising instead of silently truncating,
the provisioner seam, a 0700 ControlMaster dir, and the backend-generic
infra-error note. The items below are genuine phase-2 work or lower-severity
polish.

### Security / hardening

- [ ] **`remote_docker` composition (defence in depth).** *(security, HIGH for
  scale)* v1's bare disposable host *is* the boundary; a command that breaks out
  of the workspace owns the box. Implement the design note's `remote_docker:
  true` — run each command in a hardened `docker run …` *on* the remote (reusing
  the docker backend's flag set), so the box is the outer boundary and the
  container the inner. Until then, document loudly that the host must be
  genuinely disposable.
- [ ] **`known_hosts` posture.** *(security, MEDIUM)* v1 uses
  `StrictHostKeyChecking=accept-new` (TOFU) — a first-connection MITM is
  undetected. Offer an operator opt-in to a managed `known_hosts` +
  `StrictHostKeyChecking=yes`, documented as the hardened path.
- [ ] **Secret-injection seam.** *(security, MEDIUM)* Overlaps task 024. v1 ships
  no credentials to the box (network-limited work). When the secret seam lands,
  keep the contract: never place long-lived credentials on a box the agent
  controls; scope + short-TTL only.

### Architecture / ops

- [ ] **Reaper generalization (remote dead-owner).** *(architect/SRE, MEDIUM)*
  v1 reaps stale remote workspaces by an mtime TTL sweep at `start()` on the same
  host; there is no proper dead-owner remote reaper (the local reaper can't SSH
  out). Fold into the backend-registry reap seam (see the Docker reaper item) so
  a remote sweep by owner-marker + TTL is a first-class, scheduled operation, not
  only a start-time side effect. Also generalize the owner-marker consumer so the
  docker/ssh/local stamps are read by one code path.
- [ ] **DRY across backends.** *(architect, LOW)* `_run`'s capped/deadline drain
  loop, the owner-marker construction, and the exec-result finalization overlap
  the docker backend. Extract shared helpers (a drain-under-cap+deadline util, a
  `write_owner_marker`, an `ExecResult` finalizer) once both backends are stable.
- [ ] **`stop()` process-group kill.** *(SRE, MEDIUM)* `stop()`'s `pkill -f
  <root>` matches the wrapper, not a backgrounded child that reparented away; the
  real bound today is the remote `timeout`. Run the wrapper under `setsid` and
  kill the process group so the whole tree dies on teardown.
- [ ] **Scale control-plane deadlines to transfer size.** *(SRE, LOW)*
  `_CONTROL_DEADLINE_S` is fixed; a large `put_file`/`get_file` over a slow link
  can hit it. Scale the deadline by payload size (and cross-ref the `get_file`
  cap — chunked transfer for large files).
- [ ] **Config nesting / per-backend validation.** *(architect, LOW)* `network`
  is accepted but ignored by ssh (cpu/memory/pids only bind under
  `remote_docker`); validate/warn on options that don't apply to the chosen
  backend at config-load time.

### Agent usability

- [ ] **Environment affordance + PATH.** *(usability, HIGH)* Overlaps task 024 /
  the Docker env-affordance item. The remote wrapper pins a narrow
  `PATH=/usr/local/bin:/usr/bin:/bin` and the model isn't told the remote OS or
  toolset; render an "Installed: … / remote host" line from the resolved spec,
  and consider a capability probe at `start()` so the narrow PATH doesn't hide
  installed tools.
- [ ] **Spill path is cwd-relative.** *(usability, MEDIUM)* Same issue as the
  Docker backend — the spill writes `.hugin/last_output.txt` under the command
  cwd, so a follow-up at the workspace root can't find it. Spill to a stable
  workspace-root path and report that. Do once, shared with the Docker item.
- [ ] **Early-return on a backgrounded child.** *(usability/SRE, LOW)* A `cmd &`
  that keeps the stdout pipe open makes `_run` wait to the host deadline even
  though the sentinel proves completion. Detect the sentinel in-stream and stop
  reading early to cut that latency (correctness is already right — this is
  purely a latency win).

## Notes

- Panel transcripts and the synthesis live in the PR discussion / session notes.
- `demux=True` cleanly separates stdout/stderr but loses their relative
  interleaving order — acceptable, noted for anyone debugging interleaved logs.
