---
github_issue: null
title: "Dreaming: offline memory consolidation that feeds learnings back into prompts"
state: OPEN
labels: [enhancement, memory, prompts, agents]
author: erikarne
created: 2026-05-21
---

# Dreaming: offline memory consolidation → self-improving prompts

## The idea

Borrow the "dreaming" / sleep-consolidation framing: episodic memories (raw
experiences) are replayed offline and distilled into semantic memories (general
knowledge), which then become priors that shape future behaviour.

Mapped onto Hugin:

- **Episodic memory** = today's artifacts (`Text`/`Code`/… saved via
  `save_insight`, `src/gimle/hugin/tools/builtins/save_insight.py`).
- **Dreaming** = an offline pass that reads many artifacts, finds patterns
  across sessions, and emits a new kind of artifact: a **`Learning`**.
- **The self-improving loop** = each `Learning` is scoped to the config/task
  that produced its source material, and is injected into that config/task's
  prompt on the next run. The agent that generated the experiences gets better
  at the thing it was doing — without retraining, just by consolidating its own
  memory.

This is deliberately a *closed loop*: agent runs → artifacts → dream →
learnings → richer prompts → better runs → better artifacts.

## Design decisions (locked)

These were decided up front; the rest of the task builds on them:

1. **Injection = render-time, non-destructive.** Dreaming writes `Learning`
   artifacts to a separate store; the renderer injects the relevant ones into a
   `{{ learnings }}` block at render time. The base templates are never
   mutated. Auditable (see `HUGIN_CAPTURE_RENDERED_PROMPTS`), trivially
   reversible.
2. **Trigger = manual CLI command.** A `hugin dream` subcommand runs the
   consolidation over a storage path on demand. No daemon, no hook into the hot
   path. Easy to test; can be wired into a post-session hook or cron later.
3. **Scope = per-config *and* per-task.** A `Learning` carries the config name
   and (optionally) the task name it was distilled from. A learning for config
   `research_assistant` improves `research_assistant`; a learning for task
   `analyze_sales` improves that task specifically.
4. **Autonomy = fully autonomous (no human gate).** Learnings a dream produces
   take effect on the next run with no approval step. **Consequence:** the
   mechanical guardrails below are load-bearing, not polish — with no human in
   the loop, provenance + budget + self-rating are the *only* thing preventing
   feedback collapse. "Autonomous" means "no human gate", **not** "unbounded
   injection".

## What already exists (reuse, don't rebuild)

- **Global, queryable artifact store.** Artifacts are global across all
  sessions; `ArtifactQueryEngine`
  (`src/gimle/hugin/artifacts/query_engine.py`) does keyword search +
  rating-weighted ranking. Builtin tools `query_artifacts` /
  `get_artifact_content` already let an agent read prior memory.
- **Feedback / rating model.** `ArtifactFeedback`
  (`src/gimle/hugin/artifacts/feedback.py`, 1–5 stars, `source` =
  `agent`|`human`) already exists and the query engine boosts by it
  (`_get_rating_boost`, query_engine.py:383). This is the quality signal the
  dream uses to pick what to consolidate and what to inject.
- **A clean prompt-injection seam.** `PromptRenderer.render_prompt`
  (`src/gimle/hugin/llm/prompt/renderer.py:105`) merges a `template_inputs`
  dict before `render_jinja_recursive`. Adding one key (`learnings`) there is
  the entire injection mechanism. `render_system_prompt` (renderer.py:165) and
  `render_task_prompt` (renderer.py:146) are the call sites.
- **Sub-agent execution.** The dream worker can *be* a Hugin agent (config +
  task + the query/save tools). No new execution engine; reuse `Session.run`
  (`src/gimle/hugin/agent/session.py`) / `AgentCall`
  (`src/gimle/hugin/interaction/agent_call.py`).
- **Prompt audit.** `HUGIN_CAPTURE_RENDERED_PROMPTS=1` records the rendered
  system/user prompt per `OracleResponse` — so injected learnings are visible
  in `hugin monitor`/`interactive` and persisted JSON. This is the
  reproducibility net for an autonomous loop; use it to verify injection.

