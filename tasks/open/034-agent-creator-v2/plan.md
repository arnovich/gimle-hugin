---
title: Agent Creator v2 — Implementation Plan
state: OPEN
---

# Agent Creator v2 — Implementation Plan

Incremental PRs, each independently mergeable, each leaving `main` working.
Branch per PR off `main`, snake_case, `task/` prefix. See `spec.md` for design.

## Status — start here

**Last updated: 2026-08-21. Phases 1 and 1.5 complete. Phase 2 partly done and
partly abandoned; Phase 4's schema work pulled forward because the eval said so.**

| PR | What | State |
|---|---|---|
| #82 | 1.1 Safe writes, path confinement | merged |
| #83 | 1.2 Examples wired in | merged |
| #85 | 1.3 Static validator, `hugin validate`, CI gate | merged |
| #87 | 1.4 The gate, in code | merged |
| #97 | 1.5 + 1.4b + 1.6 + 1.7 — rest of Phase 1 | merged |
| #98 | 1.8 + 1.9 `hugin analyze` | merged |
| #100 | 2.5 golden-set eval harness (`tests/evals/`) | merged |
| #101 | Jinja recursive-render crash | merged |
| #102 | eval: outages are not generation failures | merged |
| #103 | 4.1 multi-stage agents (`task_sequence` et al) | merged |
| #104 | writing and finishing made indivisible | reverted (#106) |
| #107 | chained-stage history rendering + #104 re-landed | merged |
| #108 | 3.1 edit an existing agent | merged |
| #109 | 5.1 propose changes from traces + read-loop fix | open |

### What the eval changed about the plan

The golden-set harness went in to gate a prompt change (PR 2.2). It has since
redirected the work four times, and **not once toward the prompt**:

| Expected | Found instead |
|---|---|
| The prompt lacks schema detail | A framework Jinja crash was killing builds |
| — | The harness scored provider outages as generation failures |
| — | `generate_task` had no field for a chain, so pipelines were impossible |
| — | The builder discarded validated agents by finishing without writing |
| — | A later stage retroactively corrupted an earlier stage's rendered turn |

**PR 2.2 remains unbuilt, unmeasured, and the least-supported item on the list.**
A draft (schema tables inlined into `builder_system.yaml`, no packaging) is
stashed on `task/034_schema_in_prompt` if it is ever wanted. Do not build
PR 2.1 to support it without re-deciding first — see below.

### Pick up here

**Variance is established. Read this before quoting any eval number.**

Three identical runs on `d0ca367` (2026-08-21), same commit, same models,
temperature 0. Any difference between them is noise by construction:

| Metric | a, b, c | Spread | Use it? |
|---|---|---|---|
| `validates` | 15, 15, 15 | **0** | yes — a one-case move is signal |
| `built` | 15, 15, 15 | **0** | yes |
| `meets_task_expectation` | 15, 15, 15 | **0** | yes |
| `produced_a_pipeline` | 2, 2, 2 | **0** | yes |
| `meets_tool_expectation` | 10, 13, 12 | **3** | no — noise-dominated |
| `output_tokens` | 55027, 57896, 52616 | **5281** | no — noise-dominated |

All fifteen cases passed in all three runs, individually stable.

This **falsifies the note that used to sit here**, which assumed a
`0.933 → 0.867` move was probably noise. For `validates` it is not: the metric
is deterministic across runs, so a single case changing is evidence. The
surprise runs the other way — the metrics that look like hard numbers (tokens)
are the unreliable ones, because they aggregate a model's word choices.

**A correction this forced.** #109 reported four improvements from the
read-loop fix. Two do not survive: `meets_tool_expectation: 10 -> 13` is
exactly the observed spread on identical code, and `output_tokens: -2944` is
well inside a 5281 range. Both were noise read as signal. What survives is the
`validates` move (14/15 -> 15/15) and `refund_approver` going from a 168s
step-cap failure to a 68s pass — mechanism-first, and on a zero-spread metric.

Rule: gate on `validates` / `built` / `meets_task_expectation` /
`produced_a_pipeline`. Never claim a win from `meets_tool_expectation` or
token counts without several runs.

Then, in order of evidence:

1. **~~The builder loops in stage 1.~~ Cause found and fixed in #109.**
   `read_generated_file` kept only its 3 most recent results in context, so a
   task reasoning about five files evicted the oldest read on every new one.
   The model then re-read a file it could no longer see, evicting another —
   rational from inside the window, and unbounded. The window now holds a whole
   small agent, plus a per-file repeat guard as a backstop.

   **It moved the eval, and the predicted case is the one that moved.**
   15/15 from 14/15, and `refund_approver` -- the case that hit the loop --
   went from 168s and a step-cap failure to a 68s pass. `validates` has zero
   spread across repeat runs, so that move is signal. The tool-expectation and
   token "improvements" reported alongside it were noise and are withdrawn --
   see the variance table above.
2. **`preview_files` returns 24k chars and `read_example` 12k** — measured from
   a real builder trace. The context-window caps added in #83 only started
   working after the `stack.py` membership fix, so capping `preview_files` is a
   small change with a measurable token effect.
3. **The builder's four-stage workflow is fragile.** #104/#107 removed one way
   to lose a valid agent; an abnormal end (max steps) still loses one to
   `.rejected/` — and that is exactly what `refund_approver` hit, with a
   *valid* agent (0 errors, 0 warnings) thrown away for want of a finish.

### The #104 revert, and what it actually was

