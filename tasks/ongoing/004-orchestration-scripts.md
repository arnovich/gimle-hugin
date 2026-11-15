---
github_issue: 4
title: Define portable local and cloud agent-run orchestration
state: ongoing
labels:
- enhancement
- design
priority: medium
author: arnovich
created: 2026-01-28
audited: 2026-08-12
claimed_by: agent/0570841b-092f-43c1-906c-07267cdf2b32
claimed_at: '2026-11-15T21:29:56.436110+00:00'
branch: task/004_orchestration_scripts_d9efe5900a
console_approvals:
  a9fbeef86a47de9122af06f7:
    request_id: 1de76922-8291-40cb-8a32-fdeccc6db27d
    operation: claim
    task: 004-orchestration-scripts
    executed_by: agent/0570841b-092f-43c1-906c-07267cdf2b32
    source: Console
    verification: agent_relay
    approval: 'Owner explicitly instructed: claim Hugin Task004 and start M1: audit
      runtime capabilities, select the first coding-agent runtime, and identify relay
      or isolation gaps. Keep it offline; do not deploy or launch another experiment.
      This claim is for the M1 audit only, not runtime implementation, provider execution
      or provisioning.'
    previous_claim: null
    expires_at: '2026-11-15T21:39:54.798236Z'
    observed_revision: f1b3d0ce7bd19d81c00cfef41def5d4d7e1aa0db36adb18ddbd47a6d6486d36d:81822768341d566451e625176dbebbb1e8fe87c3
    question_id: null
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

## Conversation

### note · agent/0570841b-092f-43c1-906c-07267cdf2b32 · 2026-11-15T21:24:56Z

Reviewed planning proposal; all three independent plan reviewers cleared the revisions. Owner authorization covers publication only, keeping Task004 New, unclaimed and unqueued. The SSH/Hetzner choice is the owner's explicit console decision. No implementation or operational qualification is claimed.

#### Hugin Task004: reusable bounded runtime integration

Status: reviewed offline plan, authorized for Taskvalet publication but not for
implementation. Initial API reads returned HTTP 530; the final bounded recheck
succeeded and confirmed Task004 is New and unclaimed. The owner then explicitly
authorized a Hugin-project planning writer and API publication while preserving
New, unclaimed and unqueued state. Only that registration/publication is allowed;
no implementation, deployment, provisioning, runtime or model execution is
authorized. No local task-file write is a substitute for the API.

#### Goal and retained scope

Make Hugin and a supported coding-agent runtime usable members of the same
Taskvalet-coordinated workflow through reusable, installed adapters. Reuse the
existing agents; do not invent another agent engine, task board, scheduler,
selection system or claim store. Taskvalet owns assignments, shared memory,
questions, evidence, selection and acceptance. Hugin owns its session/stack;
the coding runtime owns its own execution state.

Task044 provides guarded MemberTools, Hugin/coding tool bridges and installed
presets/skills. Task045 provides immutable RunSpec, canonical HostRuns, persistent
reservations, Linux isolation, relay/broker channels and independent cleanup.
Those are foundations, not proof that arbitrary native model transports already
work inside the bounded profile. The current synthetic driver manually steps
tool adapters; it does not exercise a full Hugin AskOracle/response loop or a
third-party coding-agent model loop.

The older Task004 asks for local Linux plus GCP or AWS execution. Decision D1 was
resolved by the owner in this console on 2026-11-15: reuse Task048 SSH/Hetzner
first. This supersedes the old first-provider choice; GCP/AWS is not a requirement
for the first delivery. No separate Hugin cloud lifecycle is introduced. This
choice does not authorize implementation, deployment, provisioning or paid calls.
Full portable local/remote execution still needs evidence for the selected
runtime/profile, not merely fake-remote conformance. An offline milestone does
not silently finish that remaining qualification requirement.

#### Ownership and boundaries