## What needs building

1. **`Learning` artifact type.** New registered subclass
   (`@Artifact.register("Learning")`, alongside `text.py`/`code.py` in
   `src/gimle/hugin/artifacts/`). Fields beyond the base:
   - `content: str` — the lesson, in prose ready to drop into a prompt.
   - `scope_config: Optional[str]` / `scope_task: Optional[str]` — who it
     applies to (decision 3).
   - `source_artifact_ids: List[str]` — the episodic memories it was distilled
     from (evidence / traceability).
   - `confidence: float` — the dream's self-assessed confidence.
   - `derived_from: str = "dream"` — provenance marker (see guardrail 7).

2. **Provenance: recover config/task without changing the write path.** The
   links already exist — they're stored as *forward* references, so no
   write-time stamping is strictly needed:
   - an artifact persists its interaction UUID
     (`Artifact.to_dict`, artifacts/artifact.py:64);
   - each agent record persists its config and its ordered interaction UUIDs
     (`Agent.to_dict`, agent/agent.py:376), and the task identity lives in the
     agent's `TaskDefinition` interaction(s).

   The catch: a persisted *interaction* has **no** back-pointer to its agent —
   `Interaction.to_dict` drops `stack` (interaction/interaction.py:99) — so you
   can't walk artifact → interaction → agent in isolation. Two ways around it,
   both fine:
   - **(preferred) Drive the dream forward from agents.** Iterate
     `storage.list_agents()`; for each you're holding its config (+
     `_config_history`) and task(s) while you walk its interactions and collect
     their artifacts — provenance falls out for free, already grouped by
     config/task. No index needed.
   - **Or build an inverse index** `interaction_uuid → (config, task)` from the
     same agent scan, then join the global artifact list to it.

   Either way this works on the **existing artifact corpus** (retroactive),
   which matters a lot: a consolidation feature that could only see memories
   created after it shipped would be nearly useless. The dream is an offline
   batch that already scans storage, so an agent scan (cache per run) is in
   budget.

   Caveats to handle:
   - **State-machine agents.** `agent.config` is the *final* config; an agent
     that switched configs mid-run (config_state_machine) produced artifacts
     under different configs. Correct per-interaction attribution needs
     `agent._config_history` (interaction_id → state), which is persisted
     (agent/agent.py:390).
   - **Multiple tasks per stack.** Sub-agent reuse via `AgentCall` can append
     several `TaskDefinition`s to one stack; attribute an artifact to the most
     recent `TaskDefinition` at/before its position.
   - **Loading cost.** `load_artifact(stack=None)` skips interaction hydration
     and `load_interaction` requires a stack — resolve via lightweight reads of
     the agent/interaction records, not full `from_dict` hydration.

   *Injection selection is separate* and does not use this: `Learning`
   artifacts carry their own `scope_config`/`scope_task` (item 1), stamped when
   the dream creates them.

   *Optional later enhancement:* also stamp `config`/`task` onto artifacts at
   write time in `save_insight` (from `stack.agent.config.name` + the stack's
   `TaskDefinition`). That gives O(1) reads and captures the exactly-active
   config for state-machine agents — and the forward pass above can backfill it
   onto historical artifacts. Not required for v1.

3. **Learning selector.** A small `LearningStore`/selector that, given a config
   name (+ optional task name), returns the applicable `Learning` artifacts.
   The keyword `ArtifactQueryEngine` filters by *type* and searches *content*,
   not by metadata predicates — so either (a) a dedicated scan over
   `storage.list_artifacts()` filtering `Learning` by `scope_config`, or (b)
   extend the query engine with a metadata filter. Sort by (rating desc,
   recency desc); apply the budget from guardrail 7.