#104 was reverted after scoring 1/15. The diagnosis recorded at the time — "the
narrowed finalize tool list orphaned `tool_use` blocks" — was directionally
right but had the wrong mechanism, and rebuilding on it ("keep a superset of
the tools") did **not** fix the failure.

The real cause was a framework bug: `OracleResponse.tool_call_id` resolved the
called tool against the tools visible *now*, not those in force when the call
was made. Since a chain re-renders earlier stages on the same stack, dropping a
`respond_with_text` tool (`finish`) from a later stage's list re-rendered a
finished turn as an unanswerable `tool_use`, and the provider rejected the whole
request. Fixed in #107 by resolving as of the interaction.

Two lessons worth keeping:

- **Unit tests cannot see this class of bug.** All eleven tests on #104 passed
  while it failed 100% of builds; it needs two chained stages with differing
  tool lists to appear. The eval is the only thing that catches it — run it
  before merging a builder or interaction change, not after.
- **A persisted session replays offline for free.** `render_stack_context` is
  pure, so loading a stored session and checking every `tool_use` has a
  `tool_result` reproduces the provider's 400 exactly, with no API spend. That
  is how #107 was diagnosed and how it was confirmed pre-existing on `main`.

### Measurement notes

- `expect_tools` was written when the builder could only produce flat agents,
  and scored a correct three-stage agent as a regression. Tools and tasks are
  counted separately now (#103). If a change alters agent *shape*, check the
  expectations still mean what they meant.
- `self_reported_success_rate` is the agent's own verdict and must never be an
  optimisation target — see spec §5.1c for the router-outcome distinction.

### Things to decide before Phase 2, not during it

- **PR 2.1 (move reference docs into the package) may not be worth doing.** It
  was the panel's most-criticised item: all the cost, no benefit until 2.2, and
  it degrades the Claude Code plugin in between. Now that examples are wired in
  and read at build time, re-ask whether the packaged knowledge base earns its
  keep at all.
- **Move PR 2.5 (golden-set eval harness) ahead of PR 2.2.** Nothing built so
  far measures the *model*; every test pins mechanics. 2.2 changes the builder's
  prompt, and without the harness there is no way to tell whether it helped.

### Known issues not caused by this task

- `pre-commit run --all-files` is red on `main`: `tests/test_dream_pruning.py`
  fails D102/D103 (from #96). The pre-commit hook carries `flake8-docstrings`
  while CI's `flake8 src examples tests apps` does not, so CI is green and the
  divergence is invisible there. Anyone running pre-commit locally hits a
  failure they did not cause.
- The `mypy` pre-commit hook fails with an internal error on
  `openai/_client.py`. Long-standing, unrelated.

### Working notes

- **PRs here are squash-merged.** After one merges, the branches above it go
  DIRTY because GitHub retargets them and their commits are not on `main`.
  Restack with `git rebase --onto origin/main <old-base-tip> <branch>` — a plain
  rebase replays commits the squash already contains and conflicts.
- A clean rebase does not mean a correct one. #87's rebase produced no conflicts
  and 19 test failures: the writer's fixtures were stubs that the newly added
  gate refused. Run the suite after every restack.

## Sequencing rationale

Revised after a five-judge panel review. Four changes to the original order:

1. **Wiring `list_examples`/`read_example` moves to PR 1.2.** It is two lines of
   YAML against tools that already work and already scan the 21 real examples.
   It was buried as bullet 1 of a six-item grab-bag, scheduled behind a four-PR
   knowledge migration that largely duplicates its benefit.
2. **`hugin analyze` moves to Phase 1.5.** Read-only, zero LLM tokens, depends on
   nothing from Phases 2-4, works on hand-written agents. It was the fifth phase
   of a five-phase plan whose own dependency graph guaranteed it never shipped —
   and it surfaces the storage-API problem (spec §5.1) in week one rather than
   month four.
3. **Phase 4 (edit) now precedes Phase 3 (depth).** The real user loop is
   generate → 80% right → change one thing. A pipeline can be hand-written in ten
   minutes by copying `examples/task_sequences`; a builder that can *emit*
   pipelines but not *edit* them makes every pipeline mistake cost a full rebuild
   at pipeline prices. PR 4.1 was already a stated prerequisite for Phase 5.
4. **PRs that ship a tool with no caller are merged with their caller.** The
   original 1.4/3.1/4.1 each landed dead code — reproducing the exact defect this
   task exists to fix.

**Do not itemise Phases 3-5 further until Phase 1 has actually run.** This repo's
own proven method is task 023's: a phase spine, then standalone tasks filed *as
each predecessor ships* — 029 was deliberately left unbuilt with the note "a
design task, to be written after watching real agents use Phases 1-2 — do not
build it blind." The checkboxes below get refined at each phase boundary.

**Dissent, recorded.** One judge argued to cut this to three PRs and move
Phases 2-5 to a roadmap README, on the evidence that `apps/agent_builder/`,
`cli/create_agent.py` and `skills/hugin-agent-creator/` have not been touched
since January 2026 and task 013 has sat open for six months, while the
bash-sandbox series shipped ~19 PRs in six days. That evidence is real and worth
re-reading before starting Phase 2. All five phases are kept in scope by explicit
decision; the mitigation is the de-itemisation above and the fact that Phases 1
and 1.5 stand alone if the rest stalls.

---

## Phase 1 — Correctness gate

### PR 1.1 — Safe writes and path confinement `task/034_write_files_safety`
The `rmtree` at `write_agent_files.py:57` is a data-loss bug and the unvalidated
`output_dir / file_path` join at `:77-79` is an arbitrary-file-write. They ship
together, first, alone.

- [x] Changed-only writes: refuse unknown or user-modified conflicts; track
      session-written files per output path and content hash so only unchanged,
      builder-owned files can be updated or removed when superseded. Report
      `{written, unchanged, removed, preserved}` and support `dry_run`. No
      `overwrite` escape hatch and no `.bak` siblings (spec §1.4 explains why
      the backup design was dropped)
- [x] Path confinement + name validation (spec §1.1 checks 1-2) in
      `tools/agent_paths.py`, mirroring `sandbox.local.LocalSandbox._confine`
      plus descriptor-relative, atomic writes that refuse symlinks at every hop
- [x] Constrain `output_path`: refuse `/`, `$HOME`, repo root, paths containing
      `.git`, symlinked components
- [x] Unify the run command: `agent_paths.run_command()` now feeds both the
      generated README and `cli/create_agent.py`'s success screen
- [x] `tests/test_write_agent_files_safety.py` — 58 tests, including `../`,
      absolute keys, symlink escape, and the preserve/no-op/update cases
- [x] Docs pass done in the Phase 1 completion PR: the run commands already
      matched, and the stale model table now points at the registry instead

### PR 1.2 — Examples wired in `task/034_wire_examples`
Two lines of YAML plus three of prompt. Highest value-per-line in the document.

- [x] `list_examples`, `read_example` into `configs/agent_builder.yaml`, with
      `read_example` confined to a single name inside `examples/` (unconfined,
      wiring it in made an arbitrary-directory reader live)
- [x] Study step in `builder_system.yaml` **and** in `tasks/build_agent.yaml` —
      the task prompt is a concrete numbered recipe that previously began at
      `generate_config`, and a concrete recipe wins over a system-prompt
      suggestion, so the system template alone would have left it unused
- [x] `include_only_in_context_window` + small `context_window` on both, so they
      do not accumulate in a never-truncated stack
- [x] `tests/test_agent_builder_examples_wired.py` — 12 tests pinning the
      wiring, the caps, the prompt ordering, and that both tools still work
- [ ] **Deferred to PR 2.4:** `builtins.read_file` / `builtins.list_files`.
      They have no caller until the `reference_files` parameter exists, and
      2.4 is where they get the untrusted-input wrapping. Adding them here
      would land exactly the unreachable-capability problem this PR fixes.

### PR 1.3 — `validate_agent` (static checks only) `task/034_validate_agent`
- [x] Checks: path keys, reserved names, structure, reference resolution
      (using task 019's shared identifier-only heuristic), Jinja binding **as
      warnings**, AST-based tool contract
- [x] Compact `{ok, errors, warnings, observed_imports, summary}` payload
- [x] `check_imports` accepted but **defaulting False** and not implemented —
      it executes generated code, so it lands with its hardening (spec §1.5)
- [x] `tests/test_validate_agent.py` — 88 tests, one broken fixture per check
- [x] **Acceptance gate:** 26/26 shipped agents clean, parametrized in pytest
      *and* run as a `hugin validate -r` step in `.github/workflows/ci.yml`
- [x] `hugin validate` CLI pulled forward from PR 1.4, so the validator ships
      with a caller instead of sitting unreachable until the next PR

Three assumptions the acceptance gate falsified, each fixed here:

- **Tool files are not 1:1 with definitions.** `implementation_path` is
  `dotted.module:function` and several definitions routinely share one module
  (`examples/parallel_agents` puts `increment` and `get_count` in
  `counter_tools.py`). A `.py` with no `.yaml` is a normal helper module.
- **`parameters` has two shapes.** `apps/rap_machine` uses a JSON-Schema
  object with the real parameters under `properties`.
- **The verdict must not read `Tool.registry`.** It is a mutable
  process-global that accumulates every loaded agent's tools and is reset by
  test fixtures, which made the same agent validate differently depending on
  what else had run — 32 suite failures that passed in isolation. Builtin
  names are now parsed from the builtins source. Pinned by
  `TestVerdictIsOrderIndependent`.

Also: `observed_imports` filters modules that ship with the agent
(`apps/the_hugins/world`), which would otherwise have become a nonexistent
entry in PR 1.7's `requirements.txt`.

### PR 1.4 — The gate, in code `task/034_validation_gate`
- [x] `write_agent_files` calls the validator itself and refuses unless `ok`.
      No bypass parameter exists at all — not on the function, not in the tool
      YAML — so there is nothing for the model to reach for (spec §1.0)
- [x] `next_tool` chaining `validate_agent → write_agent_files` when the
      payload is clean, so "validate, then write anyway" is not expressible
- [x] Attempt counter in `env_vars` via `validate_with_state`
- [x] Capability-shrink check: tools, config tool lists and task parameters may
      not shrink across a repair unless a previous error named the removed item.
      Enforced at the **write gate**, not only in the validator tool — otherwise
      the model could skip validation and write a payload that passes precisely
      *because* the broken tool was deleted
- [x] Failure path: `dump_rejected` writes to `<output>.rejected/` with a
      `VALIDATION_REPORT.md`, wired into all three CLI exits plus a new one for
      "builder finished but wrote nothing" (spec §1.2c)
- [x] Strip the now-mechanical checks from `templates/reviewer_system.yaml`;
      the reviewer is now told explicitly *not* to re-check them
- [x] Add `validate_agent` to `configs/agent_builder.yaml`
- [x] ~~`hugin validate` subcommand + CI~~ — shipped in PR 1.3
- [x] **Delivered in PR 1.4b:** `read_generated_file(path)` and pre-repair
      snapshot/revert (spec §1.2b). These are about repair *quality* rather
      than the gate, and `read_generated_file` is a prerequisite for Phase 3's
      edit mode, so it lands with the work that needs it rather than sitting
      unused here.

### PR 1.4b — Repair quality `task/034_repair_loop`
- [x] `read_generated_file(path)` so the builder can read one file back instead
      of re-emitting a whole tool from a one-line error
- [x] Pre-repair snapshot in `env_vars` and revert on regression, so attempt 3
      is not worse-informed than attempt 1 (spec §1.2b)
- [x] Raise `max_tokens` for the builder config — a full tool regeneration in
      one tool-call argument can truncate at the 5000 default
      (`llm/models/anthropic.py:21`)
- [ ] **Deferred:** raising the builder's `max_tokens`. Models are looked
      up by name from a registry with a fixed ceiling and no config hook,
      so overriding it means threading an option through `chat_completion`
      and every `Model` subclass — a framework change, not a builder fix.
      `read_generated_file` mitigates the same problem from the other end.

### PR 1.5 — Stale-module and registry isolation `task/034_module_isolation`
Without this every repair loop in every later phase re-tests cached code.

- [x] `test_agent` runs in a subprocess
- [x] Generated tool modules loaded via `spec_from_file_location` under
      `<agent>__<tool>`, never a bare top-level name
- [x] `Registry.register(..., replace: bool = False)` raising on collision
- [x] `write_agent_files` stops registering into the live global registry
- [x] `test_agent` takes explicit `config_name`/`task_name`; stops polluting the
      builder's template registry

Notes: `test_agent` is not subprocessed. The defect was stale *code*, not
shared process state, and `AgentCall` deliberately runs children in-process;
invalidating the agent's modules (and its `__pycache__`, since bytecode is
validated on mtime+size and a same-size repair within one second is served
stale) fixes the actual bug without breaking sub-agent semantics.

### PR 1.6 — CLI non-interactive + observability `task/034_cli_noninteractive`
Its own feature, split out of the original six-item PR 1.4.

- [x] Models from `model_registry.py`, not the hardcoded lists at `:167-170`
- [x] `--name`, `--description`, `--model`, `--builder-model`, `--output`,
      `--yes`, `--dry-run`, `--stub-tools`
- [x] Ask what to build *before* four screens of provider/credential selection
- [x] Per-stage progress, elapsed time, step count; token/cost on the success
      screen
- [x] `BUILD_REPORT.md` in the generated directory (spec §1.4)
- [x] End-to-end test of non-interactive `hugin create` with `ScriptedToolModel`

### PR 1.7 — Codegen quality `task/034_generate_tool_fixes`
- [x] Real type hints from the declared schema (`generate_tool.py:87-98`)
- [x] Redacted, truncated traceback in the generated except branch
- [x] `observed_imports` → `requirements.txt` with an import→distribution map;
      missing deps are a **warning that still writes**, and skip `test_agent`
- [x] `--stub-tools` implemented (replacing the dead `full_implementation` at
      `build_agent.yaml:19`, `create_agent.py:281,321`)

---

## Phase 1.5 — Read-only trace analysis

Pulled forward from Phase 5. Zero LLM tokens, no dependency on Phases 2-4.

### PR 1.8 — Storage access for foreign runs `task/034_trace_access`
- [x] Read `storage/agents/<uuid>` JSON + `load_interaction_metadata`, following
      `cli/monitor_agents.py:671,747` — **not** `load_interaction(uuid, stack)`,
      which needs a Stack that does not exist for historic runs (spec §5.1)
- [x] Decide and record: lift `load_interaction_metadata` to the `Storage` ABC,
      or scope this to `LocalStorage` explicitly
- [x] Redactor + normalised error signatures, with a test asserting a seeded
      fake key never reaches the report

### PR 1.9 — `hugin analyze` `task/034_analyze_cli`
- [x] `analyze_traces` over the metrics in spec §5.1, top-N bounded
- [x] `hugin analyze <path> --storage-path <s>` printing the report
- [x] `tests/test_analyze_traces.py` against a synthetic storage dir
- [x] **Then** revise spec §5.1's metric table against one real storage dir
      before anything consumes it

---

Delivered as one PR (`task/034_trace_analysis`), in `src/gimle/hugin/analysis/`:
`redaction.py` (credential masking + error-signature normalisation) and
`traces.py` (reader + metrics), with `hugin analyze` on top.

Decisions recorded while building, each forced by real storage rather than the
spec:

- **Scoped to `LocalStorage`, not lifted to the `Storage` ABC.** The cheap
  reader (`load_interaction_metadata`) exists only there and no second backend
  exists to generalise against. Widening later is smaller than unpicking a
  guessed interface.
- **Tool results are attributed positionally, not by `tool_call_id`.**
  `ToolResult` carries no tool name, and on a real run both its `tool_call_id`
  and the matching `ToolCall`'s were `null`. A result belongs to the most
  recent preceding `ToolCall`.
- **Token counts are available** in `OracleResponse.response`
  (`input_tokens`/`output_tokens`), so cost is reported.
- **`success_rate` is labelled self-reported in the output itself**, because it
  is the measured agent's own `finish_type` and anything optimising it can win
  by declaring success sooner. Small samples are flagged for the same reason.

## Phase 2 — One knowledge base (closes task 013)

Re-read the dissent above before starting. PR 2.1 is the plan's most likely stall
point, and a half-done Phase 2 leaves the plugin degraded and the builder
unchanged.

### PR 2.1 — Knowledge package `task/034_knowledge_package`
- [ ] `src/gimle/hugin/knowledge/{references,templates}/`
- [ ] `skills/hugin-agent-creator/references` keeps a **readable file** —
      symlink, or physical copy plus a byte-identity test. No `python -c`
      indirection (spec §2.1 lists the five breakages)
- [ ] Hatchling `artifacts` already covers `*.md`/`*.yaml` — verify, do not add
      setuptools `package-data`
- [ ] Account for the five starter templates, not just the five reference docs
- [ ] Test: both surfaces resolve the same bytes

### PR 2.2 — Schema into the prompt `task/034_schema_in_prompt`
- [ ] Render the four schema references into `builder_system.yaml` from
      `gimle.hugin.knowledge`; keep the token-efficiency and actual-Python rules
- [ ] `read_reference(topic)` for `patterns.md` only, `topic` restricted to an
      enumerated literal set
- [ ] Derive `validate_agent`'s known-field checks from
      `dataclasses.fields(Config)` / `Task` (spec §2.1b)
- [ ] **Gated on the golden-set harness showing no regression**
- [ ] Record places-to-change-per-`Config`-field, before and after

### PR 2.3 — Example index `task/034_example_search`
- [ ] Derive the index from `examples/`+`apps/`; **keep** a packaged curated set
      as the installed-wheel path — do not delete `FALLBACK_EXAMPLES` blind
- [ ] `search_examples(query)`, bounded by extension, size and file count
- [ ] Test: usable index with `examples/` absent

### PR 2.4 — User reference files `task/034_reference_files`
- [ ] `reference_files` parameter + `--reference-file`, wrapped in a delimited
      untrusted block, size- and count-capped
- [ ] **Closes `tasks/open/013-agent-builder-enhancements.md`** — move to
      `tasks/closed/` in this PR

### PR 2.5 — Golden-set eval harness `task/034_eval_harness`
Ship before 2.2 lands. Nothing else in this plan measures the model.

- [x] 10-20 descriptions spanning the architectures
- [x] Scored run behind `slow`/`integration`: first-pass validation rate,
      post-repair rate, attempts used, architecture match, `test_agent` success,
      steps, tokens, dollars
- [x] Numbers recorded in this task file per PR

---

Shipped as `tests/evals/` (run with `uv run python -m tests.evals.run`), ahead
of PR 2.2 rather than alongside it: 2.2 rewrites the builder's system prompt,
and without a baseline that change is unfalsifiable.

**Not in `src/` and not a `hugin` subcommand.** It measures *our* builder, which
is a maintainer's question, not a user's -- shipping it would put fifteen
hardcoded descriptions and a subprocess driver into every install. The
user-facing commands (`create`, `validate`, `analyze`) are all about the user's
own agent; this is not.

Scoped honestly:

- **`expect_architecture` is recorded but not scored.** Architecture selection
  is PR 4.1 and the builder cannot yet be asked for a shape. `has_task_sequence`
  is a structural proxy in the meantime.
- **Cost is reported in tokens, not currency.** Hugin records what the SDK
  reported; real billing after routing and fallback is the router's to know
  (spec §5.1c).
- Scoring reuses `validate_files` and `analyze_traces` rather than counting
  independently, so a scored run also exercises both on real data.

**Use it to gate PR 2.2:** `uv run python -m tests.evals.run --out before.json`,
change the prompt, then re-run with `--out after.json --baseline before.json`.

## Phase 3 — Edit an existing agent

*(Was Phase 4. Reordered — see rationale.)*

### PR 3.1 — Load, read, diff, edit `task/034_edit_agent`
Merged from the original 4.1+4.2: `load_agent_files` alone had no caller.

- [x] `load_agent_files` (manifest) + `read_generated_file` from PR 1.4, so the
      builder never regenerates a file it has not read (spec §4.1)
- [x] `tasks/edit_agent.yaml`; `hugin create --edit <path> --instruction "..."`
- [x] Unified diff + y/n confirmation before writing; `--dry-run` already existed
- [x] Authorised-write allowlist (`--only`); git dirty-tree guard
- [ ] Provenance markers — **deferred, see below**
- [x] Round-trip test: one regenerated file touches exactly one file and leaves a
      hand-added unrelated file intact

Shipped as #108.

**Two things had to be solved before an edit could write at all**, neither of
which the plan anticipated:

- The writer only overwrites a file whose content still matches the hash it
  recorded when *it* wrote it. An edit reads an agent this session never wrote,
  so nothing was owned and every file was a conflict. `load_agent_files` now
  adopts what it read: the guard that matters (a file changing between load and
  write) still fires, and only the unmeetable claim "this session created it"
  is waived.
- A previously generated agent holds `README.md` and `BUILD_REPORT.md`.
  Carrying them into the payload fails validation — they are not generated
  keys — and regenerating them rewrites a build's documentation from a one-line
  edit instruction. Edit mode emits no framework files at all, which is what
  makes the round-trip guarantee literally true.

**Deviation on the authorised-write list.** Spec §4.2 asked for the set to be
*derived from the instruction*. That means asking a model which files a
sentence implies — a guess, enforcing itself as if it were a rule. `--only`
takes the set from the caller instead: same protection, deterministic. It
matters most for `--yes`, since an interactive edit already shows a diff.

**Provenance deferred, with a reason.** The in-session hash manifest already
gives edit mode the "refuse to overwrite something modified since we read it"
guarantee. What is missing is *cross-session* provenance — an on-disk manifest
saying which lines a machine wrote. That is a new file format in the agent
directory and belongs with Phase 5 attribution, which is the first thing that
actually needs it. Building it now would ship a format with no reader.

**Known cosmetic issue:** regenerating a YAML file round-trips it through the
parser, so block scalars can come back as quoted strings. Nothing breaks and
the diff shows it, but it makes a small edit look larger than it is.

### PR 3.2 — Interactive builder `task/034_interactive_builder`
- [ ] `agent_builder_interactive` config with `builtins.ask_user`
- [ ] `hugin create --interactive`; default unchanged

---

## Phase 4 — Architectural depth

*(Was Phase 3.)*

### PR 4.1 — Pipeline architecture, end to end `task/034_pipeline_architecture`
Merged from the original 3.1+3.2, scoped to **one** architecture. Splitting them
would ship task-schema parameters no prompt mentions plus a new failure mode.

- [x] `generate_task`: `task_sequence`, `next_task`, `pass_result_as`,
      `chain_config`, `system_template`
- [x] `generate_config`: `interactive`, `state_namespaces`,
      `enable_builtin_agents`, `options`; stop force-appending
      `save_text`/`save_file` — and remove that assertion from all four places
      (`generate_config.py:34-42`, `builder_system.yaml:14`,
      `build_agent.yaml:48-50`, `reviewer_system.yaml:24-27`)
- [x] `architecture` as `type: array` with per-item validation — **not**
      `categorical`, which cannot hold a list (spec §3.3)
- [x] Architecture invariants machine-checked in `validate_agent`
- [x] Selection as a separate cheap structured turn, not a mid-generation choice
- [x] `knowledge/references/*.md` updated in this same PR
- [x] Golden-set harness re-run

Shipped as #103, pulled forward from Phase 4 because the eval showed the
blocker was the tool schema rather than the prompt: `produced_a_pipeline` went
0/2 to 2/2, and `research_pipeline` went from a 10.5k-token max-steps failure
to a 3.5k-token success.

**Scope cut, deliberately:** the `architecture` parameter and the separate
selection turn were not built. Widening the schema alone was sufficient, and
adding a selection mechanism on top would have been building on a guess. The
`type: array` vs `categorical` question in spec §3.3 is therefore still open
and only matters if selection is ever added.

Not done here: `generate_config`'s wider fields (`interactive`,
`state_namespaces`, `enable_builtin_agents`, `options`) and removing the forced
`save_text`/`save_file` append. No evidence yet says they block anything.

### PR 4.2 — Further architectures `task/034_more_architectures`
Add only on demand. `delegating` needs `generate_tool`'s
`return_type: agent_call`; `shell` needs the sandbox posture rules in spec §3.3
(`backend: docker` default, hard-fail on `allow_unrestricted_egress`,
`network: false` until tasks 030/030b) plus a session-level agent-count cap.

---

## Phase 5 — Trace-driven improvement

Gated on PR 3.1. `hugin analyze` already shipped in Phase 1.5.

### PR 5.1 — `improve_agent`, propose-only `task/034_improve_agent`
- [x] `propose_change(file, change_type, metric, observed_value, rationale)`
      validating against the stored report — rejects uncited or mismatched
      claims structurally (spec §5.2)
- [x] Trace-derived strings in a delimited untrusted block, never instructions
- [ ] Replay set harvested from real trace parameters — **not built, see below**
- [x] Proposals printed with their evidence; **no write path** — the task has
      no write tool and chains nowhere, so applying is not expressible

Shipped as #109, with `hugin improve`.

**Replay deferred to 5.2, deliberately.** A replay set only earns its keep next
to a before/after comparison, and there is nothing to compare until something
can be applied. Building the harvester now would ship a fixture with no
consumer. It stays a hard prerequisite for `--apply`.

**The citation check had to be loosened once, and the reason matters.** The
first version compared each row of a list metric against the whole cited
string, so a *correct* citation of `loops_detected` was refused three times on
a real run. A guard that rejects truthful evidence is worse than no guard: it
teaches the model to abandon real findings. Strictness is not automatically the
safe direction here.

### PR 5.2 — `--apply` with a regression guard `task/034_improve_apply`
- [ ] **Never optimise `self_reported_success_rate`** (spec §5.1c). It is the
      agent's own `finish_type`, so the cheapest way to raise it is to declare
      success sooner. Where gimle-router has an outcome for a run
      (`llm/router_outcome.py` already POSTs one), that is the authority;
      otherwise the replay comparison is. `propose_change` should reject a
      proposal citing the self-reported metric as evidence of improvement.
- [ ] Before/after replay on identical harvested inputs via `test_agent`
- [ ] Agent-directory hash stamped into session metadata for attribution
- [ ] `dead_tools` proposals are warnings with a minimum-N threshold, never
      automatic deletions
- [ ] `--apply` opt-in, after a diff, with the revert path named in the output

---

## Definition of done (per PR)

- [ ] `uv run pre-commit run --all-files` clean (mypy's pre-existing
      `openai/_client.py` failure excepted)
- [ ] `uv run pytest -x -q` passes
- [ ] New behaviour covered by tests, using `ScriptedToolModel` — **not**
      `MockModel`, which cannot emit tool calls
- [ ] `hugin validate` still clean over `examples/` and `apps/`
- [ ] Docs updated when user-facing; schema changes update
      `knowledge/references/*.md` in the same PR
- [ ] Checkboxes ticked in this file as part of the PR
- [ ] Reviewed with `/panel-review` before merge for anything beyond a defect fix

## Docs owed (not yet scheduled to a PR)

`docs/src/how-to/troubleshoot-builds.md` — the validator's error catalogue with a
fix for each, what a missing dependency means, how to retry, roughly what a build
costs. Given the failure path in spec §1.2c, this is the page users will actually
open. Also: `hugin validate`, `hugin analyze`, the non-interactive flags,
`--architecture`, `--reference-file`, `--edit`, . The model-table item is **done** -- `use-creator.md` now points at
`model_registry.py` instead of restating the list; the note claiming otherwise
was itself stale, and its line numbers no longer resolve.
