---
title: Agent-to-agent communication across machines, not just within one runner
state: ongoing
priority: medium
labels: [design, enhancement, multi-agent]
claimed_by: claude-code
claimed_at: 2026-09-22T09:45:27Z
branch: task/038_inter_agent_messaging
related: [004, 029, 036]
---

# Agent-to-agent communication across machines

**Status: design settled (2026-09-22).** The survey below is the original
capture and the evidence the design rests on; it is unchanged. The four
questions it said to answer before building are answered under "The questions
this was blocked on". The design itself is in `## Plan`.

## Context

### The idea

> Is there a way that Hugin agent sessions could communicate with each other —
> between computers, for example? So not sessions within the same runner, but
> between machines.

Today every form of coordination Hugin has assumes one process. Two agents can
talk only if both are live Python objects in the same `Session`.

### What exists today, and why it is process-local

Four mechanisms, all of which pass a live object reference:

| Mechanism | Where | What it passes |
|---|---|---|
| Direct messaging | `agent/agent.py:361-368` — `message_agent()` calls `stack.insert_external_input()`. Example: `examples/agent_messaging` | The caller must already hold the target `Agent` object |
| Sub-agents | `interaction/agent_call.py:98-111` creates the child via `parent_agent.session.create_agent_from_task(...)`; the child's `TaskResult.step()` resumes the parent by pushing an `AgentResult` onto `task_def.caller.stack` (`interaction/task_result.py:136-143`) | An id on the wire, a live object at resolution time — see below |
| Stepping | `Session.step()` (`agent/session.py:158-179`) iterates `self.agents` | A list of live agents in one interpreter |
| Shared state | `Environment.env_vars`, e.g. the documented `{"worlds": {"world_1": shared_world_object}}` (`CLAUDE.md`, "Shared State"); and `SessionState` (`agent/session_state.py`), reached via `stack.get_shared_state` / `set_shared_state` | Arbitrary live Python objects — not serialisable in general |

So "cross-machine" is not a transport problem bolted onto an existing seam. Each
of these would need a remote answer, and the shared-state one may not have a
good answer at all in its current form.

Three details that shape the work more than the table does:

- **The inbox is ephemeral.** `insert_external_input` appends to
  `Stack.queued_interactions` (`interaction/stack.py:53`, `:431-441`), and
  `Stack.to_dict` (`:675-687`) serialises only `interactions` and `artifacts`.
  An in-flight message does not survive a save, a reload, or a crash. Any
  cross-machine delivery needs a durable inbox that does not exist yet, even
  for the local case.
- **The sub-agent path is closer to portable than it looks.** `caller` is stored
  as `caller_id` and resolved lazily through
  `session.get_agent(caller_id)` (`interaction/task_definition.py:34-43`). The
  persisted form is already id-based; only the *resolution* is in-process. But
  the push is guarded by a bare `if task_def.caller:` with no else branch, so an
  unresolvable caller fails silently — a parent on another machine would simply
  wait forever. `Waiting`'s own check is purely structural (`interaction/waiting.py:50-67`):
  no liveness check, no timeout, no heartbeat.
- **Shared state round-trips lossily.** `SessionState.from_dict`
  (`agent/session_state.py:304-321`) explicitly does not rehydrate — its
  docstring says objects "will need to be reconstructed by the application code".
  `Environment.env_vars` is never serialised at all.

### What is already networked (prior art to reuse, not rebuild)

- **Sandbox SSH backend** — `sandbox/ssh.py`, registered at `sandbox/sandbox.py:157`,
  alongside `docker.py` and the egress proxy in `egress_proxy.py`. Hugin can
  already run an agent's *commands* on another host. Note the boundary: this
  distributes **tool execution**, not agent sessions. The agent stays here.
- **Monitor server** — `cli/monitor_agents.py`, the only HTTP server in the
  package. It reads a storage directory; no endpoint injects input into an agent.
- **`the_hugins` world server** — `apps/the_hugins/world_server.py:702,877` is the
  one place a network request already drives an agent: a POST resolves
  `session.get_agent(id)` and calls `agent.message_agent(...)`. It works only
  because the HTTP handler shares a process with the session (the session is a
  class attribute, `:26`). This is the shape the idea wants, with the
  process boundary still in the wrong place.