4. **Render-time injection.** Fetch the selected learnings for the current
   agent's config/task and inject them as `learnings` into `template_inputs`
   inside `render_system_prompt` / `render_task_prompt` (renderer.py). Templates
   opt in by referencing `{{ learnings }}`; a config/task that never mentions it
   is unaffected. **Caveat:** injected text re-enters `render_jinja_recursive`,
   so a learning containing literal `{{ … }}` would be (mis)rendered — treat
   injected learnings as literal (escape, or render-once). This is exactly the
   escape problem tracked in task 020; coordinate.

5. **The dream worker (a Hugin agent).** A config + task that:
   - reads candidate episodic artifacts (`query_artifacts` /
     `get_artifact_content`), grouped by `scope_config`/`scope_task`;
   - synthesises cross-session patterns into `Learning` artifacts (new
     `save_learning` tool, mirroring `save_insight`);
   - self-rates each learning via `ArtifactFeedback` (`source="agent"`).
   Lives under a new package dir (e.g. `apps/dreamer/` or
   `src/gimle/hugin/dreaming/`), following the existing
   configs/tasks/templates/tools layout.

6. **`hugin dream` CLI subcommand.** Sibling of `run`/`monitor`/`interactive`.
   Loads a storage path, builds the dream worker's environment/session, runs it
   (bounded by `--max-steps`), persists the resulting `Learning` artifacts.
   Flags: `--storage-path`, optional `--config`/`--task` to consolidate a
   single scope, `--dry-run` (produce learnings but don't persist).

7. **Guardrails against feedback collapse (load-bearing — see decision 4).**
   - **No dreams-eating-dreams.** The dream's *input* query must exclude
     `Learning` artifacts (`derived_from == "dream"`), or heavily down-weight
     them, so consolidation runs on episodic memory, not on its own output.
   - **Injection budget.** Cap injected learnings per render (top-N and/or a
     char/token budget) so prompts can't grow unboundedly across cycles.
   - **Rating-driven selection.** Prefer high-rated learnings; let low-rated
     ones decay out of selection. (Autonomy removed the *human* gate, not the
     *quality* gate.)

## Open questions

- **Dedup / superseding:** when a new dream restates an existing learning, do we
  merge, version, or supersede (and how does that interact with ratings)?
- **Cold start:** with no learnings, `{{ learnings }}` renders empty — confirm
  that's clean for every opt-in template (ties into task 020's `Undefined`
  policy).
- **Multi-app scope:** decisions cover per-config/per-task; do app/world-level
  learnings (e.g. `the_hugins`) want a coarser scope key later?
- **Cost shape:** a naive dream re-reads the whole artifact store; consider
  incremental ("only artifacts since last dream") via a watermark.

## Success criteria

- [ ] `Learning` artifact type exists, serialises/deserialises, and is
      registered.
- [ ] New artifacts (insights + learnings) record producing config + task;
      verified by a test that reads the provenance back from storage.
- [ ] `hugin dream --storage-path …` runs end-to-end, reads episodic artifacts,
      and writes scoped `Learning` artifacts.
- [ ] A config/task whose template references `{{ learnings }}` receives its
      scoped learnings at render time; one that doesn't is byte-for-byte
      unchanged. Verified via `HUGIN_CAPTURE_RENDERED_PROMPTS`.
- [ ] The dream's input excludes prior `Learning` artifacts (no
      dreams-eating-dreams), with a test.
- [ ] Injection respects a budget (top-N / char cap), with a test.
- [ ] An end-to-end loop test: run agent → dream → re-render shows the learning
      present in the prompt.
- [ ] Existing artifact / prompt-rendering tests still pass.

## Context

- Builds on the artifact feedback/rating work in
  `tasks/closed/001-artifact-feedback.md` (the quality signal the loop relies on).
- Natural extension of `tasks/open/003-long-term-memory.md` (richer memory
  types + retrieval) — `Learning` is the consolidated/semantic memory type that
  task gestures at.
- Depends on / coordinates with `tasks/open/020-jinja-renderer-escape-and-undefined.md`
  for safely injecting literal text into prompts.
- Uses the rendered-prompt capture from
  `tasks/closed/018-persist-rendered-prompt` as the audit mechanism.