| Component | Owner and reuse |
| --- | --- |
| Claims, findings, independent reviews, selection, questions | Existing Taskvalet participation/research APIs and Task044 guards |
| Run identity, policy, deadlines, counters, reservations and process cleanup | Task045 HostRuns/RunSpec and Linux supervisor; extend explicitly if necessary |
| Hugin session, configuration, tool binding and model-result decoding | Hugin runtime adapter and existing bind_taskvalet_tools integration |
| Coding-agent runtime/tool transport | One named, version-pinned native coding runtime adapter using the same MemberTools contract and swarm skill |
| Reusable runtime dispatcher and relay protocol extension | New, explicitly scoped Taskvalet companion work consuming Task045; not a Hugin-owned scheduler or reopening Finished Task045 |
| Model request/usage transport | A versioned adapter to the host-controlled relay; synthetic responses for offline qualification only |
| Capacity/enrollment and pool lifecycle | Reuse Tasks037/039/046 and the Task047 API; no takeover of its current worker |
| Remote provisioning and independent remote cleanup | Task048 backend boundary; no new provider-specific scheduler in Hugin |
| Product chat, accounts and public launch UX | Later Tasks049/051; outside this work |

Hugin's separate proposed self-forming peer-swarm design is not an authorization
or shared-memory authority for this workflow. Peer messages and retrieved content
cannot grant claims, change budgets, dispatch new members or impersonate users.
Hugin Task042 is merged but was still in Review on the last successful live read;
its acceptance is a separate owner action, not silently performed by this plan.

Task048 currently describes Lean-pool backends, not generic agent hosting. Before
remote adapter implementation, agree a versioned shared backend/profile contract
covering runtime kind, installed artifact/profile digests, dispatch identity and
assigned host/incarnation, authoritative ledger location, lease/deadline
authority, status/log/artifact retrieval, stop/cleanup and retention. A Lean-worker
enrollment key is not a research participant identity or permission to run Hugin.
If Task048 provides only Lean profiles, remote agent support remains gated until
that scope/interface is explicitly extended; Task004 must not repurpose compute
enrollment as agent hosting.

#### Implementation sequence proposed for later authorization

#### M1: qualify interfaces before writing a launcher

Record pinned source/package versions and choose one concrete coding runtime.
Inspect its documented/local configuration and transport capabilities without
running an agent or contacting a provider. Produce a support matrix for complete
tool schemas, structured errors, model routing, usage/unknown outcomes, process
stop, checkpointing, children/branches and secret persistence.
Include built-in tools, plugins/MCP servers, helper model calls, telemetry and
automatic fallback/update paths in that audit. The swarm skill is guidance; the
host/broker guards, sandbox and relay enforce authority. Participation-only use
of a coding agent does not imply support for the managed, shared-budget profile.

The first coding adapter must name its actual binary/SDK and version before its
implementation begins. An in-process bridge or hand-written imitation is not
qualification of a native coding agent. If no candidate can enforce the route
and limits, report a design blocker instead of declaring a stub supported.

Task045 members currently permit AF_UNIX only. A CLI requiring ordinary HTTP/TCP
does not automatically fit that profile. Prefer a compatible local transport; if
it needs a gateway or different network profile, document a versioned, separately
reviewed design and its kernel verification requirements. Do not widen the
existing profile silently or substitute personal CLI login credentials.
Before an adapter is labelled supported or satisfies AC2/AC4, its actual runtime
and exact profile must pass the full fake-provider loop and kernel-level negative
egress tests, including out-of-manifest IPC. A changed gateway/network profile
remains design-only/blocked until that evidence exists. Historical Task045
AF_UNIX checks do not qualify a changed profile. This is a future acceptance gate,
not permission to execute a profile test during the present planning work.

#### M2: define the smallest versioned runtime binding

Extend Task045's contract where needed, rather than duplicate run state. Pin the
adapter/profile digest, installed runtime, agent config/task input hashes,
preset/skill, authorized tool surface, working-storage policy and provider
contract. The operator's allowlisted registry resolves entry points; model output
never supplies an executable, credential path, provider URL or cloud account.

Keep native credentials and journals in the host broker. The member receives
only scoped local capabilities. Provider/cloud credentials remain outside both
agent runtimes. Restored Hugin sessions require explicit per-agent rebinding;
cloned configs and task-specific tool lists must preserve the exact allowed
schemas. Child creation is disabled unless children are separately declared and
admitted with their own identities and a share of the original run limits.

The companion Taskvalet dispatcher must resolve an existing canonical run ID and
its journal references against the operator's registry, reconcile the exact
existing actors/claims and prepared compute bindings, and bind MemberTools in
the private broker. It must not create fresh identities/claims when starting or
resuming. Verify actual installed binary, adapter, preset/skill, profile and wire
implementation bytes against their pins before admission or any process start;
version strings alone are insufficient. Installed artifacts must remain protected
against member writes between verification and execution.

