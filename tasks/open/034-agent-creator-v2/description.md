---
title: Agent Creator v2
state: OPEN
labels: [enhancement, agent-builder]
priority: high
supersedes: 013-agent-builder-enhancements
---

# Agent Creator v2

Significantly upgrade the meta-agent that builds Hugin agents, in five phases:
correctness gate, unified knowledge base, architectural depth, edit-existing-agent
mode, and finally trace-driven improvement of agents already in production.

Folds in `tasks/open/013-agent-builder-enhancements.md` (read local files; embed
and make examples searchable) — see Phase 2.

## Why

### The headline problem: the builder cannot build an agent as sophisticated as itself

`tools/generate_task.py` emits only `name`, `description`, `parameters`, `prompt`,
`tools`. It has no way to write `task_sequence`, `next_task`, `pass_result_as`,
`chain_config`, or `system_template` — the exact fields that `agent_builder`'s own
`tasks/build_agent.yaml` uses to run its 4-stage pipeline.

`tools/generate_config.py` hardcodes `interactive: False` and `options: {}`, and
cannot emit `state_namespaces`, `enable_builtin_agents`, or a `state_machine`.

The consequence is that **every agent the creator produces is a single-shot loop
with flat tools**. Sub-agents (`AgentCall`), task pipelines, branching, artifacts
and insights, human-in-the-loop, shared state, and the bash sandbox — Hugin's
entire differentiated feature surface — are structurally unreachable. We ship a
framework capable of `apps/the_hugins` and a creator that generates the
equivalent of `examples/basic_agent`.

### Three creator surfaces, drifting apart

| Surface | What it is | Knowledge source |
|---|---|---|
| `src/gimle/hugin/apps/agent_builder/` | The meta-agent: `build_agent → review_agent → finalize_agent → test_agent` | `templates/builder_system.yaml` (72 lines) |
| `src/gimle/hugin/cli/create_agent.py` | The `hugin create` wizard (555 lines) | hardcoded model lists |
| `skills/hugin-agent-creator/` | Claude Code plugin, 5 reference docs incl. a 449-line pattern catalog | `references/*.md` (~1770 lines) |

The runtime builder never sees a single line of the skill's pattern catalog. Any
Hugin change has to be written up in two places, and today they disagree.

### Verified defects

| Location | Defect |
|---|---|
| `tools/write_agent_files.py:57` | `shutil.rmtree(output_dir)` unconditionally. Point it at an existing directory and it is gone — no existence check, no backup, no confirmation. |
| `tools/write_agent_files.py:77-79` | `output_dir / file_path` where `file_path` is an unvalidated LLM-chosen name. `pathlib` does not normalise `..`, and an absolute key *replaces* the root: `Path("/a/b") / "/etc/passwd"` is `/etc/passwd`. Combined with `mkdir(parents=True)`, a generated `tool_name` of `../../../.bashrc` writes anywhere the process can reach. None of the four `generate_*` tools validates a name. |
| `utils/registry.py:20` | `self._items[name] = instance` — silent overwrite, no collision check, on a process-global `Tool.registry` (`tools/tool.py:96`). `write_agent_files.py:110` registers generated tools into it mid-build, so a generated tool named `finish` or `preview_files` replaces the builder's own for the rest of the run. |
| `tools/tool.py:154` | `importlib.import_module` with no reload, against the flat module name `generate_tool.py:186` emits. After a repair, re-testing returns the **cached stale module** — so a fix-and-retest loop diagnoses the same failure and burns its attempts. A generated `tools/json.py` shadows stdlib process-wide. |
| `tools/list_examples.py`, `tools/read_example.py` | 495 lines of example-catalog tooling **not listed in `configs/agent_builder.yaml`**. Dead code — the builder cannot study any existing example before generating. Both work as-is and inject `stack` only if declared (`tools/tool.py:353`), so wiring them is two lines of YAML. |
| `tasks/build_agent.yaml:19`, `cli/create_agent.py:281,321` | `full_implementation` is asked in the wizard and declared as a task parameter, but referenced in **zero** prompts. Dead flag. |
| `tools/write_agent_files.py:91` | Generated `README.md` tells users `uv run run-agent --task main …`. That entrypoint does not exist — `pyproject.toml:126` defines only `hugin`. The success screen (`cli/create_agent.py:525`) and `docs/src/how-to/use-creator.md:137` each give a *third* and *fourth* different command. |
| `tools/generate_tool.py:87-98` | Types every parameter as `str` in the emitted signature regardless of its declared schema type, then wraps the entire body in a bare `except Exception` returning only `str(e)` with no traceback. |
| `tasks/review_agent.yaml` + `configs/reviewer.yaml` | The review stage is an LLM reading a *preview string*. Nothing ever dry-loads the environment, so a config referencing a nonexistent template or tool passes review and only fails at `test_agent` — or silently at the user's first run. Because `TaskChain.step` chains on the *same stack and agent* (`interaction/task_chain.py:78-188`), the reviewer also sees the whole build transcript: this is self-review, not review. |
| `tools/test_agent.py:92-114` | Picks `configs[0]`/`tasks[0]` arbitrarily, mutates global `sys.path` permanently, and injects the *tested* agent's templates into the *builder's* template registry. |
| `cli/create_agent.py:167-170` | Model lists hardcoded (`sonnet-latest`, `gpt-4o`, …) instead of read from `llm/models/model_registry.py`. No non-interactive mode, so `hugin create` cannot be scripted or covered by an end-to-end test. |

