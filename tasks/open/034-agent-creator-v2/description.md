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
| `tools/write_agent_files.py:60` | `shutil.rmtree(output_dir)` unconditionally. Point it at an existing directory and it is gone — no existence check, no backup, no confirmation. |
| `tools/list_examples.py`, `tools/read_example.py` | 495 lines of example-catalog tooling **not listed in `configs/agent_builder.yaml`**. Dead code — the builder cannot study any existing example before generating. |
| `tasks/build_agent.yaml:19`, `cli/create_agent.py:281` | `full_implementation` is asked in the wizard and declared as a task parameter, but referenced in **zero** prompts. Dead flag. |
| `tools/write_agent_files.py:104` | Generated `README.md` tells users `uv run run-agent --task main …`. That entrypoint does not exist — `pyproject.toml:126` defines only `hugin`. Every generated agent ships broken run instructions. |
| `tools/generate_tool.py:100-108` | Types every parameter as `str` in the emitted signature regardless of its declared schema type, then wraps the entire body in a bare `except Exception` returning only `str(e)` with no traceback. |
| `tasks/review_agent.yaml` + `configs/reviewer.yaml` | The review stage is an LLM reading a *preview string*. Nothing ever dry-loads the environment, so a config referencing a nonexistent template or tool passes review and only fails at `test_agent` — or silently at the user's first run. |
| `tools/test_agent.py:88-100` | Picks `configs[0]`/`tasks[0]` arbitrarily, mutates global `sys.path`, and injects the *tested* agent's templates into the *builder's* template registry. |
| `cli/create_agent.py:167-170` | Model lists hardcoded (`sonnet-latest`, `gpt-4o`, …) instead of read from `llm/models/model_registry.py`. No non-interactive mode, so `hugin create` cannot be scripted or covered by an end-to-end test. |

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

- [ ] A generated agent that fails to load is impossible to write to disk — the
      validator blocks it deterministically, without an LLM in the loop.
- [ ] The creator can produce a multi-stage (`task_sequence`) agent and an agent
      that delegates to sub-agents, verified by end-to-end tests.
- [ ] Hugin reference documentation exists in exactly one place and both creator
      surfaces read it.
- [ ] `hugin create --edit <path>` modifies an existing agent without destroying
      unrelated files.
- [ ] `hugin improve <path> --storage-path <s>` produces a concrete, applied
      improvement from real trace data.
- [ ] `hugin create` runs non-interactively from flags and is covered end-to-end.
