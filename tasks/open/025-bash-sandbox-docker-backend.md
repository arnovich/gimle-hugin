---
title: Bash sandbox — Docker backend (Phase 2)
state: OPEN
labels: [enhancement, security, sandbox]
priority: high
---

# Bash sandbox — Docker backend (Phase 2)

Add the `docker` execution backend for the bash tool: a real container
isolation boundary, selectable per-config with `backend: docker`. This is one of
the two isolation backends that make the bash tool safe for untrusted work;
`local` (shipped in Phase 1) has no boundary and says so. `docker` and `ssh` are
**peers** — no Docker dependency for the package to install or for `local`/`ssh`
to run.

**Design source of truth:** task 023 `spec.md` §1 (DockerSandbox), §2 (workspace),
§6 (lifecycle), §10 (deps); `plan.md` Phase 2; `review.md` (both panels). Phase 1
built the `Sandbox` ABC, `SandboxSpec` (with `image`/`network`/`cpu`/`memory`/
`pids` fields already defined), `create_sandbox` factory (raises
`NotImplementedError("phase 2")` for docker today), `SandboxManager`, reaper, and
audit — this task fills in `create_sandbox`'s docker branch.

## The acceptance gate (non-negotiable)

The security judge's containment test IS the definition of done: `python3 -c
'os.system("id")'` must be **contained by the runtime** (the container),
*provably*, not merely denied — and the docs must never claim the policy
allowlist stopped it. A denylist by design allows interpreter execution; the
container is what makes that safe.

## Status

**Shipped** (branch `bash_sandbox_docker_backend`): the backend, the reaper
extension, the optional extra, teardown, the Dockerfile, and the containment
gate — hardened after a four-judge panel review. Two mandatory-flag items are
intentionally *approximated* and their full form is deferred to task 030
(follow-ups): true **userns-remap** (we run as the host non-root uid and refuse
root-without-userns instead) and **`network:true` egress filtering** (the
default `network:false` is safe; opt-in warns loudly, filtering is deferred).
Image **digest-pinning/scan/sign** is likewise deferred (the Dockerfile is
honest that it's for local iteration). Everything else below is done.

## Tasks

- [x] `sandbox/docker.py` — `DockerSandbox(Sandbox)`. **Lazy `docker`-SDK import
      inside the module** so a user who never selects docker needs neither the
      library nor a daemon. One long-lived container per session; `docker exec`
      per command (or a persistent shell — see task 027 statefulness).
- [x] All hardening flags are **mandatory** when this backend is chosen
      *(with the userns-remap caveat above — see task 030)*:
  - `--network=none` unless `network: true`
  - `--cap-drop=ALL`, `--security-opt=no-new-privileges:true`
  - `--read-only` root, `--tmpfs /tmp:rw,noexec,nosuid,size=256m`
  - `--cpus` / `--memory` / `--pids-limit` from spec; `--ulimit nproc/nofile`
  - `--init` (PID 1 reaps double-forked children — the case the local backend
    can't handle)
  - default seccomp + apparmor kept; **never** `--privileged`, never
    `seccomp=unconfined`
  - ~~userns-remap so container-root ≠ host-root~~ *(approximated: runs as the
    host non-root uid; refuses root-without-userns. True remap → task 030)*
  - `HOME=/workspace/...`, empty env by default (no inherited secrets)
  - workspace = a **bind volume keyed by session-id** so a resumed session
    reattaches its filesystem instead of getting an empty one
  - labels `hugin.session` / `hugin.owner_pid` / `hugin.owner_start` /
    `hugin.created` / `hugin.ttl` (the dead heartbeat file was dropped; liveness
    is the owner PID + start-time token, and a dead-owner container is recreated
    on resume so its labels refresh)
  - **no docker socket mount, ever**
  - *(added in review)* `/dev/shm` noexec,nosuid tmpfs; `memswap_limit` pinned
- [ ] `network: true` egress control — block link-local/metadata
      (`169.254.0.0/16`) and RFC1918 by default, ideally via an egress-allowlist
      proxy. **Deferred to task 030** — `network:false` (the default) is safe and
      is the only tested path; `network:true` warns loudly for now.
- [x] `docker/sandbox.Dockerfile` — **thick and boring** image (Debian slim +
      `bash coreutils findutils git curl ca-certificates ripgrep jq less` +
      `python3` + `uv` + `node`; **No Hugin source, no credentials**). Digest
      pinning / scan (Trivy/Grype) / sign (cosign) / verify-on-pull → task 030.
- [x] Extend the reaper (`sandbox/reaper.py`) so it reaps abandoned **containers**
      (by `hugin.owner_pid` label + start-time/TTL), not just local dirs.
      Daemon-optional; short client timeout. (Cross-host/root scoping → task 030.)
- [x] `docker` SDK → optional `sandbox` extra in `pyproject.toml`
      (`docker>=7.1`); a clear remediation error if `backend: docker` is selected
      but the extra isn't installed (surfaced at `start()`).
- [x] `Session.close()`/`SandboxManager.close()` actually stop+remove the
      container; the reaper is the backstop for abrupt exits.
- [x] Tests (`slow` marker, skipped without a daemon): every hardening flag is
      asserted on the created container, the **containment gate** is proven, a
      resumed session reattaches its volume, the container is removed on
      `close()`, and a dead-owner container is recreated on resume. Plus a
      daemon-free hardening-contract layer that pins every flag.

## Success criteria

- [x] The same config runs unchanged with `backend: docker` — contained, no
      network by default.
- [x] `python3 -c 'os.system("id")'` is provably contained by the container
      (runs, but host FS unreachable, non-root uid, no network).
- [x] Package still installs and `local`/`ssh` still run without the `docker` SDK.
- [x] No container or volume leaks on clean OR abrupt exit.
- [x] `/panel-review` (security judge's containment test is the gate) — done;
      load-bearing findings fixed, the rest tracked in task 030.
