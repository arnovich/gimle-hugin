---
title: External input delivery loses messages, buries a turn, and never leaves context
state: open
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

- [ ] A message delivered to an agent is still delivered after the session has
      been saved and reloaded.
- [ ] Delivering three messages before an agent's next turn results in all
      three reaching the model, in one turn.
- [ ] The interaction that triggers a drain still takes its turn; no interaction
      is left appended-but-never-stepped.
- [ ] Delivered message text participates in the context policy: after its
      configured window it is reduced or elided like any tool result, and the
      default window is finite. A test asserts rendered context does not grow
      without bound as messages accumulate.
- [ ] A message can be delivered to a named branch and is observed by that
      branch.
- [ ] Remote or externally-sourced text is rendered fenced from surrounding
      content, with its provenance visible.
- [ ] The mechanism has direct test coverage, which it has none of today.

## Notes

- Task 038 depends on this. Its plan builds cross-machine messaging on this
  exact path, and states that every one of these defects would otherwise show
  up as a messaging bug rather than a stack bug.
- Defect 4 interacts with the artifact and `dream` machinery: a bounded context
  policy for messages raises the question of where message history goes when it
  leaves the window. Out of scope here; noted in 038.
- Defect 3's fix should settle drain *ordering*, not only persistence — those
  are separable and the ordering one is the more visible.