### Trust boundary

`agent_builder` is a **code-execution tool**: it turns a natural-language description into Python and then imports and runs it. The bash-sandbox work (`tasks/closed/023-bash-tool`) states its threat model in prose and refuses a silent backend default; this surface has never had one written down. Stating it is part of this task.

**Position taken: generated code is executed with the operator's full privileges, and the description, any `--reference-file`, and any analysed trace are assumed non-hostile.** Consequences, to be documented in the README and on the `hugin create` screen:

- Validation must not be described as a sandbox. A subprocess is a crash boundary, not a security boundary — and it is void anyway, because `write_agent_files` imports the same modules in-process seconds later.
- Where a *mechanical* guarantee is cheap, take it: path confinement, name validation, and reserved-name collision checks are ~40 lines and prevent the builder writing outside its target directory at all.
- Anything that weakens this position — Phase 3's `shell` architecture, Phase 4's editing of hand-written code, Phase 5's unattended rewriting — must state its own additional constraints where it is specified.

This repo already ships `src/gimle/hugin/sandbox/` (docker/local/ssh backends, egress proxy, reaper). Running generated code inside it is the upgrade path to a real boundary, and is deliberately **out of scope here** — noted so the choice is explicit rather than overlooked.

### What we cannot do today, and want to

Run a generated agent for a while, look at its Hugin traces, and feed those back
into the creator so it improves the agent. The storage layer already records
everything needed (`Storage.list_sessions/list_agents/list_interactions`,
per-interaction JSON, and `rendered_system_prompt`/`rendered_user_message` when
`HUGIN_CAPTURE_RENDERED_PROMPTS=1`), but no tool reads it back.

## Phases

1. **Correctness gate** — deterministic `validate_agent`, plus the defect table above.
2. **Unified knowledge base** — one canonical set of reference docs read by both the
   runtime builder and the Claude Code skill; examples embedded and searchable
   (closes 013).
3. **Depth** — full config/task schema, architecture selection, sub-agent-capable
   tool generation.
4. **Edit mode** — load an existing agent and modify it instead of greenfield-only.
5. **Trace-driven improvement** — `hugin improve`, analysing historic runs.

Phases 1–4 are prerequisites for 5: trace-driven improvement is exactly Phase 4's
edit path driven by a Phase 1 validator, informed by Phase 2/3 pattern knowledge.

See `spec.md` for the design and `plan.md` for the PR breakdown.

## Success Criteria

- [x] `write_agent_files` refuses to write a payload it has not itself validated.
      The gate lives in the tool, not in a prompt sentence — no reachable
      instruction to the model can skip it.
- [x] No generated file can be written outside its target directory, and no
      generated name can shadow a builtin tool or a stdlib module.
- [x] `hugin validate` passes clean on every directory in `examples/` and `apps/`,
      enforced in CI. A validator that fails on the repo's own shipped agents is
      wrong about the framework, not right about the agents.
- [x] A failed build always leaves the user something actionable: the rejected
      payload on disk plus the validator's errors, never a silent zero after a
      paid multi-stage run.
- [ ] The creator can produce a multi-stage (`task_sequence`) agent, verified by
      an end-to-end test — and the architecture claim is machine-checked, not
      asserted by a reviewer.
- [ ] `hugin create --edit <path>` shows a diff before writing and never
      regenerates a file it has not read.
- [ ] `hugin analyze` reports on real trace data with no LLM in the loop, and
      `hugin improve` proposes by default and applies only on `--apply`.
- [x] `hugin create` runs non-interactively from flags and is covered end-to-end.
- [ ] Schema knowledge is not duplicated further than today: measured by the
      number of places that must change to add one `Config` field.

## Progress (2026-08-16)

Phase 1 complete: PRs #82, #83, #85, #87 merged; #97 open and green. See
`plan.md` -> "Status — start here" for what to pick up next and why.

Criteria still open are Phase 3-5 work (edit mode, machine-checked architecture
claims, `hugin analyze` / `hugin improve`) and the one measurement criterion:
nothing yet counts places-to-change-per-`Config`-field, because the knowledge
base work in Phase 2 has not started.