- **Router correlation** — `llm/router_correlation.py` and `llm/router_outcome.py`
  already stamp a `session.id` across sub-agent LLM calls and report an
  edition's outcome to an external endpoint. Evidence that a session id is
  already a meaningful cross-process handle.

### The likely seam

`Storage` is an ABC (`storage/storage.py:21`) with `LocalStorage`
(`storage/local.py:52`) as its only implementation, persisting sessions, agents,
interactions and artifacts. If two machines shared a storage backend they would
already share the durable half of a session. That is worth investigating first,
because it is the one place the codebase is already abstract.

It is not sufficient on its own, and it is not ready as it stands:

- `Storage.store` (`storage/storage.py:28`) is an in-process object cache that is
  never invalidated — two processes on one backend would serve each other stale
  objects.
- There is no locking, no CAS or etag, no transactions. `_save_session` is a
  plain non-atomic write (`storage/local.py:192-196`); only
  `_detach_artifact_reference` bothers with a temp-file replace (`:170-183`).
- `Stack.step` holds a non-reentrant `_step_lock` (`interaction/stack.py:54`,
  `:395-399`), i.e. the scheduler assumes one thread per session.
- An agent is not self-describing: `Tool.registry` is a process-global `ClassVar`
  (`tools/tool.py:96`), and `Environment.load` mutates `sys.path` and imports
  tool modules by bare name (`agent/environment.py:327-356`). A machine can only
  step an agent whose package tree it can already import.

And storage only records what happened. It does not step an agent, deliver a
message to a *running* stack, or tell machine B that machine A wants something.
At minimum it leaves open: who steps which agent, how a waiting agent learns it
can resume, and what happens when two machines write the same session.

### Discipline the sandbox work already established

Whatever this becomes, it should not re-learn what tasks 023-033 already paid
for:

- `Sandbox` is an ABC with a lazy backend registry (`sandbox/sandbox.py:111-120`)
  explicitly modelled on the `Storage` ABC — the repo's own precedent for
  "pluggable, and one of them is remote".
- The SSH backend refuses to guess: a completion sentinel distinguishes "the
  command finished" from "the connection dropped mid-command", and the latter is
  raised as do-not-retry rather than retried (`sandbox/ssh.py:104-117`). A
  partition cannot hang a turn, and cannot silently double-execute.
- The reaper already stamps ownership with PID, process start time, boot id and
  hostname (`sandbox/reaper.py`) — the codebase has thought about "which machine
  and which incarnation owns this" before.
- `session.id` already works as a cross-service correlation key over HTTP
  (`llm/router_correlation.py`, `llm/router_outcome.py`).

### The questions this was blocked on, now answered

Resolved in conversation with the repo owner, 2026-09-22. The original
questions are kept verbatim so the reasoning can be audited.

1. **What is the actual use case?** Of the four shapes listed — fan-out
   compute, capability-specific machines, long-lived agents conversing, and
   session hand-off — it is the **third**. The stated aim is swarms of agents
   working a problem together: asking each other for input, answering each
   other's requests, and posting updates others can pick up. Fan-out remains
   task 004's problem, and hand-off is not what is wanted.

2. **Does it need to be live, or is durable hand-off enough?** Neither, quite.
   Hand-off is the wrong shape — both agents are alive and the conversation
   matters. But "live" does not require a live *transport*: both modes reduce to
   writing a message to shared durable storage and waiting on a condition that
   reads it back. See "Delivery" in the plan. This retires the proposed
   shared-`Storage` hand-off spike, which answered shape 4.

3. **What is the trust boundary?** Group membership, declared statically in
   config. A message arriving on a group an agent did not declare is dropped
   before it reaches the stack. See "Trust boundary".

4. **What breaks in `env_vars`?** It stays explicitly local. Nothing in this
   design serialises live objects; agents exchange message bodies, not state.
   A serialisable shared-state contract is a separate question and is not
   needed for this.

One correction to the survey above: `### The likely seam` nominates `Storage`
as the seam because it is the one place the codebase is already abstract. That
is still right, but for a different reason than it gives. Storage is not the
session hand-off medium — it is the **message board**. The concurrency problems
it lists (`Storage.store` caching, no locking or CAS) still apply and are
prerequisites either way.

