---
title: Docker egress-allowlist proxy — the real network:true filter
state: OPEN
labels: [enhancement, sandbox, security, docker, networking]
priority: high
---

# Docker egress-allowlist proxy

The real filter behind `backend: docker` + `network: true`. The gating interim
(PR #68, task 030) made `network: true` **fail-closed** — refused unless
`allow_unrestricted_egress: true` explicitly accepts unfiltered egress — because
the container's `cap_drop=ALL` rules out in-container iptables and real
destination filtering needs host root or a proxy. This task builds that proxy so
`network: true` can mean **filtered egress** (an operator allowlist; link-local/
metadata + RFC1918 blocked) instead of all-or-nothing.

**Design source of truth:** `design.md` in this folder (the load-bearing
decisions, to be signed off before code), task 030's `network: true` item, and
the docker backend (`src/gimle/hugin/sandbox/docker.py`).

See `design.md` for the architecture (an `internal` docker network + a
dual-homed forward-proxy sidecar), the config surface, DNS, lifecycle, and the
open questions for sign-off.