Before effects, record exact unit/job intents; start the independent guardian
before relay/member work, then use LinuxHost and the selected native adapter.
HostRuns.submit currently admits accounting only. Keep that behavior explicit;
the new dispatcher is a separate reviewed entry point, not a covert launcher
added to --rehearsal. Offline conformance may use only prepared local API fixtures
and synthetic provider capabilities; it must reject real origins, credentials
and provider routes. Live admission remains disabled until its separate approval,
price-bound, readiness and cleanup prerequisites are implemented and verified.

Actual Hugin prompts, conversation history, tools and tool results exceed the
current relay's synthetic prompt-only shape. Specify a closed, bounded message
envelope and request/result codecs before implementing them. Account for the
whole request, tool schemas, referenced inputs, tool-call IDs, bounded outputs,
usage and unknown outcomes. Any RunSpec/wire change needs an explicit version or
compatible extension, canonical digest tests and rejection of unsupported forms.
Do not claim existing live-model pricing support: only the fixed synthetic cost
contract is presently admitted.

#### M3: implement actual runtime adapters with fake provider responses

Run Hugin through its real Session/AskOracle/OracleResponse/tool-result path with
deterministic synthetic provider replies. For the selected coding runtime, use
its actual engine/driver and real tool-service integration against that same
offline provider contract. A temporary provider credential must be a fixture
capability, not a personal subscription or real API key. Disable external egress.

Both adapters use the same guarded MemberTools semantics and published skill/
preset. Domain tools are explicitly host-approved and bounded. Hugin's session
call limit is an additional guard, not a monetary cap; all branches, children,
failed calls, retries and auxiliary model calls must traverse the shared relay
and its reservation-before-dispatch ledger.

Interchangeability is configuration at prepare time. Changing runtime/config
under an existing immutable run ID is refused. A deliberate later runtime change
requires a separately reviewed run while preserving the previous journals,
evidence, reservations and attempt history; there is no implicit identity takeover
or hot-swap that resets the old lifetime.

#### M4: persist observable outcomes and recover conservatively

Keep Taskvalet journals, host ledger and agent checkpoints distinct. Use versioned
checkpoint descriptors with artifact digests and bounded private logs; do not
serialize provider bindings or secret-bearing runtime configuration. A runtime
without trustworthy checkpoint support advertises inspection/cancel recovery,
not fabricated continuation. Uncertain dispatch is reconciled without repeating
paid/model/tool effects or resetting original deadlines.

Status distinguishes proposed, prepared, admitted, running, waiting, stopping,
terminal, uncertain and cleanup-incomplete states where the underlying host can
prove them. Views do not launch. Cancellation seals dispatch, stops owned work,
retains the independent guardian until its receipt and cancels only exact owned
jobs through an admitted backend. Unsupported or unconfirmed remote cleanup
remains incomplete; never infer process death from a stale heartbeat.

#### M5: one complete offline conformance gate

Use deterministic fake-provider transcripts and isolated Taskvalet API fixtures.
Exercise a complete member loop and a mixed-team handoff: candidate checked by
the fake checker, publication with original authorship, peer reuse, separate
review, selection and only the chosen follow-up becoming eligible. Use separate
fixture actors; do not copy a proof receipt to manufacture another author's work.
Scripted judgments verify transport, not mathematical truth or model quality.

Include lost replies, repeated requests, controller/runtime exit, corrupted or
missing checkpoints, uncertain usage, wrong actor/claim, schema rejection,
attempts to bypass the relay, malicious findings, revoked tools, bounded disk/
output, original deadlines, child processes and cleanup failure. Resume must
reopen the same canonical state. Recovered bindings must not cross agent/session
identities. Compare Hugin and coding outcomes through the common protocol, not
identical prose. Retain attributed immutable receipts and counts.

#### M6: review packaging and remote readiness, without activation

Build and install pinned Hugin/Taskvalet wheels in disposable environments; test
their actual optional-dependency boundary and installed runtime entry points.
Keep Hugin usable without Taskvalet. Validate preset/skill and adapter digests,
configuration rejection, source manifests and credential-free diagnostics.
Perform lifecycle, budget/security and operations review before opening a PR.

