# Panel review outcomes — docker egress proxy (task 033)

A three-judge panel (security engineer, framework/docker architect, SRE/ops)
reviewed the implementation. **Consensus: the security boundary is
fundamentally sound** — single-resolution + connect-to-the-checked-IP is
genuinely DNS-rebinding-safe, `cap_drop=ALL` removes the raw-socket/ICMP
channels, the internal network gives no direct route out, and the gating +
empty-allowlist + identity-hash logic all hold. No Critical findings. The
material findings below were **fixed in this PR**; the rest are **deferred** with
rationale.

## Fixed in this PR

- **Embedded-IPv4 SSRF (security, the one real bypass).** `ip.is_global` alone
  does not unwrap IPv4-mapped `::ffff:169.254.169.254` (denied only on
  CVE-2024-4032-patched stdlib) or NAT64 `64:ff9b::a9fe:a9fe` (`is_global` True
  on *every* stdlib) — an allowlisted domain serving those AAAA records reaches
  the metadata endpoint. Now `safe_global_addresses` unwraps both forms and
  judges the *embedded* IPv4 (connecting over clean IPv4). No longer depends on
  the stdlib patch level. Tests: `TestEmbeddedIpv4Deny`.
- **`stop()` teardown could raise (wedge hazard).** `_remove_proxy_and_network`
  ran for every docker sandbox and its proxy lookup caught only `NotFound`, so a
  flaky daemon could raise from `stop()` and permanently wedge the agent stack.
  Now: early-return when not egress-filtered, and every step guarded. Tests:
  `TestTeardownSafety`.
- **`start()` leaked infra on partial failure.** A throw after the network/proxy
  were created left them orphaned. Now `start()` tears down what it created on
  any failure before re-raising (via the never-raising teardown).
- **`_wait_for_proxy` real readiness + raise-on-timeout.** Was `status==running`
  + a fixed 0.3 s sleep, and returned *success* on timeout. Now probes the
  proxy's listener from inside the container (cross-platform) and raises on a
  crash or the deadline.
- **Network subnet-pool exhaustion** now surfaces with an actionable remediation
  message (`hugin sandbox prune` / widen `default-address-pools` / lower
  concurrency) instead of the SDK's raw 500.
- **Proxy hardening pinned daemon-free.** Extracted `_proxy_kwargs()` (like
  `_container_kwargs`) so a regression dropping a hardening flag on the proxy is
  caught without a daemon. Tests: `TestProxyHardeningContract`. Added a CPU cap
  (`nano_cpus`), raised `pids_limit` to 128, and an `on-failure` restart policy.
- **Proxy request-parse hardening.** Socket timeout on the parse phase +
  header count/byte caps (slowloris self-DoS), a defensive port parser
  (`"²".isdigit()` no longer crashes a handler thread), and a failed
  bridge-connect now removes the half-created proxy instead of leaving a
  silently-egress-less one. Allowlist parsing strips leading dots too.
- **DNS-exfil residual channel documented** (see below) — the module docstring
  no longer over-claims "whatever this proxy refuses is unreachable".

## Deferred (with rationale) — follow-ups

- **DNS exfiltration (security H2).** The sandbox still reaches docker's embedded
  resolver (it must, to resolve the proxy's container name), which forwards
  external queries via the daemon — so `<base32-secret>.attacker.example` can
  exfiltrate low-bandwidth data over DNS without touching the proxy. It cannot
  reach the metadata endpoint that way (exfil-only). Documented in
  `egress_proxy.py`. Closing it (static proxy host via `extra_hosts` + a
  constrained resolver) is a follow-up. *This backend is HTTP/HTTPS egress
  control, not a full network jail.*
- **Open relay on the shared bridge (security M1).** The proxy is dual-homed on
  the default `bridge` and binds `0.0.0.0`, so a co-located container could use
  it as a forward proxy to the allowlisted hosts. Effectively moot: any
  container on the bridge already has full unfiltered egress, so the proxy grants
  it nothing it can't already do (and it still can't reach private IPs). Tighten
  by binding the listener to the internal-interface IP if this ever matters.
- **Pin the sandbox base image by digest (security M2).** Now defense-in-depth
  only (the embedded-IPv4 fix no longer relies on the stdlib CVE patch), but
  still good hygiene — `docker/sandbox.Dockerfile` is `FROM debian:bookworm-slim`
  unpinned.
- **Adopted-network stale labels on resume (arch M4 / SRE M3).** A network reused
  after a crashed owner keeps the dead PID's labels; the reaper then judges it
  abandoned every invocation and is stopped only by the "still attached"
  refusal. Not a correctness bug (the live network is never actually removed) —
  just a wasted reap attempt per invocation on a rare partial-failure path. The
  startup reaper deletes the stale network before `start()` in the common path.
- **Reaper startup latency (SRE M4).** `reap_abandoned_containers` +
  `reap_abandoned_networks` build a client each; on a *wedged* daemon that is
  ~5 s + ~5 s. Bounded by the 5 s client timeout; share one client to halve it.
- **Operability (SRE M5).** `hugin sandbox list` shows only workspaces, not the
  proxy containers / egress networks; the subcommand help text still says "local
  sandbox workspaces". `prune` already reaps them. Extend `list` (+ `--json`).
- **Plain-HTTP niceties (security L3 / arch L7).** Verbatim `Host` forwarding
  (vhost confusion on a shared/CDN allowlist entry — not an egress bypass) and
  keep-alive to a second host reusing the first upstream (fails closed). Force
  `Connection: close` if we want strictness.
- **Bind-mount of `egress_proxy.__file__` (arch L8).** Requires the file on the
  *daemon* host, so a remote `DOCKER_HOST` breaks the proxy. Same assumption as
  the workspace bind; bake the script into the image to remove it.
