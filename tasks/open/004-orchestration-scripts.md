---
github_issue: 4
title: Define portable local and cloud agent-run orchestration
state: OPEN
labels: [enhancement, design]
priority: medium
author: arnovich
created: 2026-01-28
audited: 2026-08-12
---

# Define portable local and cloud agent-run orchestration

## Audit (2026-08-12)

Still relevant as a product capability, but not implementation-ready. The repo
has CI/release workflows and sandbox Docker assets; it does not have a
production run specification, GCP/AWS launchers, or cloud-storage adapter. The
old "similar to mimir" reference is context, not an acceptance criterion.

## Design first

Define one backend-neutral run contract covering:

- agent/config/task inputs, model credentials, storage location, resource
  limits, timeout, and network policy;
- a stable run ID plus idempotent submit/resume/cancel/status operations;
- structured status, logs, artifacts, and terminal outcome;
- least-privilege secret delivery and cleanup;
- the storage capabilities required by remote workers (do not assume a local
  filesystem API maps directly to object storage).

Then implement the smallest vertical slice twice: a local Linux runner and one
chosen cloud target (GCP or AWS). The second cloud should reuse the contract,
not force a second orchestration model. GitHub Actions should dispatch that same
interface rather than contain provider-specific run logic.

## Success criteria

- The same checked-in run spec works locally and on the first cloud target.
- Duplicate submission is safe, interrupted runs have an explicit resume
  policy, and status/logs remain available after the worker exits.
- Credentials are not written to task output, logs, or persistent workspaces.
- Provider setup, IAM, teardown, and cost-bearing resources are documented.