Design the first SSH/Hetzner remote mapping through Task048 using the same run/policy and artifact
contracts. Inject a fake remote transport for contract tests; do not provision,
install on Causa, start remote services or submit cloud/model jobs. Document
provider/IAM/secret delivery, storage capabilities, leases, infrastructure budget,
deletion recovery and rollback. Hugin filesystem operations are not an object
storage API: preserve capabilities explicitly rather than translating paths to
arbitrary bucket URLs.

Task045's canonical state is host-scoped. Before remote dispatch, the shared
admission authority must durably bind the logical run and dispatch request to one
executing host/runner incarnation, profile digest and authoritative ledger.
Backend retries reuse that recorded placement/request; the authoritative budget
and original deadlines are not recreated on remote storage. An uncertain remote
reply means hold/fence and inspect the same attempt, never fallback to a fresh
local or second-host ledger. No automatic failover or live session migration is
in scope. Cross-target conformance comparisons use separate deliberate execution
IDs and budgets under the same versioned application/policy template; portability
does not mean re-admitting one live run twice. If the shared backend cannot prove
single admission and exact stop/cleanup ownership, remote support remains blocked.

#### Proposed acceptance criteria and evidence

These are proposed task text, not recorded checks or implementation results.

| ID | Criterion | Required evidence |
| --- | --- | --- |
| AC1 | Runtime integration reuses Task044 and Task045, with a reusable Taskvalet-owned dispatcher resolving existing native journals/claims and starting the guardian before members | Ownership ADR and dispatcher/broker integration tests; no new scheduler/claim store, fresh identities on resume, direct task-file writes or real dispatch through --rehearsal |
| AC2 | One named/version-pinned Hugin runtime and one named/version-pinned coding runtime pass a full model/tool/result loop through the same guarded contract | Actual runtime entry points with synthetic provider transcripts and the exact qualified isolation profile; driver stubs and unverified profile changes cannot satisfy this criterion |
| AC3 | Runtime/profile/input/preset/skill/transport pins are bound to the immutable canonical run ID and actual installed bytes are verified before admission | Wrong binary/adapter/preset/profile/wire bytes cause zero process/model dispatch; changed runtime under same ID refused; old wire compatibility explicit |
| AC4 | Sole admitted model route and verified pre-dispatch cost bounds cover every model invocation | Exact chosen runtime/profile's kernel negative-egress and fake-provider traces; changed gateway/profile blocked until verified; unknown/insufficient contracts cause zero dispatch; auxiliary calls cannot bypass the meter |
| AC5 | Credentials, authority and bindings remain scoped per concrete member; children/restores do not inherit authority implicitly | Cross-agent/session and injection tests; no real keys in config, logs, output or checkpoints |
| AC6 | Prepare/status/resume/cancel preserve original state and reconcile unknown effects conservatively | Process-exit/lost-response tests; same IDs, counters, deadlines and exposure; corrupt state fails closed |
| AC7 | Owned-resource stop and cleanup remain independent of the controller and preserve unrelated work | Deadline/descendant/failure tests, guardian receipt, unsupported cleanup explicitly incomplete |
| AC8 | The installed mixed-runtime fixture carries evidence, attribution and selected work across teams without altering the owner queue | Complete deterministic handoff/review/selection trace with separate actors and checked-receipt references |
| AC9 | Status, logs, artifacts and terminal results remain inspectable after runtime exit under explicit storage capabilities | Installed-package/read-after-exit and retention tests; sanitized bounded diagnostics |
| AC10 | The support matrix and rollout plan accurately distinguish supported adapters, synthetic evidence, design-only profile changes and live NO-GO gates | Reviewed matrix, pinned package manifests, compatibility, rollback and required CI; unsupported transports never labelled supported |
| AC11 | The first remote target uses an agreed Task048 SSH/Hetzner runtime/profile contract and binds one logical execution to one host/incarnation and authoritative ledger | Recorded D1 choice, shared profile/lease/cleanup/artifact contract, duplicate/uncertain dispatch and second-host fallback-denial tests; Lean-only profiles do not count as agent-hosting support |
| AC12 | Full Task004 acceptance includes real local/remote qualification for the selected runtime/profile, or an explicit owner scope amendment | Separately authorized and verified evidence, which may be supplied by Task048 only if it covers the same adapter/profile; no inference from fake-remote conformance |