### Relationship to existing tasks

- **004 — Define portable local and cloud agent-run orchestration.** Adjacent and
  should be settled first. 004 is about running *a* run somewhere else, with a
  backend-neutral run contract, stable run ids and a storage capability
  statement. Much of what 004 must define (run id, storage that is not a local
  filesystem, resume policy) is a prerequisite here. This task is the different
  question of two runs *talking* while both are alive.
- **026 — Bash sandbox SSH/remote backend (merged).** Prior art for reaching
  another machine, at the tool layer.
- **029 — Bash sandbox "harness blend" (open, parked).** Proposes a shared
  filesystem medium with a `common/` area for **cross-agent hand-offs** and a
  one-writer-per-object invariant. Single machine, but it is the same hand-off
  question one layer down; the two should not answer it differently.
- **006 — Support batched tool calls end-to-end.** Unrelated, but touches the
  same stepping loop; worth checking for interactions if both land.
- **036 — `hugin create` test stage never runs (open).** The same defect with no
  network involved: the CLI steps only the parent while the resume path depends
  on the child being stepped. Every ask in this design has that shape, so 036
  should be fixed before any of it — it is cheaper to debug locally.


## Plan

### Two modes, one mechanism

**Ask.** A message sent to an address, expecting answers. The sender waits, with
a deadline and an answer count. Recipients may be one or many; "ask one agent"
is not a separate case, it is the case where one agent happened to be listening.

**Post.** A message sent to an address, expecting nothing. An FYI. Nobody waits,
so nothing can hang, and delivery can be best-effort.

These are not two systems. An ask is a post plus a correlation id and a wait
state. Building them separately would duplicate addressing, delivery and
durability in both.

### The envelope

One message type, extending `ExternalInput` (today it carries only
`input: Optional[str]`, `interaction/external_input.py`):

| Field | Post | Ask | Reply |
|---|---|---|---|
| `uuid` | own id | own id — **this is the correlation id** | own id |
| `sender` | swarm + group + role + agent uuid | same | same |
| `to` | group + topic | group + topic | — |
| `reply_to` | absent | absent | the ask's `uuid` |
| `body` | text | text | text |
| `ttl` | hop budget | hop budget | hop budget |

`reply_to` absent means a post; present means a reply. That single optional
field is the whole difference between the two modes.

The correlation id needs no new concept: every `Interaction` already gets a
uuid from `@with_uuid` (`utils/uuid.py`), and ids are already the persisted
form throughout — `Stack.to_dict` stores interaction ids, `TaskDefinition`
stores `caller_id`. The asker mints it and it travels in the envelope; nobody
ever looks it up. One ask produces N replies all sharing one `reply_to`, so it
is a thread id, not a pair id — which is exactly what the group case needs.

For multi-hop tracing (B asks C in order to answer A) reuse `session.id`, which
`llm/router_correlation.py` already treats as a cross-service trace key. Do not
invent a third identifier.

### Addressing

**A generated uuid can never be an address.** `Agent.id` is a local `uuid4`
(`agent/agent.py:94`), so one machine cannot name an agent on another. The
existing `examples/agent_messaging` tool only works because it iterates
`session.agents` to find its target. An address must be something both sides
can write down *before either process starts*, which means it must be static
config.

Two levels, both declared up front:

- **Group** — membership and trust. Who hears this, and whose messages I accept.
  Like a mailing list: an agent subscribes once, and topics added later reach it
  without a config change.
- **Topic** — filtering within a group an agent has already agreed to listen to.

Per group, an agent declares `post` and `read` separately. That asymmetry is the
permission axis that matters: an agent with `read` but not `post` on a group
cannot flood it.

Sketch, to be firmed up in Phase 1 — a swarm-level file declaring the groups,
shared by every machine:

```yaml
swarm: market_research
groups:
  research:
    topics: [findings, sources, questions]
  alerts:
    topics: [halt, anomaly]
```

and, in an agent config, what that agent may do with them:

```yaml
name: analyst
messaging:
  research: [post, read]
  alerts: [read]
```

Rules that fall out:

