---
title: External input delivery loses messages, buries a turn, and never leaves context
state: closed
priority: high
labels: [bug, interaction, runtime]
related: ["038"]
---

# External input delivery loses messages, buries a turn, and never leaves context

## Context

`Stack.insert_external_input` (`interaction/stack.py:431-441`) is the only way
anything outside an agent gets text into it. It backs `Agent.message_agent`,
the `the_hugins` world server (`apps/the_hugins/world_server.py:702,877`) and
`examples/agent_messaging`. It has four defects, all found during the panel
review of task 038, and none covered by a test — `grep` across `tests/` for
`queued_interactions`, `insert_external_input` or `message_agent` returns
nothing.

Each is a defect today with one agent on one machine. Together they mean the
mechanism cannot carry more than one message at a time, and that whatever it
does carry stays in the context window permanently.

**1. The inbox does not survive a save.** `queued_interactions` is initialised
at `interaction/stack.py:53` and appended at `:441`, but `Stack.to_dict`
(`:675-687`) serialises only `interactions` and `artifacts`. A message that has
arrived but not yet drained is silently dropped on save, reload or crash.

**2. Fan-in delivers only the last message.** The queue drains into the flat
interaction list (`:379-385`). `Stack.step` steps only
`get_last_interaction_for_branch` (`:172-186`, `:411-424`), so given three
queued messages the stack becomes `[..., EI1, EI2, EI3]` and only `EI3.step()`
runs. `EI1` and `EI2` are neither `AskOracle` nor `OracleResponse`, so
`render_stack_context` never renders them either — their text reaches the model
never, while `save_interaction` rewrites them on every session save forever.

**3. The drain buries the triggering turn.** `add_interaction` appends the new
interaction and *then* extends with the queued ones (`:358`, `:383`), producing
`[..., AskOracle, EI1]`. The `AskOracle` that triggered the drain is no longer
last on its branch, so its `step()` — the LLM call site — never runs. The turn
merges rather than being lost, because the buried oracle's rendered prompt
survives in context, but the result is a `tool_result` user turn immediately
followed by a plain-text user turn with no delimiter between them.

**4. Delivered text can never leave the context window.**
`AskOracle.create_from_external_input` (`interaction/ask_oracle.py:61-69`)
builds `Prompt(type="text", text=...)` with no `tool_name`. Every trimming
policy in `render_stack_context` hangs off `tool_call =
interaction.prompt.tool_name` (`interaction/stack.py:247`); with it `None`,
`append_to_context` stays `True` and `reduced` stays `False` (`:221-222`).
Every tool result in Hugin can be elided after its context window. A delivered
message cannot, by construction — it is carried, in full, on every subsequent
turn for the life of the agent.

**5. Delivery ignores branches.** `insert_external_input` constructs
`ExternalInput(stack=self, input=input)` with `branch` defaulting to `None`
(`interaction/interaction.py:43`). An agent doing branched exploration
(`examples/branching/`) cannot receive a message on a named branch.

## Outcome

- [x] A message delivered to an agent is still delivered after the session has
      been saved and reloaded.
- [x] Delivering three messages before an agent's next turn results in all
      three reaching the model, in one turn.
- [x] The interaction that triggers a drain still takes its turn; no interaction
      is left appended-but-never-stepped.
- [x] Delivered message text participates in the context policy: after its
      configured window it is reduced or elided like any tool result, and the
      default window is finite. A test asserts rendered context does not grow
      without bound as messages accumulate.
- [x] A message can be delivered to a named branch and is observed by that
      branch.
- [x] Remote or externally-sourced text is rendered fenced from surrounding
      content, with its provenance visible.
- [x] The mechanism has direct test coverage, which it has none of today.

## Notes

- Task 038 depends on this. Its plan builds cross-machine messaging on this
  exact path, and states that every one of these defects would otherwise show
  up as a messaging bug rather than a stack bug.
- Defect 4 interacts with the artifact and `dream` machinery: a bounded context
  policy for messages raises the question of where message history goes when it
  leaves the window. Out of scope here; noted in 038.
- Defect 3's fix should settle drain *ordering*, not only persistence — those
  are separable and the ordering one is the more visible.

## Review

Three-role panel (correctness/security, compatibility/testing, maintainability/performance): the plain-text completion delivery gap was reproduced and fixed in dca0e08; follow-up independent review passed. No remaining blocking findings. Provider-adapter end-to-end coverage was suggested as a nonblocking extension.

## Conversation

### note · codex/task040 · 2026-09-28T10:44:00Z

Claimed to implement, test, and panel-review a separate PR; merge awaits owner review.

## Plan

- Persist the pending inbox inline in stack state, preserving message IDs,
  branch, source label, and context window. Keep the existing string-only
  delivery calls compatible and guard concurrent enqueue/drain operations.
- Drain a branch's complete batch at its pending AskOracle execution boundary,
  attaching durable message records to that oracle rather than burying its
  original prompt or tool result. Retain the batch on failure for retry.
- Wake completed branches with a message turn while leaving child, tool, and
  human waits intact. Release the stack step lock even when a provider fails.
- Render external text as fenced JSON data with visible provenance, separately
  from trusted task/tool content. Elide it after a configurable positive window
  of model turns (default five); retain the durable history on disk.
- Add direct regressions for disk reload, ordered fan-in, trigger preservation,
  retries, branch targeting, wait safety, bounded context, and hostile fence
  content. Run focused and full tests, pre-commit checks, and independent review.

## Verification

- Added 20 direct delivery regressions; focused delivery, context-window,
  storage, and waiting suites: 105 passed.
- `TMPDIR=/private/tmp uv run pytest -x -q`: 1781 passed, 53 skipped.
  Local socket tests require the approved unsandboxed test run; the first
  sandboxed attempt stopped at an existing localhost bind restriction.
- Changed-file pre-commit hooks all pass. Required all-file hooks were run;
  remaining failures are existing docstring lint findings, the untyped
  `scripts/sync_packaged_examples.py:51`, and four existing secret-test fixtures.
  Restored the unrelated detect-secrets baseline rewrite.
- No unresolved CLAUDE markers in touched files. Independent review and PR
  integration remain with the coordinating agent.
- Inbox persistence follows normal completed session saves; the existing
  multi-file storage format does not provide crash-atomic session transactions.

## Conversation

### note · codex/task040 · 2026-09-28T11:22:54Z

Implemented durable ordered delivery, branch-aware wakeup, retry retention, and
fenced external context with a default five-turn window; full tests and changed-file
hooks pass. Awaiting independent review and PR integration.

### note · codex/task040 · 2026-09-28T11:28:49Z

Independent review found that a plain-text response could stop the session before
its appended TaskResult ran, stranding a message received during the call.
Added a failing real-session regression and made an appended branch successor
count as progress; updated two legacy premature-stop assertions. The follow-up
passes 122 focused stack/wait/delivery tests, 75 agent/session/integration tests,
and the full suite again (1781 passed, 53 skipped).

### note · codex/task040 · 2026-09-28T11:31:02Z

Panel complete; preparing the implementation PR for owner review.

### note · codex/task040 · 2026-09-28T12:48:08Z

Merged https://github.com/arnovich/gimle-hugin/pull/141 after required CI passed. Closed after verifying the merged implementation matches the tested integration.
