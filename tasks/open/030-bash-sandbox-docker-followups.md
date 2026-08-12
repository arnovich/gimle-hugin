---
title: Bash sandbox — remaining cross-backend hardening
state: OPEN
labels: [enhancement, security, sandbox, tech-debt]
priority: high
audited: 2026-08-12
---

# Bash sandbox — remaining cross-backend hardening

This is the consolidated backlog for Docker/SSH panel findings and the few
unshipped items from closed task 024. It is not a claim that the current default
is unsafe: `network: false` remains the default, and task 033/PR #70 shipped the
filtered egress proxy for allowlisted `network: true` runs. Explicit
`allow_unrestricted_egress` remains exactly that—an operator acceptance of
unfiltered egress.

## Shipped baseline

- [x] Filtered Docker egress with metadata/private-address and DNS-rebinding
  protection (task 033 / PR #70).
- [x] Per-file size cap across backends (PR #79); total workspace quota remains
  open.
- [x] Final-component `O_NOFOLLOW` for local/Docker file transfer (PR #80);
  intermediate-directory races remain open.
- [x] Host/boot-scoped Docker reaping (PR #78); the CLI seam is still bespoke.
- [x] Atomic Docker start rollback and explicit `output_capped` results (PR
  #80).
- [x] Per-agent file confinement, stable spill paths, environment note,
  close-time audit counters, and create-run-finish `Session.close()` wiring
  (PRs #72–#77; closed task 024).

## High-priority containment for untrusted workloads at scale

- [ ] **Docker user namespaces.** Document and detect daemon `userns-remap`;
  provide a require/fail-closed option where the daemon exposes its security
  settings. Running as the host UID inside the container is not userns remap.
- [ ] **Image supply chain.** Pin the default image/base and installers by
  digest/checksum; add image scanning and a signed publish/verification path.
- [ ] **Total workspace quota.** Bound aggregate workspace use, not only each
  file. Choose a portable fallback for hosts without project/volume quotas.
- [ ] **Full path-walk confinement.** Protect intermediate path components for
  file transfer (for example Linux `openat2` from a trusted dirfd), with a
  documented fallback on unsupported platforms.
- [ ] **SSH defence in depth.** Design `remote_docker` composition for scaled
  untrusted use. Until it exists, keep the contract explicit: the remote host
  itself must be genuinely disposable.
- [ ] **Hardened SSH identity.** Support operator-managed `known_hosts` with
  `StrictHostKeyChecking=yes`; retain TOFU only as an explicit convenience mode.

## Lifecycle, secrets, and operations

- [ ] Add a backend lifecycle/reap interface so `hugin sandbox` iterates the
  backend registry instead of calling local/Docker free functions. Include
  remote TTL/heartbeat cleanup and observable resource handles.
- [ ] Add a short-lived, least-privilege secret-provisioning seam. Never persist
  long-lived credentials in agent-controlled workspaces or audit output.
- [ ] Extend observability with categorized start failures, reaped-resource
  counts, start/pull duration, and live resource counts.
- [ ] Kill a Docker exec immediately when its output cap is reached; do not rely
  only on the in-container timeout.
- [ ] Run SSH commands in a process group and kill the full tree on teardown;
  scale file-transfer deadlines by payload size.
- [ ] Account for and reap idle per-agent/branch workspace and spill subtrees,
  rather than retaining all of them for the full session.
- [ ] Close sessions returned to long-running app orchestrators when those apps
  first adopt bash; the current create-run-finish entry points are covered.

## Contract and usability polish

- [ ] Preflight or clearly document the `bash` + coreutils `timeout` contract
  for custom Docker images.
- [ ] Validate/warn about backend-inapplicable options (for example SSH options
  that only take effect under future `remote_docker`).
- [ ] Add an optional remote capability/PATH probe without making the prompt's
  policy description depend on mutable discovery.
- [ ] Add an in-band hint for `timeout_s` on timeout and a generic marker when
  older context-window interactions were elided.
- [ ] Document the boundary: bash for exploration/mechanical work; structured
  tools when Hugin must type, validate, observe, or persist the result.
- [ ] Extract shared owner-marker, drain/finalize, and resource-removal helpers
  only where doing so reduces real Docker/SSH duplication.

## Sequencing and closure

Split implementation into focused PRs. The first slice should be chosen from the
high-priority containment section based on the intended deployment target; the
lower sections need not block ordinary local/default-network use. Close this
umbrella when every item is shipped, explicitly declined with rationale, or
moved to a focused task with an owner and acceptance criteria.

Related but separate: multi-tool-call support (006), the harness blend (029),
and persistent shells (032).
