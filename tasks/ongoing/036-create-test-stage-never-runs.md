---
title: "`hugin create`'s test stage never runs — the child agent is never stepped"
state: ongoing
claimed_by: codex/task036
claimed_at: 2026-09-28T09:17:51Z
branch: task/036_create_test_stage
labels: [bug, agent-builder, cli]
priority: high
---

# `hugin create`'s test stage never runs

## Context

The fourth stage of a build (`test_agent`) launches a child agent and then
waits for it forever. The child is never stepped, so the parent spins on
`Waiting` until it exhausts `--max-steps`, and the build reports
`capped_after_write` — a message that blames the build's size for what is a
one-line wiring difference between two CLI entry points.

## Evidence

Observed on a clean build (2026-08-24, builder agent `489e4ba8`, storage
`./storage/agent_builder`):

- Stages 1-3 completed normally in ~120s; the agent was written and validates
  with 0 errors and 0 warnings.
- Stage 4 called `test_agent`, which returned an `AgentCall`. The child agent
  `c9437364` (`test_release_notes_writer`) was created with **exactly one
  interaction** — its `TaskDefinition` — and never advanced.
- The parent went from ~75 interactions to the 200-step cap in roughly one
  second of spinning (`AgentCall` at 14:25:02.89, run over at 14:25:03), because
  a `Waiting` step costs no model call.
- The CLI printed *"reached maximum steps (200). The agent was written; the test
  run after it did not finish. Try it yourself, or re-run with --max-steps."*
  Raising `--max-steps` cannot help: the extra steps are spent spinning.

## Cause

Four pieces that are individually correct:

- `cli/create_agent.py:943` drives the loop with `step_fn=agent.step` — the
  **parent** agent only.
- `tools/test_agent.py` returns an `AgentCall`, which is the documented way for
  a tool to spawn a child (`AGENTS.md`, "Launching Sub-Agents from Tools").
- `interaction/waiting.py:50-67` — a `Waiting` whose previous interaction is an
  `AgentCall` returns `True` indefinitely, to keep the branch alive while the
  child runs.
- `interaction/task_result.py:136-143` — the parent is resumed by the **child's**
  `TaskResult.step()`, which pushes an `AgentResult` onto `task_def.caller.stack`.
  Note `caller` is a property that resolves through
  `self.stack.agent.session.get_agent(self.caller_id)`
  (`interaction/task_definition.py:34-43`), and the push is guarded by a bare
  `if task_def.caller:` with **no else branch** — so a caller that cannot be
  resolved is not an error, it is silence.

So the parent's resume depends on the child being stepped, and nothing steps it.
`agent.step()` has no path into another agent; `Session.step()`
(`agent/session.py:158-179`) is the one that iterates every agent in the session.

`hugin run` gets this right — `cli/run_agent.py:603` and `:1055` both use
`step_fn=session.step`. The generated agent from the same build ran correctly
end to end under `hugin run`.

## Impact

- The post-write test has never actually executed a generated agent. Its
  coverage today is `tests/test_agent_builder_test_agent.py`, which asserts the
  tool *returns* an `AgentCall` — true, and not the same thing as the child
  running.
- Every build that reaches stage 4 burns its remaining step budget and reports
  `capped_after_write`, so that outcome carries no signal.
- The advice in the message ("re-run with `--max-steps`") sends users to spend
  more money on the same outcome.

`hugin improve` shares the `step_fn=agent.step` shape (`cli/improve_agent.py:371`)
but is not affected in practice: its task's tool list
(`tasks/improve_agent.yaml:17-25`) contains nothing that returns an `AgentCall`.
Worth fixing anyway so the two entry points cannot drift apart again.

## Tasks

- [ ] Switch `cli/create_agent.py` to `step_fn=session.step` and confirm stage 4
      runs the generated agent to a `TaskResult`.
- [ ] Decide the step budget. `step_cap_outcome`'s docstring already assumes the
      child's steps count against the builder's allowance; once they actually do,
      check whether the default 200 still leaves room for a test run, or whether
      the test should get its own budget.
- [ ] Re-check what `capped_after_write` means once the test really runs, and
      reword the note if it no longer fits.
- [ ] Do the same for `cli/improve_agent.py:371`, or document why it differs.
- [ ] Consider a guard so a `Waiting` that makes no progress cannot silently
      consume a step budget — spinning on a child that is not being stepped
      should be loud, not slow.

## Outcome

- [ ] A build with default flags executes the generated agent in stage 4 and
      reports its result.
- [ ] A test that drives a real build stage containing an `AgentCall` and asserts
      the child reached a `TaskResult` — not merely that an `AgentCall` was
      returned.
- [ ] A build that hits the step cap does so for a reason the message states
      accurately.

## Plan

- Drive `create` and `improve` through `Session.step`, matching `run` so
  dynamically launched children advance and return their results.
- Add a scripted-model CLI regression that exercises the real build, review,
  write, and test stages, checks the child's `TaskResult` and the parent's
  receipt of it, and completes within the default 200 session steps.
- Cover a genuinely capped child and an exhausted budget after the child has
  finished. Describe the cap as unfinished session work, since file creation
  alone cannot identify which stage remains unfinished.
- Keep one shared 200-session-step allowance; do not create an independent
  child budget. Each step advances all agents. General idle-loop detection,
  storage write suppression, and LLM-call budgeting remain task 041.
- Exercise `improve` through its real CLI loop with a scripted child as a
  regression against future delegation. Run focused tests, the full suite,
  pre-commit checks, and a correctness/test/maintainability review panel.
