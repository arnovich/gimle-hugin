---
title: Agent-to-agent communication across machines, not just within one runner
state: ongoing
priority: medium
labels: [design, enhancement, multi-agent]
claimed_by: claude-code
claimed_at: 2026-09-22T09:45:27Z
branch: task/038_inter_agent_messaging
depends_on: ["036", "039", "040", "041"]
related: ["003", "004", "029"]
---

# Agent-to-agent communication across machines

**Status: design settled 2026-09-22, revised the same day after a panel
review.** The survey under `## Context` is the original capture and is
unchanged. `## Decisions` records what was settled, and what the review
corrected. `## Plan` is the design.

The review moved this task's prerequisites out of it: they are now tasks 039,
040 and 041, alongside the existing 036, and this task depends on all four.
None of them is messaging work — each is a defect on one machine today.

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
- **039 — Storage metadata can load arbitrary Python (open, filed from this
  review).** A hard dependency: it is what stops "can write the board" from
  escalating to code execution in the operator's CLI process.
- **040 — External input delivery defects (open, filed from this review).** The
  inbox this design delivers through loses messages, buries a turn, and cannot
  leave the context window.
- **041 — Waiting agents burn the step budget (open, filed from this review).**
  A parked ask is only affordable once this is fixed.


## Decisions

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

### What the panel review changed

The design was reviewed on 2026-09-22 by five judges — distributed systems,
security, codebase fit, implementability, and cost at scale. Every claim below
was verified against the source before it was accepted. The addressing model,
the two-modes-one-envelope reduction and the inseparable `(n, deadline)` policy
survived unchanged. The delivery and resume halves did not.

**One design decision reversed.** The ask parked on `Waiting` with a
`Condition`. It now parks on a `MessageWaiting` modelled on `BashWaiting`,
because a `next_tool` chain leaves the model's `tool_use` block unpaired — a
fact the repo had already established twice and written down
(`interaction/bash_waiting.py:13-18`). The original section cited "Discipline
the sandbox work already established" and then re-learned one of its lessons.

**Four factual errors corrected.**

| Was claimed | Actually |
|---|---|
| `wait_for_seconds` loses its start time across a reload | False — `SessionState` writes plain values verbatim and a float round-trips. The real defect is key aliasing: any delivered message resets the clock |
| `Agent.id` can never be an address, while `Session.id` is a prerequisite | Both are `@with_uuid` and equally assignable. The obstacle is communicating an id at all, not minting one |
| Reuse `session.id` for multi-hop tracing | It is the router's lifetime spend-budget key (#124). A swarm sharing one would share one budget and post competing outcomes. `trace` is now its own field |
| `all_branches_complete` is a real join | It is `isinstance(last, Waiting)` — a structural test, and one an ask parked on `Waiting` would falsely satisfy |

**Three sections added** because the original specified sending and not
consuming: `### Delivery semantics` (at-least-once, cursors, dedupe),
`### The board` (layout, atomicity, cache bypass) and `### Tool surface` (what
an agent actually invokes, plus a worked trace).

**The trust section was rewritten.** It called static group config "the trust
boundary"; every control it described is evaluated against fields the sender
writes, with no authentication anywhere in the design or the repo. It now states
plainly what the model defends against and refuses a cross-machine board unless
explicitly enabled.

**`### What it costs` was added**, because the original measured token fan-out —
the one cost pull-over-push already addresses — and missed the three that
dominate: delivered text cannot leave the context window, a parked agent spins
the session loop, and `n` does not bound fan-out.

**The prerequisites left this task.** They were four unrelated pieces of
framework surgery, and the standard's one-task-one-concern rule applies: they
are now tasks 039, 040 and 041 alongside the existing 036, and this task
`depends_on` all four.

## Plan

### Two modes, one mechanism

**Ask.** A message sent to an address, expecting answers. The sender parks, with
a deadline and an answer count. Recipients may be one or many; "ask one agent"
is not a separate case, it is the case where one agent happened to be listening.

**Post.** A message sent to an address, expecting nothing. An FYI. Nobody parks,
so nothing can hang, and nothing needs waking.

These are not two systems. An ask is a post plus a correlation id and a parked
branch. Building them separately would duplicate addressing, delivery and
durability in both.

### The envelope