- **Role is identity, not an address.** `config.name` goes in `sender`. "Ask all
  analysts" is a group named `analysts`, so role addressing needs no separate
  mechanism.
- **Every address is multicast.** Several agents can read one group; that is the
  point. There is no single-recipient primitive to write.
- **Topics are advertised, not enforced.** Enumerate a group's topics in config
  so they can be rendered into agent prompts — an LLM agent cannot discover a
  topic by observing traffic, it has to be told. But warn on an undeclared
  topic rather than rejecting it. A closed set makes every new topic a change to
  a file that must stay identical on every machine. Closed-to-open is an easy
  change later; open-to-closed breaks live senders.
- **Addresses need a scope.** Two unrelated runs both have an `analysts` group.
  A swarm id sits above groups — and it **must be assignable, not generated**.
  See prerequisites.
- **A learned uuid is a weak reference.** An agent uuid arriving in `sender` may
  be used as a return address, but the agent may have finished or its machine
  gone. Learned, never discovered, and never assumed live.

Naming: do not call the swarm scope a *namespace*. `--namespace` already means
shared-state namespaces in the CLI (`cli/run_agent.py:710`).

### One completion policy

Wait-for-first, wait-for-N, wait-for-quorum and wait-with-timeout are one
policy with two knobs: **proceed when `n` replies have arrived, or when
`deadline` passes.** `n=1` is first-wins; a generous `n` and deadline is
collect-all; a short deadline is time-boxed.

Both knobs are always present. A count alone hangs whenever fewer than `n`
agents ever reply, which in a swarm is the normal case rather than the edge
case, because the sender does not know how many recipients there were. A
deadline alone always costs the full wait even when everyone answered at once.

**Zero replies is a success, not an error.** The continuation must run on an
empty set. Nobody knew the answer, or nobody was listening, and the agent needs
to carry on.

### Changes to `Waiting`

`Waiting` plus `Condition` is the right seam, and a better one than the survey
above identified. A `Condition` serialises as an evaluator *name* plus a
parameters dict (`interaction/conditions.py:44`) and resolves through a registry
at evaluation time — it holds no live object reference, so it is already
portable. That is precisely what the `AgentCall`/`caller` resume path is not.

Three changes:

1. **`expires_at`, absolute and on the interaction.** Not a countdown.
   `wait_for_seconds` (`interaction/conditions.py:188`) seeds `time.time()` into
   shared state on first evaluation, and `SessionState.from_dict` does not
   rehydrate — so a save and reload silently restarts the timer. Compute an
   absolute wall-clock deadline at creation and store it on the `Waiting`. A
   scheduler can then see what has expired without evaluating anything.
2. **A second exit.** Today there is one continuation: the condition goes False
   and `next_tool` runs. Nothing distinguishes *I got my answers* from *I gave
   up*. Add `on_timeout` alongside `next_tool`.
3. **A `replies_received` evaluator**, parameterised by correlation id and `n`,
   counting matching messages. `all_branches_complete`
   (`interaction/conditions.py:112`) is the local ancestor — a real join, but
   only over in-process branches.

Note `wait_for_ticks` (`interaction/conditions.py:139`) is unusable across
machines: a tick is a session step, so the clock runs at whatever rate the
machine that happens to be stepping you sets. Wall clock is the only shared
reference.

### Delivery: one board, no live transport

Both modes reduce to a write to shared durable storage plus a condition that
reads it back. **No live transport is needed for v1.** An ask is a board write
and a `replies_received` condition; a reply is a board write; a post is a board
write that nobody waits on. Latency is bounded by step rate, which for agents
between LLM calls is seconds — irrelevant next to the calls themselves.

This is where the `Storage` seam genuinely earns its place, and it is worth
being explicit that it is **not** the role the survey proposed for it. Storage
is the board, not a session hand-off medium.

It also bounds the cost that would otherwise sink this at swarm scale. Every
delivered message is tokens in somebody's prompt, forever. Pushing every post
into every subscriber's stack is O(n^2) in tokens. Pulling from a board means an
agent pays only for the topics it reads, when it reads them. The batching at
`interaction/stack.py:379` — queued interactions drain only when the next
interaction is an `AskOracle` — helps, but it coalesces rather than bounds.