An offline implementation milestone can pass AC1-10 without live provider/cloud
calls. AC11-12 implement the selected shared backend ownership and preserve the
remaining real local/remote qualification requirement. Do not close the whole
task based only on fake remote conformance. Keep monetary and
infrastructure budgets separate; call counts and timeouts are not dollar caps.

#### Publication and authorization gates

Current authorization is preparation and review only. No implementation, live
provider selection, spending, provisioning, deployment, campaign or experiment.
No test run is claimed by this document. Future offline implementation requires
a deliberately scoped instruction and the M1 capability decision.

When Taskvalet returns, reread the authoritative Task004 body, claimant, owner
queue, questions and diagnostics. Record the owner's D1 choice faithfully when
updating the old cloud criterion. Use a proper Hugin-project registered run for all API writes; preserve
existing identities and do not take Task042 or Task047 from their workers.
Publish Context/Outcome/Plan through the API only. Cross-project Task044/045/048
references belong in Context/plan; the task API's dependency field is same-project.
Do not revive the legacy AGENTS.md direct-Git task/queue recipes or set next.
This draft neither changes the task nor claims current implementation readiness.

#### Source basis

- Hugin main `cef8b1a6b8ca38ca6d7721daa4a695f4c392cd47`: native tool binding,
  Session budgets, actual oracle/tool flow and legacy Task004 design-first scope.
- Taskvalet accepted Task044 (PR34) and Task045 (PR39, merge
  `522b928eba053e3860e12bc342897547dcf8a459`, correction `efa1eff…`): MemberTools,
  CodingAgentBridge, presets/skills, HostRuns, fixed synthetic relay and cleanup.
- Last successful live reads: Task046 Finished; Task047 independently claimed;
  Task048 New/dependent on Task047; Hugin Task042 merged/Review; Task004 New and
  unclaimed. These must be refreshed before any task write or claim.

### note · agent/0570841b-092f-43c1-906c-07267cdf2b32 · 2026-11-15T21:29:56Z

Owner approval relayed by agent (Console). Operation claim; request 1de76922-8291-40cb-8a32-fdeccc6db27d; previous claimant none.

Owner explicitly instructed: claim Hugin Task004 and start M1: audit runtime capabilities, select the first coding-agent runtime, and identify relay or isolation gaps. Keep it offline; do not deploy or launch another experiment. This claim is for the M1 audit only, not runtime implementation, provider execution or provisioning.

### note · agent/0570841b-092f-43c1-906c-07267cdf2b32 · 2026-11-15T21:40:41Z

#### Task004 M1: native runtime capability audit

Audit date: 2026-11-15. Scope: offline source inspection and installed CLI
metadata. No agent session, fake-provider conversation, provider request,
deployment or experiment was run. Task004 is Ongoing under its existing planning
writer. M1 does not qualify a runtime or complete Task004.

#### Decision

Select **Codex CLI 0.166.0-alpha.5.1** as the first coding-runtime implementation
candidate. Its installed help exposes noninteractive execution, JSONL events,
explicit model/config selection, resume, no-daemon mode, strict config and
user-config/rules controls. These are useful adapter surfaces, not evidence of
sole model egress or complete tool mediation. This is an alpha build: an upgrade
requires a new pin and repeat qualification, never an implicit replacement.

Keep Claude Code 2.1.314 as a second candidate. Its help exposes print/stream-json,
explicit tools/MCP settings, bare/restricted modes, session IDs and a native
dollar limit. Those controls are promising; the native dollar limit cannot replace
the shared Taskvalet meter. No comparative quality or performance claim is made.
Codex is selected to keep the first implementation narrow, not because this audit
has established that Claude cannot work.

The Hugin candidate is source commit
`cef8b1a6b8ca38ca6d7721daa4a695f4c392cd47`. It is not yet a built, installed,
dependency-pinned runtime artifact. The Taskvalet contract reference is accepted
main `522b928eba053e3860e12bc342897547dcf8a459`; the inspected Task045 worktree
is `efa1effff1a7cec71c7040093c759763b6c21790`. The relevant Task045 sources
must remain identical when constructing the implementation package.

#### Evidence and its limits

