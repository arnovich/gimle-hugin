---
title: Agent Creator v2 — Implementation Plan
state: OPEN
---

# Agent Creator v2 — Implementation Plan

Incremental PRs, each independently mergeable, each leaving `main` working.
Branch per PR off `main`, snake_case, `task/` prefix. See `spec.md` for design.

Rationale for the ordering: Phase 1's validator is the safety net every later
phase leans on — widening the schema (Phase 3) without a validator would let the
builder emit pipelines referencing tasks that do not exist, and Phase 5 rewrites
agents automatically, which is only safe once writes are non-destructive (1.4)
and incremental (4.2).

---

## Phase 1 — Correctness gate

### PR 1.1 — `write_agent_files` safety `task/034_write_files_safety`
The `shutil.rmtree` at `write_agent_files.py:60` is a data-loss bug; it goes
first and alone.

- [ ] Add `overwrite` / `dry_run` parameters; refuse a non-empty existing target
      by default; back up to `<path>.bak.<timestamp>` when overwriting
- [ ] Fix the generated README to `uv run hugin run --task <task> --task-path <path>`
- [ ] `tests/test_write_agent_files_safety.py`

### PR 1.2 — `validate_agent` tool `task/034_validate_agent`
- [ ] `tools/validate_agent.py` + `.yaml`: structure, reference resolution, Jinja
      parameter binding, tool contract, subprocess import check, subprocess dry load
- [ ] Compact `{ok, errors, warnings, missing_dependencies, summary}` payload
- [ ] `tests/test_validate_agent.py` — one broken fixture per check + a clean one

### PR 1.3 — Wire the gate `task/034_validation_gate`
- [ ] `validate_agent` in `configs/agent_builder.yaml`
- [ ] `build_agent.yaml`: validate before `finish`, bounded repair loop (max 3)
- [ ] `finalize_agent.yaml`: `ok: true` required before `write_agent_files`
- [ ] Strip the now-mechanical checks (§2-§5) from `templates/reviewer_system.yaml`;
      narrow the reviewer to description alignment
- [ ] `hugin validate <path>` subcommand in `cli/cli.py`
- [ ] `requirements.txt` emission from `missing_dependencies`

### PR 1.4 — Defect sweep `task/034_builder_defect_sweep`
- [ ] Wire `list_examples` + `read_example` into `configs/agent_builder.yaml`
- [ ] Remove the dead `full_implementation` flag (wizard, task, summary screen)
- [ ] `generate_tool.py`: real type hints from the declared schema; include a
      truncated traceback in the except branch
- [ ] `cli/create_agent.py`: models from `model_registry.py`; non-interactive
      flags (`--name`, `--description`, `--model`, `--builder-model`, `--output`,
      `--yes`)
- [ ] `tools/test_agent.py`: explicit `config_name`/`task_name`; stop polluting
      the builder's template registry
- [ ] End-to-end test of non-interactive `hugin create` with `MockModel`

---

## Phase 2 — One knowledge base (closes task 013)

### PR 2.1 — Canonical knowledge package `task/034_knowledge_package`
- [ ] Create `src/gimle/hugin/knowledge/` with `references/` + `templates/`;
      move the five reference docs out of `skills/hugin-agent-creator/`
- [ ] `get_knowledge_path()`, `list_references()`, `read_reference()`
- [ ] `pyproject.toml` package-data so it ships in the wheel
- [ ] Repoint `skills/hugin-agent-creator/skills/*/SKILL.md` at the package path
      with the in-repo path as development fallback
- [ ] Test: both surfaces resolve the same dir; every file named in `SKILL.md` exists

### PR 2.2 — Builder reads the knowledge base `task/034_read_reference_tool`
- [ ] `read_reference` tool + config entry
- [ ] Rewrite `templates/builder_system.yaml` as routing instructions; delete the
      duplicated schema prose
- [ ] Update `docs/src/how-to/use-creator.md`

### PR 2.3 — Real example search `task/034_example_search`
- [ ] Delete `FALLBACK_EXAMPLES`; derive the index by scanning `examples/` and
      `apps/` (README heading, present directories, `task_sequence` usage,
      `AgentCall` usage), cached in `env_vars`
- [ ] `search_examples(query)` returning short snippets with file+line
- [ ] Test: finds a known string in a known example