If a live transport is later shown to be needed, it is an optimisation over this
design, not a replacement for it.

### Trust boundary

An `ExternalInput` arriving from another machine is prompt injection with a
network interface. The containment is declarative, not textual:

- A message on a group the agent did not declare `read` on is **dropped before
  it reaches the stack**. Config is the allowlist.
- A reply is addressed to a correlation id, not a group, so it bypasses that
  check. Close it: accept replies on a correlation id only from senders in the
  group the ask went to.
- `ttl` decrements per hop, and an agent does not wake on its own thread.
  Swarms loop — A replies to B, B posts, the post wakes A. Cheap now, miserable
  to retrofit against a live swarm.

### Prerequisites

Each is a defect on one machine too, and each is independently worth fixing.

1. **A durable inbox.** `Stack.to_dict` serialises only `interactions` and
   `artifacts`, so `queued_interactions` (`interaction/stack.py:53`, `:441`) is
   silently dropped on save. Every message in flight is lost on a restart.
2. **Assignable swarm identity.** `Session.id` is a `uuid4` with a setter
   (`agent/session.py:85`) that nothing in the CLI ever calls — there is no
   `--session-id`. The handle the survey nominated as the ready-made
   cross-service key cannot itself be agreed between two machines, for exactly
   the reason a uuid cannot be an address. It works for the router only because
   one process both mints it and sends it.
3. **Who steps the responder** — task 036, which is this bug with no network
   involved.
4. **`Storage.store` invalidation and write concurrency**, as the survey's
   `### The likely seam` already sets out.

### Phasing

- **Phase 0 — prerequisites.** Durable `queued_interactions`; assignable swarm
  id; fix 036; `Storage` cache invalidation and a stated write-concurrency
  policy. No messaging yet, and all four are useful without it.
- **Phase 1 — addressing and post.** Group/topic config schema and validation;
  the board on `Storage`; post and pull; group `read`/`post` enforcement. Posts
  work across two processes. No asks.
- **Phase 2 — ask.** `reply_to` on the envelope; `expires_at` and `on_timeout`
  on `Waiting`; the `replies_received` evaluator; the `(n, deadline)` policy
  with the empty-set path. Asks work across two processes.
- **Phase 3 — hardening.** `ttl` and loop damping; the reply ACL; an end-to-end
  test with two processes on one board, including partition and timeout.

## Outcome

- [ ] `queued_interactions` survives a save and reload; a test asserts a queued
      message is still there after a round trip through storage.
- [ ] A swarm id can be set from config or the CLI, and two independently
      started processes share one.
- [ ] Groups and topics are declared in config, with `post`/`read` per group.
      A message on an undeclared group never reaches the agent's stack; a
      message on an undeclared topic is delivered with a warning.
- [ ] Two agents in separate processes on one machine exchange a post through
      a shared board, with neither holding a reference to the other and neither
      knowing the other's agent uuid.
- [ ] An agent asks a group and resumes on `(n, deadline)`: `n=1` returns on the
      first reply; a deadline with no replies runs the `on_timeout` path; an
      empty reply set is handled without error.
- [ ] A `Waiting` with `expires_at` still expires correctly after the stack has
      been saved and reloaded.
- [ ] The same exchange works with the two processes on different machines
      against shared storage.
- [ ] A reply whose sender is not in the group the ask went to is rejected.

## Notes

Deliberately left open, to be decided on evidence rather than up front:

- **A live transport.** v1 is board-and-poll. Add one only if measured latency
  proves it necessary; it would be an optimisation over this design.
- **Board retention.** How long posts live, and who prunes. Touches task 003's
  lifecycle work and should not answer it differently.
- **Group config distribution.** The group definitions are the one piece of
  state both machines must share, and being static is what makes that cheap —
  no registry, no consistency protocol, no liveness. But the file still has to
  get to both machines. Same class of problem as `Environment.load` needing an
  importable package tree, and much lighter.
- **Interaction with task 029.** 029 proposes a shared filesystem area for
  cross-agent hand-offs with a one-writer-per-object invariant. That is the same
  board question one layer down; if both land, they should share a medium rather
  than inventing two.