The adjacent [Codex metadata](task004-evidence/codex-metadata.json) and
[Claude metadata](task004-evidence/claude-metadata.json) contain executable paths,
SHA256 values and captured help/version outputs. Every recorded probe exited 0.
They ran inside a macOS child sandbox denying network, file writes and access to
the specific personal paths listed in each recorded sandbox policy. No complete
credential-location inventory or filesystem read trace was collected. An earlier attempt to create that child
sandbox from the desktop sandbox failed before either executable started; the
successful probes used an approved outer command to install the stricter child
sandbox. Codex warned that it could not create PATH aliases; this did not prevent
metadata inspection. These controls are probe containment, not Linux qualification.

| Artifact | Observed version/platform | SHA256 |
| --- | --- | --- |
| Codex executable | 0.166.0-alpha.5.1, packaged aarch64-apple-darwin | `58a91f6ea19bea477ae3a2ec48d619f0039afe75d3476260747e11d201fa7cea` |
| Claude executable | 2.1.314, installed macOS executable | `21d6e7b9a6f07b4cfcb7df13760b3b72aa25e084e13a5354413382987ba832ed` |

No Linux executable was downloaded, installed or hashed. Neither Mac hash can
qualify Causa. No credential contents were requested or captured. Installed help is
evidence that an interface is advertised, not that its full runtime behavior has
passed a test. Provider routing configuration, event schemas, usage completeness,
signal behavior and checkpoint contents remain unverified for the selected CLI.

#### Capability matrix

| Concern | Hugin source evidence | Codex installed help evidence | Required closure |
| --- | --- | --- | --- |
| Native loop | Session / AskOracle / OracleResponse / ToolCall / ToolResult | `exec`, `--json`, `exec resume` | Execute actual engines with deterministic provider transcripts; do not substitute a Python driver |
| Tool schemas | Taskvalet integration forwards complete provider schemas; model wrappers use input_schema | MCP management advertised; final `--output-schema` is a final-answer schema | Pin broker tool schemas and error envelopes; prove call/result identity, rejection and replay through the engine |
| Model route | OpenAI SDK chat completions and Anthropic SDK messages; Ollama is another route | model/config overrides; OSS/local providers advertised | Determine and pin native model wire protocol; reject all unadmitted routes, fallbacks and unsupported options |
| Accounting | Session call budget includes children/branches, not money; SDK usage read after responses | JSONL advertised; no verified shared spend contract | Reserve before every provider attempt including retries, compaction and auxiliary calls; settle conservatively on uncertain outcome |
| Stop / recovery | Session persistence exists separately from Taskvalet canonical host lifetime | resume/fork/ephemeral advertised | Exact session-to-run mapping, no counter/deadline reset, independent guardian and descendant cleanup; signal tests still needed |
| Secrets / config | SDK clients constructed from ambient config; provider errors can log message content | `--ignore-user-config` explicitly still uses auth; plugin/hooks/search/daemon/cloud surfaces exist | Launcher-owned restricted configuration and sanitized environment; no personal auth mounts; deny unapproved hooks/plugins/MCP/IPC |
| Isolation | In-process Taskvalet binding does not sandbox arbitrary Hugin tools | CLI sandbox is advertised for model-generated shell commands | External kernel confinement must cover the entire process tree and every model/tool route |

Hugin sources inspected: `src/gimle/hugin/integrations/taskvalet.py`,
`src/gimle/hugin/agent/session.py`, `src/gimle/hugin/interaction/ask_oracle.py`,
`src/gimle/hugin/interaction/oracle_response.py`,
`src/gimle/hugin/llm/models/{openai,anthropic,ollama}.py` and
`src/gimle/hugin/llm/router_outcome.py`. The Anthropic wrapper explicitly requests
five SDK retries. Its current error logging includes conversation/system text;
managed mode needs bounded redacted diagnostics. Missing usage must not become a
zero-cost settlement. Tool/LLM call counters alone cannot bound retry spend.

Taskvalet sources inspected: `swarm_bridges.py` and
`swarm_host/{manager,member,relay,costs,linux,budget}.py` under
`src/taskvalet/`. Three existing patterns to reuse are immutable claim-bound
MemberTools, the canonical HostRuns ledger and the LinuxHost/guardian resource
boundary. A coding bridge is a tool provider, not a native CLI launcher.

#### Gaps and implementation gates