A board record, with its own wire schema. It is **not** an `Interaction` and is
**never** parsed with `Interaction.from_dict`, which dispatches on a persisted
`type` field into the process-global registry and loads artifacts before the
type check (`interaction/interaction.py:189-221`). A board entry is parsed by a
dedicated strict parser that accepts one shape and rejects everything else.

| Field | Post | Ask | Reply |
|---|---|---|---|
| `v` | schema version | schema version | schema version |
| `uuid` | own id | own id — **the correlation id** | own id |
| `sender` | swarm, group, role, agent uuid | same | same |
| `to` | group + topic | group + topic | — |
| `reply_to` | absent | absent | the ask's `uuid` |
| `trace` | causal chain id | causal chain id | inherited from the ask |
| `ttl` | hop budget | hop budget | inherited, minus one |
| `expires_at` | — | absolute, from the asker's clock | — |
| `body` | text | text | text |

`reply_to` absent means a post; present means a reply. That single optional
field is the whole difference between the two modes.

The correlation id needs no new concept: every `Interaction` already gets a uuid
from `@with_uuid` (`utils/uuid.py`), and ids are already the persisted form
throughout. The asker mints it and it travels in the envelope. One ask produces
N replies all sharing one `reply_to`, so it is a thread id, not a pair id —
which is what the group case needs.

Three rules the fields only work under:

- **`trace` is its own field.** An earlier draft reused `session.id` for
  multi-hop tracing. That is wrong twice over: `session.id` is minted per
  process and two machines cannot agree on one, and it is now the router's
  lifetime spend-budget key (`llm/router_correlation.py`, `x-gimle-session`,
  landed in #124). A swarm sharing one `session.id` would share one spend
  budget non-deterministically and post competing outcomes from every machine.
  `trace` is minted by the originating ask and inherited across hops;
  `session.id` stays per-process and keeps meaning one run, one budget, one
  outcome.
- **`ttl` is inherited, not reset.** A message minted while handling message M
  carries `M.ttl - 1`, and `ttl <= 0` cannot be sent. Without the inheritance
  rule a hop budget bounds nothing, because a reply and a follow-up post are new
  messages with fresh budgets. A hop budget bounds *depth*, not fan-out — see
  "What it costs" for the fan-out bound.
- **`v` is present from the first record written.** The board is a wire format
  between independently-deployed machines. Unknown fields are preserved on
  round-trip, never silently dropped.

### Addressing

**A minted uuid can never be an address.** `Agent.id` and `Session.id` are both
locally generated (`@with_uuid`), so one machine cannot name an agent on
another. Both are in fact *assignable* — `@with_uuid` accepts `uuid=`, and both
classes have setters (`agent/agent.py:104`, `agent/session.py:85`) — but nothing
assigns them, and assigning them would not help: the id would still have to be
communicated before it could be used, which is the problem. An address must be
something both sides can write down *before either process starts*.

Two levels, both declared up front:

- **Group** — membership. Who hears this, and whose messages I am willing to
  accept. Like a mailing list: an agent subscribes once, and topics added later
  reach it without a config change.
- **Topic** — filtering within a group an agent already subscribes to.

Per group, an agent declares `post` and `read` separately.

The swarm-level file, shared by every machine:

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

`Config` is a closed dataclass and `Config.from_dict` does `cls(**data)`
(`agent/config.py:73`), so `messaging:` must be a declared field — it cannot be
added as a loose key. The existing precedent to mirror is `state_namespaces`
(`agent/config.py:39`), a per-agent permission list enforced in
`SessionState._can_access` (`agent/session_state.py:232-268`). Follow its shape
rather than inventing a parallel permission axis.

Rules that fall out:

- **Role is identity, not an address.** `config.name` goes in `sender`. "Ask all
  analysts" is a group named `analysts`.
- **Every address is multicast.** There is no single-recipient primitive to
  write; one reader is the degenerate case.
- **Topics are advertised, not enforced.** Enumerate them so they can be
  rendered into prompts — an LLM agent cannot discover a topic by watching
  traffic, it has to be told. Warn on an undeclared topic rather than rejecting
  it: a closed set makes every new topic a change to a file that must stay
  identical on every machine, and closed-to-open is easy later while
  open-to-closed breaks live senders. But the warning goes **in the tool
  result**, not only to a logger — see "What it costs".
- **Swarm and group names are validated at load** against
  `^[A-Za-z0-9._-]{1,64}$`. They become path components on the board, and
  `LocalStorage` joins ids into paths without validation
  (`storage/local.py:195`).
- **A learned uuid is a weak reference.** An agent uuid arriving in `sender` may
  be used as a return address, but the agent may have finished or its machine
  gone. Parse it as a UUID at ingest; never use it as a storage key.

Naming: do not call the swarm scope a *namespace*. `--namespace` already means
shared-state namespaces (`cli/run_agent.py:710`).

### Delivery semantics

The original draft described a board and never said how a reader knows what it
has already consumed. That is the single most consequential decision here, so it
is made explicitly:

- **At-least-once, deduplicated by envelope `uuid`.** Handlers must be
  idempotent. A message that causes a tool call is guarded by its envelope uuid
  as an execution key.
- **A durable per-(agent, group) cursor**, persisted with the agent, not on the
  board — it is private, and it must survive a reload. The cursor advances only
  **after** the message is durably in the agent's stack, so a crash re-delivers
  rather than loses.
- **A bounded seen-uuid set** alongside the cursor, to absorb the re-delivery
  that ordering creates.
- **No global ordering.** Messages are a set, not a sequence. Bodies must be
  self-contained: send `state: halted`, not `halt` followed by `resume`. Per-
  sender FIFO is available if wanted by adding a monotonic per-sender sequence
  number, which costs one integer and needs no clock; it is not in v1.
- **`n` counts distinct senders**, keyed on `sender.agent` plus `reply_to`, last
  write wins on body. Counting messages would let one flapping agent satisfy a
  quorum of three by itself.

### The board

One immutable JSON object per message, never mutated, never rewritten:

```
board/<swarm>/<group>/<topic>/<YYYYMMDD>/<uuid>.json
```

- Written temp-then-`rename`, with fsync. `LocalStorage._save_session` is a
  plain truncating write (`storage/local.py:192-196`); a reader polling a
  partially-written board entry gets a `JSONDecodeError`. Only
  `_detach_artifact_reference` does the atomic dance today (`:170-183`); the
  board must.
- **Built on the existing `Storage.save_file` / `load_file`**
  (`storage/storage.py:365-382`), not on new abstract methods. `Storage` has two
  implementations, not one — `LocalStorage` and the tests' `MemoryStorage`
  (`tests/memory_storage.py`) — and adding abstract methods breaks both plus any
  third-party subclass.
- **Board reads bypass `Storage.store` entirely.** That cache is populate-only
  and never expires (`storage/storage.py:68-72`, `:285-288`), so a cached board
  read would return the same answer forever. The cache is for immutable
  historical objects; board records are immutable but their *listing* is not.
- **Time-partitioned** so a cursor bounds the scan to new partitions. Without
  it every poll is O(all messages ever) and retention becomes load-bearing
  rather than deferrable.

An append-only collection of immutable objects needs no locking, no CAS and no
transactions — which is why this shape is chosen over a single mutable board
document. Concurrent writers never contend. The one thing a backend must
promise is atomic single-object create plus read-after-create visibility to
other clients; `LocalStorage` over NFS does not promise the second, so a
shared-filesystem deployment carries that caveat explicitly.

### How an ask parks and resumes

**Not `Waiting` with a `Condition`.** An earlier draft chose that seam because a
`Condition` serialises as an evaluator name plus a parameters dict and holds no
live object reference. That reasoning is correct and the conclusion was still
wrong, because the repo has already solved this problem twice and rejected
exactly this approach:

`BashWaiting`'s module docstring states it outright
(`interaction/bash_waiting.py:13-18`): resolving via a proper `tool_result` —
not a `next_tool` chain — is load-bearing, because a chained `ToolCall` carries
`tool_call_id=None` (`interaction/waiting.py:91`), which renders as a plain-text
message and leaves the model's original `tool_use` block unpaired: an Anthropic
400. `AgentResult.step` does the same thing correctly
(`interaction/agent_result.py:51-58`). `Waiting` predates both.

So an ask parks on a **`MessageWaiting`**, modelled on `BashWaiting`:

- Its `step()` polls the board with a bounded read — only records whose
  `reply_to` is this correlation id, only in partitions at or after the ask's
  own — and returns "idle until T" rather than "active" (task 041).
- On completion it resolves into a real `tool_result` bound to the **originating
  ask call's** `tool_call_id`, carrying the replies.
- The timeout path produces the *same* tool_result shape with whatever replies
  exist and a `reason`. One resolution point, two payloads — which removes the
  need for the `on_timeout` second continuation an earlier draft proposed, and
  removes the question of what happens to a partial set at the deadline.
- The collect is fully guarded and never raises. An exception escaping a tool
  leaves the stack's step-lock held and kills the agent for the rest of the
  session (`interaction/bash_waiting.py:17-18`).
- It records its **branch**, and delivery targets that branch.
  `insert_external_input` builds an `ExternalInput` with `branch` defaulting to
  `None` (`interaction/stack.py:440`), so a branched agent would never see its
  reply — task 040.

Two further reasons this is the better seam:

- A `Condition` returns a **bool**, so reply bodies would not travel with the
  resume. The continuation would have to re-read the board and could not know
  which replies the condition had counted.
- `Stack.is_branch_complete` is `isinstance(last_interaction, Waiting)`
  (`interaction/stack.py:197-198`), so a branch parked on a `Waiting` reads as
  *finished* to any join over branches. `all_branches_complete`
  (`interaction/conditions.py:112`) is built on it and is a structural test, not
  the real join an earlier draft called it. A distinct interaction type
  sidesteps this for free.

`expires_at` is absolute, computed at creation, stored on the interaction. The
justification an earlier draft gave for this — that `wait_for_seconds` loses its
start time across a reload — **is false**: `SessionState` writes plain values
verbatim (`agent/session_state.py:295-297`) and a float round-trips. The real
reason is worse. The key is `_wait_seconds_{last.uuid}` where `last` is
`get_last_interaction_for_branch` (`interaction/conditions.py:218-221`), so
delivering any message onto that branch changes the key and restarts the clock
from zero. Under this design that means **any group member can reset another
agent's in-flight deadline, indefinitely**. The same aliasing affects
`wait_for_ticks`. An absolute deadline on the interaction is immune.

Two traps to name so they are not found at implementation time:

- `Waiting._from_dict` is a hand-rolled field whitelist
  (`interaction/waiting.py:113-131`), unlike the generic
  `Interaction._from_dict`.
  A new field added to the dataclass will *serialise* and deserialise as `None`.
  `MessageWaiting` must not repeat that pattern.
- The persisted type name **is** the registry key
  (`interaction/interaction.py:116`, `:210-216`), and `Stack.from_dict` swallows
  an unknown type as a `logger.warning` and drops the interaction
  (`interaction/stack.py:722-735`) — silent data loss, not a load failure. Name
  the types once, in Phase 2, and add a round-trip test.

Ownership: **the agent's own stepping loop is the sole authority on its own
`expires_at`.** A scheduler or monitor may observe it, never act on it. Clock
skew between machines otherwise turns a deadline into a race, and NTP is a
stated deployment precondition.

### One completion policy

Wait-for-first, wait-for-N, wait-for-quorum and wait-with-timeout are one policy
with two knobs: **resume when `n` distinct senders have replied, or when
`expires_at` passes.** `n=1` is first-wins; a generous `n` and deadline is
collect-all; a short deadline is time-boxed.

Both knobs are always present. A count alone hangs whenever fewer than `n`
agents ever reply, which in a swarm is the normal case rather than the edge
case, because the sender does not know how many recipients there were. A
deadline alone always costs the full wait.

**Any number of replies is a success, including zero and fewer than `n`.** The
resume carries the replies that exist plus a `reason` (`answered` or
`deadline`) plus the subscriber count the ask went to. The deadline is always
re-read against the board after it is judged to have passed, so a reply that
landed before the deadline is never dropped on a race.

The ask's `expires_at` travels **in the envelope**, so a responder whose clock
says the deadline has passed declines before spending a model call. A reply
written after the deadline is stored but never delivered; a correlation id is
dead once its `MessageWaiting` has resolved.

`timeout_s` is clamped to a configured maximum at creation. Otherwise an agent
whose deadline came from an LLM-chosen tool argument, in a turn triggered by a
message, can park for a week.

### What it costs

The original draft argued pull-over-push on token fan-out and stopped there.
That was the wrong resource to measure. Three costs dominate and each needs a
bound stated in the design, not discovered in production.

**Delivered text must be able to leave the context window.** Today it cannot:
`AskOracle.create_from_external_input` builds a prompt with no `tool_name`
(`interaction/ask_oracle.py:61-69`), and every trimming policy in
`render_stack_context` hangs off that field (`interaction/stack.py:247`,
`:221-222`). Every tool result in Hugin can be elided after its context window;
a delivered message cannot, by construction, so it is carried in full on every
subsequent turn for the life of the agent. Messages must participate in the
context policy with a finite default window. This is task 040, and it is the
single largest cost in the design.

**A parked agent must be cheap.** `Session.run` has no sleep and calls
`save_session` every iteration, cascading to every interaction of every agent;
`Waiting.step()` returning `True` counts as activity, and `--max-steps` counts
loop iterations. A realistic deadline therefore exhausts the step budget in
milliseconds while rewriting the whole stack thousands of times. The claim an
earlier draft made — that latency is bounded by step rate, which is seconds and
irrelevant next to LLM calls — is true of the active path and exactly backwards
for the idle one, where there is no LLM call pacing anything. This is task 041.
Polling gets an explicit floor and backoff, capped by the nearest deadline.

**Fan-out needs a bound that `n` does not give.** `n` is when the *asker* stops
waiting, not when responders stop being charged: `n=1` costs the same as
`n=all`, because every subscriber still receives the ask, still spends a turn
deciding, and most still answer. A 20-agent group ask is ~19 LLM calls whatever
`n` says. So an ask carries `max_responders`, enforced at the board: the first
k readers to claim the correlation id may reply, the rest see it claimed and
skip. Reads are bounded too — `limit` and a body-size cap, with an explicit
truncation marker rather than silent loss.

**Attribution.** The swarm id gets its own header (`x-gimle-swarm`) alongside
the existing `x-gimle-task` and `x-gimle-route`
(`llm/router_correlation.py`), and calls made while handling a message carry
`x-gimle-group`. Without this, chatter arrives as ordinary input tokens on the
same route as real work and no bill can distinguish them.

**Empty results must say why.** "Zero replies is a success" plus "topics are
advertised, not enforced" otherwise means a typo'd topic burns a full deadline
and reports the same thing as a genuine no-answer — and an LLM, told nothing,
rephrases and asks again. The board knows the subscriber count from static
config, so the ask result carries it, and an undeclared topic is reported in the
tool result rather than only to a logger.

### Tool surface

Nothing in this design reaches an agent except through tools. They live in
`src/gimle/hugin/tools/builtins/`, each `.py` plus `.yaml`, following the
existing builtin pattern.

```
post(group, topic, body, reason=None)
  -> {message_id, delivered_to: <subscriber count>, topic_declared: bool}

read(group, topic=None, limit=20)
  -> {messages: [{message_id, sender, topic, body, created_at}],
      truncated: bool, new_since_last_read: int}
     advances this agent's cursor for that group

ask(group, topic, body, n=1, timeout_s=60, max_responders=None)
  -> parks on MessageWaiting; resolves to a tool_result:
     {replies: [{sender, body, message_id}], reason: "answered"|"deadline",
      asked: <subscriber count>, replied: <distinct senders>}

reply(reply_to, body)
  -> {message_id, accepted: bool}
```

A worked trace, which Phase 2 should reproduce as an integration test:

1. `analyst-1` calls `post("research", "findings", "EURUSD vol is mispriced")`.
   One board object is written. Result says `delivered_to: 3`.
2. `analyst-2` calls `read("research")`. Its cursor was at zero; it gets one
   message and the cursor advances past it. A second `read` returns nothing.
3. `analyst-2` calls `ask("research", "questions", "got the vol surface?",
   n=2, timeout_s=120)`. A board object is written carrying `expires_at`. The
   branch parks on `MessageWaiting`.
4. `analyst-1` and `analyst-3` each `read`, see the ask, and call
   `reply(reply_to=<id>, body=...)`.
5. `analyst-2`'s `MessageWaiting.step()` sees two distinct senders, resolves
   into a `tool_result` on the original `ask` call id carrying both bodies,
   `reason: "answered"`, `asked: 3`, `replied: 2`.

`examples/agent_messaging` stays as the in-process case and is explicitly *not*
superseded; a note in its README should point here for the cross-process case.

### Trust model

The honest statement, which an earlier draft got wrong by calling group config
"the trust boundary":

> **Every process that can write the board holds the combined tool authority of
> every agent that reads it, across every machine in the swarm.**

There is no authentication in this design and none in the repo to inherit.
`sender`, `to` and `reply_to` are all fields the writer fills in, so every
control that reads them — the group ACL, the reply ACL, `ttl` — is evaluated
against attacker-supplied data. They contain **misconfiguration and accidental
cross-talk**, and they give auditability. They do not contain a hostile or
injected writer.

That is an acceptable model for the intended deployment — one operator, one
trusted storage volume — and it is not acceptable silently. So:

- A cross-machine board is **refused unless explicitly enabled**, by a flag
  whose name says what is being asserted (every writer is trusted).
- The board's trust perimeter is the machine set, and that is documented where
  an operator will read it.
- Task 039 is a hard dependency. It is what stops "can write the board" from
  escalating into "runs code in the operator's CLI process", which is a
  different severity class from "can inject text into an agent".
- Envelopes are parsed by a strict parser, never `Interaction.from_dict`.
- Swarm and group names are charset-validated before becoming path components.
- A remote body is rendered fenced, with `sender`, `to` and `reply_to` visible
  as metadata outside the fence, and never in the position a human operator's
  input occupies. Today `ExternalInput` is the channel for human nudges
  (`apps/the_hugins/world_server.py`, `cli/ui.py`) and a remote message reduced
  to it would be indistinguishable from one.
- Loop damping is receiver-side, using state the sender cannot forge: a
  per-(trace, agent) message budget and a per-(group, agent) rate window held
  locally. `ttl` alone damps reply chains, not the A-posts, B-refines,
  C-synthesises dynamic that a swarm actually produces.

If authentication is wanted later, the shape is signed envelopes with keys
distributed alongside the group config, or a backend with real per-writer
authorization (object-store prefix credentials, database roles). Either is a
Phase 4; neither is needed to make the above honest.

### Monitor

`hugin monitor` renders interaction detail from a hand-maintained allowlist
(`cli/monitor_agents.py:1553-1557`, mirrored in
`ui/static/js/monitor.js:2206-2217`), which maps only `input` for
`ExternalInput` and only `status`/`condition` for `Waiting`. Every new field is
invisible until both files are edited. For a feature whose entire debugging
story is "why did this agent never get its answer", the monitor is the tool —
so envelope fields and `MessageWaiting` state are in scope, not a follow-up.

### Phasing

Prerequisites are no longer phases of this task. They are tasks 036, 039, 040
and 041, and this task depends on all four.

- **Phase 1 — addressing, board, post and read.** The groups file, its loader
  and registry; the `messaging` field on `Config` with `post`/`read`
  enforcement; the board layout and its strict parser over
  `save_file`/`load_file`;
  cursors; `post` and `read` tools; `ttl` and `trace` in the envelope from the
  first record; charset validation; the cross-machine guard flag. Two OS
  processes exchange posts through one board directory.
- **Phase 2 — ask and reply.** `MessageWaiting`; `ask` and `reply` tools;
  `(n, deadline)` with distinct-sender counting and the partial-set resume;
  `max_responders`; the reply ACL, which belongs with the reply path it guards
  rather than in a later hardening phase.
- **Phase 3 — hardening and evidence.** Partition and timeout behaviour;
  receiver-side loop damping; the cost regression tests; monitor rendering; a
  two-process E2E harness gated like `tests/test_bash_e2e_backends.py`.

Honest sizing: Phase 1 is two to three PRs, Phase 2 two, Phase 3 one plus the
harness — on top of four dependency tasks. This is not a single sitting, and it
should not be claimed as one.

## Outcome

Stated behaviourally, so they survive the plan changing underneath them.

**Addressing and delivery**

- [ ] An agent config declaring `messaging:` loads without error, and a group
      or swarm name containing a path separator is refused at load time.
- [ ] Two agents in separate OS processes exchange a post through one board
      directory, with neither holding a reference to the other and neither
      knowing the other's agent uuid.
- [ ] A post is delivered exactly once to a reader across a crash and restart
      mid-consume — neither lost nor repeated.
- [ ] Three posts arriving before a reader's next turn all reach the model, in
      one turn.
- [ ] A message on a group the agent did not declare `read` on never reaches
      its context; a message on an undeclared topic is delivered, and the fact
      that the topic was undeclared is visible in the tool result.
- [ ] Two writers publish to one group concurrently; both records are readable
      and neither is partially written.

**Ask and resume**

- [ ] An ask resumes its caller as a `tool_result` paired with the original
      tool call, not as a plain-text turn.
- [ ] An ask resumes on `n` distinct senders, or at its deadline with whatever
      replies exist, and reports which of the two happened plus how many
      subscribers it went to.
- [ ] Two replies from one sender count as one toward `n`.
- [ ] An ask that nobody answers resumes with zero replies and a reason, and
      the run continues.
- [ ] An ask issued on a named branch resumes that branch.
- [ ] A reply written after the deadline is never delivered to the asker.
- [ ] A message delivered to an agent does not reset or extend that agent's
      in-flight deadline.
- [ ] An ask survives a save and reload and still expires at its original
      deadline.
- [ ] A branch parked on an ask is not reported complete by a join over
      branches.

**Cost**

- [ ] An agent waiting sixty seconds performs zero LLM calls and fewer than a
      stated small number of storage operations.
- [ ] A deadline longer than the default `--max-steps` completes rather than
      terminating the run.
- [ ] Rendered context stops growing once a message passes its context window;
      a long run with messaging enabled does not accumulate message text
      without bound.
- [ ] One ask into a group produces at most `max_responders` LLM calls.

**Trust**

- [ ] A cross-machine board cannot be enabled without the explicit flag.
- [ ] A board record whose `type` or shape is not the envelope is refused
      without being hydrated into an interaction.
- [ ] A remote message never renders in the position a human operator's input
      occupies, and its sender, group and topic are visible in `hugin monitor`.
- [ ] A two-agent mutual-post loop terminates within a bounded number of
      messages.

**Cross-machine**

- [ ] The two-process exchange above works with the processes on different
      machines against shared storage. Manual verification; the CI-able form is
      two processes against one board directory.

## Notes

Deliberately left open, to be decided on evidence rather than up front:

- **Authentication.** v1 declares the board a trusted medium (see "Trust
  model"). Signed envelopes, or a backend with per-writer authorization, is the
  shape if that stops being acceptable. Not needed to make v1 honest; needed
  before a board spans a trust boundary.
- **A live transport.** v1 is board-and-poll. Add one only if measured latency
  proves it necessary, and only once task 041 has made a parked agent cheap. It
  would be an optimisation over this design, not a replacement.
- **Board retention, and where message history goes.** The board is
  append-only and time-partitioned, so a cursor bounds the scan regardless —
  which is what makes retention deferrable rather than load-bearing. But once
  messages participate in the context policy (task 040), history that has left
  the window has to go somewhere. A group's message history is exactly the
  corpus shape `dreaming/` already consolidates, and `Learning` artifacts
  already carry scope, provenance and supersession. Phase 1 should store
  messages in a form the dream selector could already select over, so retention
  is not decided twice and differently. Touches task 003.
- **Group config divergence.** The Notes previously deferred *distribution* of
  the groups file; the failure that actually happens is *divergence*. Each side
  validates against its own copy, so an unknown group is dropped on read —
  divergence fails closed, and silently. Phase 1 should at least log it; a
  config digest in the envelope would make it detectable.
- **Interaction with task 029.** 029 proposes a shared filesystem area for
  cross-agent hand-offs with a one-writer-per-object invariant. That is the same
  board question one layer down, and the immutable-object-per-message layout
  here satisfies 029's invariant by construction. If both land, they should
  share a medium.
- **Artifacts are out of scope for v1.** A post with a large body, or an ask
  that wants a document back, has an obvious home in the artifact system and
  none in a text `body`. Revisit once bodies are size-capped.
- **Rewind.** `Stack.rewind_to` deletes rewound interactions from storage
  (`interaction/stack.py:741-810`), but the board keeps posts the agent already
  sent. Rewinding past an ask is therefore asymmetric and unrecoverable. Only
  reachable via `Agent.rewind_to` today; note it alongside retention.
- **Per-sender FIFO.** Not in v1 — messages are an unordered set. A monotonic
  per-sender sequence number in the envelope would give real ordering within a
  sender without any clock, if a use case appears.
