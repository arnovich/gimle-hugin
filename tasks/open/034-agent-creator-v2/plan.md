---
title: Agent Creator v2 — Implementation Plan
state: OPEN
---

# Agent Creator v2 — Implementation Plan

Incremental PRs, each independently mergeable, each leaving `main` working.
Branch per PR off `main`, snake_case, `task/` prefix. See `spec.md` for design.

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
- [ ] Read `storage/agents/<uuid>` JSON + `load_interaction_metadata`, following
      `cli/monitor_agents.py:671,747` — **not** `load_interaction(uuid, stack)`,
      which needs a Stack that does not exist for historic runs (spec §5.1)
- [ ] Decide and record: lift `load_interaction_metadata` to the `Storage` ABC,
      or scope this to `LocalStorage` explicitly
- [ ] Redactor + normalised error signatures, with a test asserting a seeded
      fake key never reaches the report

### PR 1.9 — `hugin analyze` `task/034_analyze_cli`
- [ ] `analyze_traces` over the metrics in spec §5.1, top-N bounded
- [ ] `hugin analyze <path> --storage-path <s>` printing the report
- [ ] `tests/test_analyze_traces.py` against a synthetic storage dir
- [ ] **Then** revise spec §5.1's metric table against one real storage dir
      before anything consumes it

---

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

- [ ] 10-20 descriptions spanning the architectures
- [ ] Scored run behind `slow`/`integration`: first-pass validation rate,
      post-repair rate, attempts used, architecture match, `test_agent` success,
      steps, tokens, dollars
- [ ] Numbers recorded in this task file per PR

---

## Phase 3 — Edit an existing agent

*(Was Phase 4. Reordered — see rationale.)*

### PR 3.1 — Load, read, diff, edit `task/034_edit_agent`
Merged from the original 4.1+4.2: `load_agent_files` alone had no caller.

- [ ] `load_agent_files` (manifest) + `read_generated_file` from PR 1.4, so the
      builder never regenerates a file it has not read (spec §4.1)
- [ ] `tasks/edit_agent.yaml`; `hugin create --edit <path> --instruction "..."`
- [ ] Unified diff + y/n confirmation before writing; `--dry-run` on `create` too
- [ ] Authorised-write allowlist; git dirty-tree guard; provenance markers
- [ ] Round-trip test: one regenerated file touches exactly one file and leaves a
      hand-added unrelated file intact

### PR 3.2 — Interactive builder `task/034_interactive_builder`
- [ ] `agent_builder_interactive` config with `builtins.ask_user`
- [ ] `hugin create --interactive`; default unchanged

---

## Phase 4 — Architectural depth

*(Was Phase 3.)*

### PR 4.1 — Pipeline architecture, end to end `task/034_pipeline_architecture`
Merged from the original 3.1+3.2, scoped to **one** architecture. Splitting them
would ship task-schema parameters no prompt mentions plus a new failure mode.

- [ ] `generate_task`: `task_sequence`, `next_task`, `pass_result_as`,
      `chain_config`, `system_template`
- [ ] `generate_config`: `interactive`, `state_namespaces`,
      `enable_builtin_agents`, `options`; stop force-appending
      `save_text`/`save_file` — and remove that assertion from all four places
      (`generate_config.py:34-42`, `builder_system.yaml:14`,
      `build_agent.yaml:48-50`, `reviewer_system.yaml:24-27`)
- [ ] `architecture` as `type: array` with per-item validation — **not**
      `categorical`, which cannot hold a list (spec §3.3)
- [ ] Architecture invariants machine-checked in `validate_agent`
- [ ] Selection as a separate cheap structured turn, not a mid-generation choice
- [ ] `knowledge/references/*.md` updated in this same PR
- [ ] Golden-set harness re-run

### PR 4.2 — Further architectures `task/034_more_architectures`
Add only on demand. `delegating` needs `generate_tool`'s
`return_type: agent_call`; `shell` needs the sandbox posture rules in spec §3.3
(`backend: docker` default, hard-fail on `allow_unrestricted_egress`,
`network: false` until tasks 030/030b) plus a session-level agent-count cap.

---

## Phase 5 — Trace-driven improvement

Gated on PR 3.1. `hugin analyze` already shipped in Phase 1.5.

### PR 5.1 — `improve_agent`, propose-only `task/034_improve_agent`
- [ ] `propose_change(file, change_type, metric, observed_value, rationale)`
      validating against the stored report — rejects uncited or mismatched
      claims structurally (spec §5.2)
- [ ] Trace-derived strings in a delimited untrusted block, never instructions
- [ ] Replay set harvested from real trace parameters
- [ ] Proposal printed as a diff; **no write path in this PR**

### PR 5.2 — `--apply` with a regression guard `task/034_improve_apply`
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
`--architecture`, `--reference-file`, `--edit`, and a model table generated from
`model_registry.py` rather than restated (`use-creator.md:71-73` is already stale
against `create_agent.py:167-170`).