1. **Model protocol and cost contract — blocks managed execution.** The shipped
   relay accepts `{model,max_output_tokens,prompt}` and synthetic text results;
   its closed cost gate supports only `synthetic-only` with the fixed five-micro-USD
   contract. Neither SDK's conversation/tool protocol is implemented there.
   Do not route a real model through that contract. Specify versioned request,
   tool/result, error, streaming and usage envelopes, maximum input/output and
   bounded retry behavior, including cached/reasoning tokens and provider-side tool
   charges. Unknown prices/models/usage remain refused or retain
   reserved exposure. The CLI's exact model wire API is unresolved, not inferred
   from its remote app-server `unix://` option.
2. **Transport versus isolation — blocks qualification.** Task045 uses
   `PrivateNetwork=yes`, `RestrictAddressFamilies=AF_UNIX`, `DynamicUser=yes`
   and per-member LoadCredential. SDK HTTP defaults and a native CLI cannot be
   assumed to work through this profile. First investigate a private Unix-socket
   gateway with a pinned SDK/CLI-compatible client transport. If that is not
   feasible, explicitly design a new confined profile; do not enable general
   TCP or reuse old AF_UNIX rehearsal evidence to certify the change. Prove deny
   behavior for IPv4/IPv6, DNS, loopback, host sockets, inherited descriptors,
   descendants, proxy settings and alternate model/auth routes on Linux.
3. **Native dispatcher — blocks complete runs.** HostRuns rehearsal accounting
   and FixtureHost are not a production process launcher. A Taskvalet-owned
   companion dispatcher must resolve existing journal/actor/claim bindings,
   verify installed bytes before admission, record owned resources before
   effects and start the guardian before relay/members. Reuse Task044/045;
   do not create another scheduler, claim store or owner queue.
4. **Ambient authority and auxiliary actions — blocks sole-route claims.** Use
   an explicit allowlist for environment, built-ins, tools, MCP endpoints,
   plugins, hooks, telemetry and update paths. CLI defaults are not such an
   allowlist. Determine which controls actually disable these in the pinned
   runtime; unknown behavior remains blocked. Hugin outcome reporting and
   auxiliary/child calls also need explicit routing or exclusion. Host secrets
   stay in the broker, not native workspaces/checkpoints. Every concrete agent,
   including restored/child agents, needs explicit authority binding.
5. **Lifecycle / diagnostics — blocks recovery claims.** Bound streamed logs,
   redact errors, preserve original attribution and claim, and reconcile lost
   responses under the same canonical ID before retry. Native resume/fork must
   not create a fresh shared budget. Prove controller death, relay death,
   cancellation during provider/tool calls and orphan cleanup independently.
6. **Remote artifact contract — blocks remote support.** Task048 is a Lean-pool
   backend, not an already agreed native-agent host API. Agree runtime artifact,
   host incarnation, authoritative ledger, admission/lease/deadline, status,
   storage capabilities and cleanup receipts. An uncertain SSH submission must
   fence the same attempt; no automatic fresh host/local budget fallback.

#### Next bounded work

M1's output is the candidate decision and this gap register. M2 should first
settle the model wire and private transport design, then implement the smallest
dispatcher/adapter contract using existing lifecycle and authority primitives.
Before claiming support, add offline regression tests for: wrong installed bytes
causing zero admission; full native tool success/error/repeat fetch; every model
attempt reserving from one ledger; unknown usage retaining exposure; cross-claim
denial; no authority inheritance; same-ID restart; guardian cleanup; and exact
Linux negative egress. A fresh fake-provider full-loop rehearsal is a separate
next step, not something performed by this audit.

Participation through a skill can be useful without a managed shared-budget
profile. It must be labelled participation-only and cannot satisfy the bounded
profile acceptance criteria. Neither candidate is presently qualified for that
profile. No acceptance checkbox is marked complete by this M1 document; real
local/SSH-Hetzner qualification still needs separate authorization or an explicit
owner scope change. The owner's queue is unchanged.


Owner authorized publication and model-wire/private-relay design in Console on 2026-11-15. No deployment or agent experiment authorized. Independent three-role panel review found no blocking architectural findings; two evidence precision corrections were incorporated. Repository checks could not start because offline dependencies lack pyarrow==22.0.0; the audit remains uncommitted. Full Task004 acceptance criteria remain open.
