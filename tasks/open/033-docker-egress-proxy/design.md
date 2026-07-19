# Docker egress-allowlist proxy — design note

**Status: SIGNED OFF (2026-07-19).** Decisions: **a small custom proxy** (resolve
the host, deny any answer in link-local/RFC1918/loopback, then the host
allowlist, for CONNECT + GET); **`network: true` re-means filtered egress**
(proxy + allowlist), lifting the PR-#68 fail-closed refusal when a proxy is
configured, with `allow_unrestricted_egress` the unfiltered escape hatch;
**per-session** proxy + internal network; **HTTP/HTTPS-only** egress (non-proxy
tools blocked); empty allowlist = deny-all. The real egress filter for
`backend: docker` +
`network: true`. Load-bearing decisions written and signed off before any code
(the backend / background-exec / escalation playbook). Source of truth: task 030
`network:true` item; the docker backend (`sandbox/docker.py`); the fail-closed
gating already shipped (PR #68).

## Goal & the constraint

`network: true` today attaches the default bridge with **unfiltered** egress —
an injected `curl http://169.254.169.254/...` reads cloud instance metadata and
exfiltrates IAM credentials. The gating interim refuses it unless
`allow_unrestricted_egress: true`. We want `network: true` to instead mean
**filtered egress**: block link-local/metadata (`169.254.0.0/16`) and RFC1918 by
default, permit an operator allowlist.

The container has `cap_drop=ALL`, so **in-container iptables is out**, and real
destination-IP filtering otherwise needs host root (mutating the daemon's
iptables — inappropriate for an unprivileged library) or a proxy. So the filter
must be **a proxy the container's egress is forced through**, at the network
layer.

## Architecture — internal network + a dual-homed proxy sidecar

Per session (or per distinct spec, keyed like the sandbox container):

1. **An `internal` docker network** (`docker network create --internal
   hugin-egress-<id>`). Containers on it can reach each other but have **no
   route to the outside**. The sandbox container joins **only** this network
   (`network_mode` = the internal network, replacing today's `"bridge"`), so it
   has **no direct egress** — a raw socket to `169.254.169.254` has nowhere to
   go.
2. **A forward-proxy sidecar container**, **dual-homed**: attached to the
   internal network (to receive the sandbox's traffic) *and* to the default
   bridge (to reach the internet). It runs an HTTP/HTTPS forward proxy
   configured with the operator allowlist.
3. **The sandbox is pointed at the proxy** — `HTTP_PROXY` / `HTTPS_PROXY` /
   `NO_PROXY` in the container env point at the proxy's internal-network IP.
   `curl`/`uv`/`pip`/`npm` honour these, so their traffic goes to the proxy,
   which resolves the hostname, checks the allowlist, and connects (or 403s).

**Why this is the real filter:** the sandbox's *only* path out is the proxy
(internal network = no other route), and the proxy enforces the allowlist for
what it forwards. Non-proxied traffic (raw sockets, a tool that ignores
`HTTP_PROXY`) has no route and simply fails — fail-closed. The metadata endpoint
is unreachable both ways: no direct route (internal net) and the proxy refuses
link-local/private destinations (below).

## The one load-bearing decision: the proxy (off-the-shelf vs custom) — SIGN-OFF

- **Option A — off-the-shelf (`tinyproxy`).** Tiny, battle-tested, has a
  `Filter`/`Allow` allowlist and upstream support. *Pro:* little code, proven.
  *Con:* config quirks; and its filter matches the *requested* host — to defend
  against **DNS rebinding** (an allowed hostname resolving to `169.254.169.254`
  or a private IP) and direct-IP requests, we must add IP-range denies on top
  (tinyproxy can deny by resolved address via `Filter` + `FilterDefaultDeny`,
  but private-IP-after-DNS blocking needs care / may need a resolver in front).
- **Option B — a small custom proxy** (~150 lines, Go or Python in the sidecar
  image). *Pro:* precise, auditable security policy in one place — allowlist by
  host **and** a hard deny of any destination that resolves to link-local /
  RFC1918 / loopback (DNS-rebinding-safe), for both `CONNECT` (HTTPS) and plain
  `GET`. *Con:* we own a network-facing proxy (attack surface, maintenance).

**Recommendation: Option B (small custom proxy).** The security-critical
requirement is the **private-IP / DNS-rebinding deny** — the host allowlist alone
is insufficient, because an attacker who controls an allowlisted domain can point
its DNS at `169.254.169.254`. tinyproxy filters on the *requested* host, **not
the resolved address**, so it *cannot* natively block that — it would need a
custom resolver in front. Squid *can* (`dst` ACLs on resolved IPs) but is a heavy
image + complex config. A ~150-line custom proxy resolves the host itself and
denies any answer in link-local/RFC1918/loopback before connecting — precise,
auditable, tiny image — which is exactly the mandatory control. So B is the
clean fit; the private-IP deny is non-negotiable and must be tested against a
hostname that resolves to `169.254.169.254`.

## Config surface

```yaml
options:
  bash:
    backend: docker
    network: true                       # now: FILTERED egress via the proxy
    egress_allowlist:                    # hosts/domains the proxy permits
      - pypi.org
      - files.pythonhosted.org
      - github.com
    # allow_unrestricted_egress: true    # the escape hatch: direct bridge,
    #                                      unfiltered (still warns) — unchanged
```

- **`network: true` now means filtered egress** (proxy + allowlist), so it is
  **no longer fail-closed** — the gating refusal (PR #68) is lifted *when a
  proxy is in place*. An **empty `egress_allowlist` blocks everything** (the
  proxy denies all) ≈ `network:false` but via the proxy; the operator opts hosts
  in explicitly.
- **`allow_unrestricted_egress: true`** stays the escape hatch: the old direct
  bridge, unfiltered, still warned. (So: none / filtered-allowlist /
  unrestricted-with-ack are the three egress postures.)
- **The allowlist is host/domain-based** (what the proxy sees), never IP-based
  for *allow* (IPs bypass DNS intent); the *deny* is IP-range-based (link-local/
  private) as the backstop.

## DNS

Proxied HTTP(S) needs no in-container DNS — the client sends the **hostname** to
the proxy (`GET http://host/…` or `CONNECT host:443`), and the **proxy** resolves
it (and applies the private-IP deny on the resolved address). So the sandbox
does not need external DNS at all for the supported path; the internal network's
embedded DNS (which may not forward externally) is a non-issue. **Documented
limitation:** only tools that honour `HTTP_PROXY` get egress; raw sockets and
non-proxy-aware tools are blocked (no route). This is HTTP/HTTPS egress, not
arbitrary network.

## Lifecycle & reaper

The proxy container + the internal network are **per-session resources** that
must not leak, exactly like the sandbox container:

- Labelled `hugin.session` / `hugin.owner_pid` / `hugin.created` / `hugin.ttl`
  (reuse the sandbox's label scheme) so the reaper reaps a dead owner's proxy +
  network.
- Created lazily in `start()` **only when `network: true` + a non-empty
  allowlist**; `stop()` removes the proxy container and the network (after the
  sandbox container). Ordering: sandbox first, then proxy, then network.
- The reaper (`reaper.py`) gains proxy-container + network cleanup alongside the
  sandbox container (overlaps the 024/030 reaper-generalization).

## Security properties (what must be tested)

- **Metadata unreachable:** `curl http://169.254.169.254/…` fails (no route +
  proxy deny). The headline gate.
- **DNS-rebinding-safe:** a hostname in the allowlist that resolves to a
  link-local/private IP is **denied by the proxy** (resolved-address deny). This
  is the subtle one — test it explicitly.
- **Non-allowlisted host:** `curl https://evil.example` → proxy 403.
- **Allowlisted host:** `curl https://<allowed>` succeeds.
- **No direct egress:** a raw socket / non-proxy tool cannot reach the internet
  (internal network). Fail-closed.
- **Default-deny:** empty allowlist ⇒ nothing gets out.

## What v1 ships vs. defers

**Ships:** the internal-network + proxy-sidecar wiring in `DockerSandbox`
(`network:true` → filtered); the proxy image (pinned, minimal) + its allowlist +
private-IP deny; `egress_allowlist` config; `HTTP_PROXY` injection; per-session
proxy/network lifecycle + reaper cleanup; tests (metadata blocked, DNS-rebinding
denied, allow/deny, default-deny) — daemon-gated, plus no-daemon unit tests of
the network/proxy wiring (`_container_kwargs`-style). Lifts the PR-#68 refusal
when a proxy is configured.

**Defers:** ssh-backend egress filtering (the ssh box's own concern —
`remote_docker` composition, task 030); non-HTTP egress (SOCKS / raw-socket
allowlisting); a shared (cross-session) proxy for density; per-request audit of
egress (the proxy's access log is the seam).

## Open questions for sign-off

1. **The proxy: tinyproxy (A) vs a small custom proxy (B).** Recommendation:
   tinyproxy if the private-IP/DNS-rebinding deny is expressible robustly, else a
   small custom proxy. The private-IP deny is mandatory either way.
2. **`network: true` re-meaning to "filtered egress"** (lifting the PR-#68
   fail-closed refusal when a proxy+allowlist is configured), with
   `allow_unrestricted_egress` remaining the unfiltered escape hatch — confirm.
3. **Per-session proxy** (isolation, 2 containers + a network per session) vs a
   shared proxy (density). Recommendation: per-session for isolation in v1.
4. **HTTP/HTTPS-only egress** (the honest limitation: non-proxy-aware tools are
   blocked) — acceptable for v1?
