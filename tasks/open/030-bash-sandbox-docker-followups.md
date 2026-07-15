---
title: Bash sandbox — Docker backend follow-ups (deferred panel findings)
state: OPEN
labels: [enhancement, security, sandbox, tech-debt]
priority: high
---

# Bash sandbox — Docker backend follow-ups

Deferred items from the four-judge panel review (security / architecture / SRE /
agent-usability) of the Docker backend (task 025, PR that added
`sandbox/docker.py`). The load-bearing findings were fixed before that PR merged
— the narrow-`except` escape, the no-host-deadline hang, resume recreating on a
dead owner, fail-fast on a missing image, the 137/OOM mislabel, the root-without-
userns guard, `/dev/shm`/swap hardening, and the `network:true` warning. The
items below are genuine phase-2 design work or lower-severity polish, tracked
here so they aren't lost. Several overlap task 024 (reaper generalization,
observability, `put_file`/`get_file`, env affordance) — do them once, in whichever
task is picked up first.

## Security (do before recommending `docker` for untrusted input at scale)

- [ ] **`network: true` egress control.** *(security, HIGH — effectively
  CRITICAL on a cloud host)* Today `network:true` attaches the default bridge
  with unrestricted egress; an injected `curl http://169.254.169.254/...`
  exfiltrates cloud IAM credentials. The code warns loudly and the default
  (`network:false`) is safe, but the opt-in path needs real filtering: block
  link-local/metadata (`169.254.0.0/16`) and RFC1918 by default, ideally via an
  egress-allowlist proxy (the container has `cap_drop=ALL`, so in-container
  iptables is out — filter at the network/proxy layer). Until then, consider
  refusing `network:true` unless an explicit allow-flag is set.
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

- [ ] **Reaper generalization + scoping.** *(architect/SRE, MEDIUM)* Backend
  reap logic (`reap_abandoned_containers`) is a bespoke free function in
  `reaper.py`; SSH will add a third. Give the backend registry a reap seam so the
  CLI iterates it. Also the container sweep is daemon-global: it lists *every*
  `hugin.session` container and judges the owner PID against the *local* process
  table — wrong for a remote/shared daemon, and it can reap another
  `--storage-path`'s containers. Label the container with a host/boot-id and its
  workspace-root and filter on both; document the local-daemon assumption.
  Overlaps task 024's reaper-generalization item.
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

## Notes

- Panel transcripts and the synthesis live in the PR discussion / session notes.
- `demux=True` cleanly separates stdout/stderr but loses their relative
  interleaving order — acceptable, noted for anyone debugging interleaved logs.
