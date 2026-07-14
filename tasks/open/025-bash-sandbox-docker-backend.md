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

## Tasks

- [ ] `sandbox/docker.py` — `DockerSandbox(Sandbox)`. **Lazy `docker`-SDK import
      inside the module** so a user who never selects docker needs neither the
      library nor a daemon. One long-lived container per session; `docker exec`
      per command (or a persistent shell — see task 027 statefulness).
- [ ] All hardening flags are **mandatory** when this backend is chosen:
  - `--network=none` unless `network: true`
  - `--cap-drop=ALL`, `--security-opt=no-new-privileges:true`
  - `--read-only` root, `--tmpfs /tmp:rw,noexec,nosuid,size=256m`
  - `--cpus` / `--memory` / `--pids-limit` from spec; `--ulimit nproc/nofile`
  - `--init` (PID 1 reaps double-forked children — the case the local backend
    can't handle)
  - default seccomp + apparmor kept; **never** `--privileged`, never
    `seccomp=unconfined`
  - userns-remap so container-root ≠ host-root
  - `HOME=/workspace/...`, empty env by default (no inherited secrets)
  - workspace = a **named/bind volume keyed by session-id** so a resumed session
    reattaches its filesystem instead of getting an empty one
  - labels `hugin.session` / `hugin.owner_pid` / `hugin.created` / `hugin.ttl` +
    a heartbeat file touched each step (so the reaper can find/kill it)
  - **no docker socket mount, ever**
- [ ] `network: true` egress control — block link-local/metadata
      (`169.254.0.0/16`) and RFC1918 by default, ideally via an egress-allowlist
      proxy. Otherwise an injected `curl http://169.254.169.254/...` exfiltrates
      cloud IAM credentials. (`network:false` — the default — is the safe path;
      this item is only for when an operator opts into network.)
- [ ] `docker/sandbox.Dockerfile` — **thick and boring** image (a thin image is a
      false economy — every missing binary is a wasted agent turn): Debian slim +
      `bash coreutils findutils git curl ca-certificates ripgrep jq less` +
      `python3` + `uv` + `node`. Pinned by digest, scanned (Trivy/Grype), signed
      (cosign), verified on pull. **No Hugin source, no credentials** — the
      sandbox is dumb; stack/interactions/artifacts stay host-side.
- [ ] Extend the reaper (`sandbox/reaper.py`) so it reaps abandoned **containers**
      (by `hugin.owner_pid` label + heartbeat/TTL), not just local dirs — the
      Phase 1 reaper is local-dir + host-PID only (see task 024). Container
      liveness is not a host `os.kill`.
- [ ] `docker` SDK → optional `sandbox` extra in `pyproject.toml`
      (`docker>=7.1`); `create_sandbox` gives a clear remediation error if
      `backend: docker` is selected but the extra isn't installed.
- [ ] Ensure `Session.close()`/`SandboxManager.close()` actually stop+remove the
      container (Phase 1 `stop()` is a no-op for local; here it releases a real
      resource — wire it so a clean exit doesn't leak a container, and confirm
      the reaper is the backstop for abrupt exits).
- [ ] Tests (`slow` marker, skipped without a daemon): assert every hardening
      flag is actually set on the created container, and assert the **containment
      gate** above. Plus: resumed session reattaches its volume; container is
      removed on `close()`; reaper removes an abandoned container.

## Success criteria

- [ ] The same config runs unchanged with `backend: docker` — contained, no
      network by default.
- [ ] `python3 -c 'os.system("id")'` is provably contained by the container.
- [ ] Package still installs and `local`/`ssh` still run without the `docker` SDK.
- [ ] No container or volume leaks on clean OR abrupt exit.
- [ ] `/panel-review` (security judge's containment test is the gate) before merge.