### PR 2.4 — User reference files `task/034_reference_files`
- [ ] `builtins.read_file` + `builtins.list_files` into the builder config
- [ ] `reference_files` parameter on `build_agent`; `--reference-file` on the wizard
- [ ] **Closes `tasks/open/013-agent-builder-enhancements.md`** — move it to
      `tasks/closed/` in this PR

---

## Phase 3 — Architectural depth

### PR 3.1 — Full task and config schema `task/034_full_schema`
- [ ] `generate_task`: `task_sequence`, `next_task`, `pass_result_as`,
      `chain_config`, `system_template`
- [ ] `generate_config`: `interactive`, `state_namespaces`,
      `enable_builtin_agents`, `options`; stop force-appending
      `save_text`/`save_file`
- [ ] Extend `validate_agent`: sequence/successor names must exist,
      `pass_result_as` must name a declared parameter of the successor
- [ ] Tests for each new field, including the cross-reference failures

### PR 3.2 — Architecture selection `task/034_architecture_selection`
- [ ] `architecture` parameter (categorical list, `auto` default) on `build_agent`
- [ ] Architecture → reference-example mapping in the builder prompt
- [ ] Reviewer checks the choice against the description
- [ ] `--architecture` flag on `hugin create`
- [ ] Per-architecture build test with `MockModel`, each asserted to validate clean

### PR 3.3 — Sub-agent-capable tools `task/034_agent_call_tools`
- [ ] `return_type: tool_response | agent_call` on `generate_tool`
- [ ] Emit the `Union[ToolResponse, AgentCall]` form with config/task lookup
- [ ] End-to-end test: generated delegating agent spawns a child and completes

---

## Phase 4 — Edit an existing agent

### PR 4.1 — Load and incremental write `task/034_load_agent_files`
- [ ] `load_agent_files` tool returning a manifest only
- [ ] `write_agent_files(changed_only=True)` reporting written vs unchanged
- [ ] Round-trip test: one regenerated file touches exactly one file on disk and
      leaves a hand-added unrelated file intact

### PR 4.2 — `edit_agent` task and CLI `task/034_edit_agent`
- [ ] `tasks/edit_agent.yaml`
- [ ] `hugin create --edit <path> --instruction "..."`
- [ ] Docs + end-to-end test ("add a tool to this agent")

### PR 4.3 — Interactive builder `task/034_interactive_builder`
- [ ] `agent_builder_interactive` config with `builtins.ask_user`
- [ ] `hugin create --interactive`; default unchanged

---

## Phase 5 — Trace-driven improvement

Gated on Phases 1-4. Do not start before PR 4.1 merges — automated rewriting of a
working agent is only safe on top of validated, incremental, non-destructive
writes.

### PR 5.1 — `analyze_traces` `task/034_analyze_traces`
- [ ] Tool over the `Storage` API: success rate, step exhaustion, step
      percentiles, per-tool call/error counts and top errors, dead tools,
      oversized results, detected loops
- [ ] Bounded report payload (top-N truncation on every list)
- [ ] `tests/test_analyze_traces.py` against a synthetic storage dir produced by
      running a fixture agent with `MockModel`

### PR 5.2 — `improve_agent` `task/034_improve_agent`
- [ ] `tasks/improve_agent.yaml`: analyze → load → evidence-linked proposal →
      apply → validate → write → test
- [ ] Every proposed change must cite the metric that motivated it
- [ ] End-to-end test on an agent with a deliberately dead tool and a
      deliberately oversized tool result

### PR 5.3 — `hugin improve` CLI `task/034_improve_cli`
- [ ] `hugin improve <path> --storage-path <s> [--limit N] [--dry-run]`
- [ ] `--dry-run` prints the proposal without touching files
- [ ] `docs/src/how-to/improve-agents.md`; note that
      `HUGIN_CAPTURE_RENDERED_PROMPTS=1` materially enriches the analysis

---

## Definition of done (per PR)

- [ ] `uv run pre-commit run --all-files` clean (mypy's pre-existing
      `openai/_client.py` failure excepted)
- [ ] `uv run pytest -x -q` passes
- [ ] New behaviour covered by tests
- [ ] Docs updated when user-facing (`docs/src/how-to/use-creator.md`, CLAUDE.md)
- [ ] Checkboxes ticked in this file as part of the PR
- [ ] Reviewed with `/panel-review` before merge for anything beyond a defect fix
