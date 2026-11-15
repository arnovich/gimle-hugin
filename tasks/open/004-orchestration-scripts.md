---
github_issue: 4
title: Define portable local and cloud agent-run orchestration
state: open
labels:
- enhancement
- design
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
## Context

Prepare reusable Hugin and native coding-agent runtime adapters around accepted Taskvalet Tasks044 and045. Taskvalet retains claims, memory, selection and canonical host lifecycle; Hugin owns its session. The owner explicitly chose Task048 SSH/Hetzner first in the console on 2026-11-15. This supersedes the legacy GCP/AWS first-provider choice while preserving real local/remote qualification before full task acceptance. The legacy Audit/Design-first text is historical context; this Context, proposed Outcome and reviewed planning note define the updated planning scope. Planning/review only: no implementation, deployment, provisioning or experiment authorized.
## Outcome

- [ ] AC1: Runtime integration reuses Task044 and Task045, with a reusable Taskvalet-owned dispatcher resolving existing native journals/claims and starting the guardian before members. Evidence: Ownership ADR and dispatcher/broker integration tests; no new scheduler/claim store, fresh identities on resume, direct task-file writes or real dispatch through --rehearsal
- [ ] AC2: One named/version-pinned Hugin runtime and one named/version-pinned coding runtime pass a full model/tool/result loop through the same guarded contract. Evidence: Actual runtime entry points with synthetic provider transcripts and the exact qualified isolation profile; driver stubs and unverified profile changes cannot satisfy this criterion
- [ ] AC3: Runtime/profile/input/preset/skill/transport pins are bound to the immutable canonical run ID and actual installed bytes are verified before admission. Evidence: Wrong binary/adapter/preset/profile/wire bytes cause zero process/model dispatch; changed runtime under same ID refused; old wire compatibility explicit
- [ ] AC4: Sole admitted model route and verified pre-dispatch cost bounds cover every model invocation. Evidence: Exact chosen runtime/profile's kernel negative-egress and fake-provider traces; changed gateway/profile blocked until verified; unknown/insufficient contracts cause zero dispatch; auxiliary calls cannot bypass the meter
- [ ] AC5: Credentials, authority and bindings remain scoped per concrete member; children/restores do not inherit authority implicitly. Evidence: Cross-agent/session and injection tests; no real keys in config, logs, output or checkpoints
- [ ] AC6: Prepare/status/resume/cancel preserve original state and reconcile unknown effects conservatively. Evidence: Process-exit/lost-response tests; same IDs, counters, deadlines and exposure; corrupt state fails closed
- [ ] AC7: Owned-resource stop and cleanup remain independent of the controller and preserve unrelated work. Evidence: Deadline/descendant/failure tests, guardian receipt, unsupported cleanup explicitly incomplete
- [ ] AC8: The installed mixed-runtime fixture carries evidence, attribution and selected work across teams without altering the owner queue. Evidence: Complete deterministic handoff/review/selection trace with separate actors and checked-receipt references
- [ ] AC9: Status, logs, artifacts and terminal results remain inspectable after runtime exit under explicit storage capabilities. Evidence: Installed-package/read-after-exit and retention tests; sanitized bounded diagnostics
- [ ] AC10: The support matrix and rollout plan accurately distinguish supported adapters, synthetic evidence, design-only profile changes and live NO-GO gates. Evidence: Reviewed matrix, pinned package manifests, compatibility, rollback and required CI; unsupported transports never labelled supported
- [ ] AC11: The first remote target uses an agreed Task048 SSH/Hetzner runtime/profile contract and binds one logical execution to one host/incarnation and authoritative ledger. Evidence: Recorded D1 choice, shared profile/lease/cleanup/artifact contract, duplicate/uncertain dispatch and second-host fallback-denial tests; Lean-only profiles do not count as agent-hosting support
- [ ] AC12: Full Task004 acceptance includes real local/remote qualification for the selected runtime/profile, or an explicit owner scope amendment. Evidence: Separately authorized and verified evidence, which may be supplied by Task048 only if it covers the same adapter/profile; no inference from fake-remote conformance
