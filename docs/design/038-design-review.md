# Task 038 design review

Date: 2026-09-28. Artifact: [self-forming private swarms](038-self-forming-swarms.md).
Baseline: task 038's historical shared-board plan, after tasks 036/039/040/041
merged. This is a design review, not evidence that a swarm implementation exists.

## Verdict

Approved as an implementation specification after revisions and independent
follow-up review. No unresolved P0/P1 design findings remain. All four judges
approved within their respective roles. Release still requires the protocol,
crash, security, deployment and scale tests specified in the artifact.

The owner confirmed private invite admission, tens to hundreds of machines,
LAN/private VPN connectivity, and AWS/Hetzner-style provisioning or many workers
on one large Linux host. The design implements those requirements with a
per-host daemon, local replicated boards and separately owned local runners.

## Panel and method

Four independent role-based reviewers read the full draft and returned
severity-ranked findings. The author synthesized overlaps, revised the design,
and sent the changes back for verification. A networking follow-up found an
additional drain failure, which was fixed and independently rechecked.

| Role | Review focus | Final assessment |
| --- | --- | --- |
| Distributed systems/networking | Group convergence, replication journal, churn, retention, scale-in | Approved after original findings and follow-up drain fix |
| Runtime/durability | Existing code seams, checkpoints, provider reservations, waits, restoration | No remaining P0/P1 blockers; retain implementation gates |
| Security | Invite/grant authority, origin binding, revocation, parser and execution boundaries | Approved; original findings resolved |
| Operability/product | Cloud bootstrap, Linux workers, renewal, drain, recovery and rollout | Approved; all five findings resolved |

No role recommended a central message server. The reviewers agreed that
reachable private networking makes bounded HTTPS replication a reasonable v1
choice, and that network delivery cannot imply exactly-once model/tool effects.

## Prioritized findings and disposition

No P0 finding was raised. P1 means a missing correctness/security/operational
contract that must be resolved before implementation; P2 means an important
clarification or completeness issue. Overlapping findings are consolidated
below at their highest reported severity.

| Severity | Finding and originating roles | Resolution in specification |
| --- | --- | --- |
| P1 | Invitation chain could be paired with a different public grant (security) | Root-signed issuer SPKI binding, validated chain/grant/envelope identity match |
| P1 | Expired policy prevented fetching its replacement (networking, operations; security P2) | Bounded policy-only recovery route without client certificate; pinned valid server chain, signed snapshot, no group access |
| P1 | Interior journal entries could expire without a reported history gap (networking) | Monotonic compaction watermark advances past any deletion; bounded resync with an upper sequence |
| P1 | Fresh-key autoscaling exhausted a permanent 512-node directory (networking) | Active slots expire separately from bounded evidence and replay metadata; replacement churn test |
| P1 | Write-only origins lacked a replication route (networking) | Own-record push to authorized readers, with no read permission escalation |
| P1 | Async dispatch acceptance could become an ordinary retry after restart (runtime) | Accepted/running/terminal/ambiguous operation ledger; unsupported executor tools disabled in durable mode |
| P1 | Late queued asks could start expensive work after their deadline (runtime; security P2) | Inbound deadline validation, admission and dispatch guards, explicit expiry without quota spending |
| P1 | Ordinary finite runs did not provide long-lived advertised workers (runtime) | Explicit resident mode, availability state table, interruptible wakeup and hourly-budget recovery |
| P1 | Coherent interaction history did not restore arbitrary application state (runtime) | Versioned app resumability contract, unsupported-state rejection and required artifact durability |
| P1 | Cloud termination could discard unfinished work or unreplicated records (operations) | Machine-readable drain, fenced admission and explicit incomplete/loss handling |
| P1 | Drain could delete the last copy using old acknowledgments (networking follow-up) | All retained records need fresh confirmations from non-draining peers after a persistent fence |
| P2 | Reply-before-ask ordering could be mistaken for permanent invalidity (networking) | Bounded durable dependency staging/fetch; no execution before full validation |
| P2 | Relay traffic and catch-up limits were ambiguous (networking) | Signed-author first-insert accounting separate from relay byte/request limits and fair catch-up scheduling |
| P2 | A retried reservation could change identity across checkpoints (runtime) | Stable session, origin generation and operation ID; ordered durable reservation handshake |
| P2 | Resident workers could emit duplicate/premature router outcomes (runtime) | Disable finite-session outcome hook in resident mode; preserve correlation headers |
| P2 | Opening wording overstated prompt-injection protection (security) | Separate direct protocol authority from model use of locally granted tools |
| P2 | Initialization/readiness and budget examples were not automatable (operations) | Idempotent join, exit codes, explicit first node, readiness contract and budget configuration |
| P2 | Ambiguity had no operator resolution interface (operations) | Redacted machine-readable operation ledger and audited reconcile/abandon/retry choices |
| P2 | Qualification omitted boot storms and rolling upgrades (operations) | Simultaneous joins, version mismatch, migration/rollback, renewal and scale-in gates |

## Synthesis and remaining trade-offs

The old plan's first-k reader claims cannot enforce a strict partition-safe
responder cap without coordination. The replacement freezes recipients at the
asker before publishing. This is compatible with decentralization because each
ask has an owner; there is no swarm-wide leader. A timeout returns partial
results instead of silently recruiting extra responders.

Full replication within subscribed groups is intentionally retained for v1.
It is simple to recover but costs storage and bandwidth proportional to group
membership. Bounded connections do not imply bounded total replication cost;
100/300-host qualification must measure it before release.

The offline-root model has an operational cost: periodic policy signing and
private grant renewal. Seven-day authorization freshness and 30-day grants
are explicit starting defaults, not immediate revocation or permanent
membership after a short invite window. They can be shortened with a matching
operator renewal process. No reviewer conflict remains on these trade-offs.

Deduplicated agent admission requires a new coherent checkpoint backend.
Existing file saves and in-memory budgets are insufficient. This adds an
implementation increment, but removes an otherwise false recovery guarantee.
Existing ordinary `bash` uses an in-memory background executor; it is not
eligible for durable mode until its operation lifecycle is supported. Applications
with arbitrary mutable environment objects also need a declared restore contract.

Post does not automatically start all subscriber models in v1. Explicit asks
and locally scheduled reads provide controlled execution. Provider invocation
allowances are durable per host/session; neither selected recipient count nor
these counters are an exact currency or whole-swarm spending guarantee.

## Validation of this documentation change

- Audited current registration, inbox serialization, storage write ordering,
  scheduler wait classification, model budget boundaries and monitor seams.
- Checked primary references for certificate validation, Ed25519, canonical
  JSON, SQLite WAL, journal-style replication and NAT traversal. Links are in
  the specification beside the relevant design rationale.
- Verified internal document links, frontmatter/state consistency, preservation
  of historical task prose, clean whitespace and changed-file pre-commit checks.
- Repository suite and all-file check results are recorded in the design PR.
  No new runtime tests are claimed for documentation; future release tests are
  explicitly labeled as requirements in the specification.

No runtime behavior, dependencies or deployed services change in this PR.
Task 038 stays ongoing for the implementation sequence.
