---
title: Agent Creator v2 — Technical Specification
state: OPEN
---

# Agent Creator v2 — Technical Specification

All paths are relative to the repo root. The meta-agent lives at
`src/gimle/hugin/apps/agent_builder/`; the wizard at
`src/gimle/hugin/cli/create_agent.py`; the Claude Code plugin at
`skills/hugin-agent-creator/`.

---

## Phase 1 — Deterministic correctness gate

### 1.1 `validate_agent` tool

New tool `apps/agent_builder/tools/validate_agent.py` (+ `.yaml`). It is the
single highest-leverage addition: it replaces "an LLM read a preview string and
said it looked fine" with a hard, mechanical gate.

Signature:

```python
def validate_agent(
    stack: "Stack",
    agent_path: Optional[str] = None,
    check_imports: bool = True,
) -> ToolResponse:
```

When `agent_path` is omitted it validates the in-memory
`env_vars["generated_files"]` by materialising them into a `TemporaryDirectory`.
This lets it run *before* anything touches the user's filesystem.

Checks, in order (cheapest first, all deterministic — no LLM):

1. **Structure** — `configs/` and `tasks/` exist and are non-empty; every
   `tools/*.py` has a sibling `.yaml` and vice versa.
2. **Reference resolution**
   - `config.system_template` resolves to a registered template name, or is an
     inline Jinja string (contains `{{`). A bare string matching neither is the
     failure mode that `tasks/open/019-warn-on-unknown-template-reference.md`
     already flags — reuse that check.
   - Every entry in `config.tools` resolves: `builtins.X:Y` exists in the builtin
     registry, or `X` names a generated tool.
   - `task.tools`, when present, is a subset of the resolvable tool set.
3. **Jinja parameter binding** — parse each task `prompt` and `system_template`
   with `jinja2.meta.find_undeclared_variables` over `Environment().parse(src)`.
   Every undeclared root variable must be a declared task parameter. This catches
   `{{ ticker.value }}` where `ticker` was never declared — the most common
   silent breakage, and one the current pipeline cannot see at all.
4. **Tool contract** — each `tools/*.py` compiles (`compile(src, path, "exec")`);
   the function named by the YAML's `implementation_path` (`mod:func`) exists;
   its signature accepts `stack`; every parameter in the YAML `parameters` block
   appears in the signature.
5. **Import check** (`check_imports=True`) — import each tool module in a
   **subprocess** (`python -c "import importlib.util; …"`) so a broken or
   side-effecting module cannot poison the builder process. `ModuleNotFoundError`
   is reported as a *missing dependency* with the module name, not as a generic
   failure — this feeds §1.3.
6. **Dry load** — `Environment.load(tmpdir, storage=LocalStorage(tmp))` in the
   same subprocess. Any exception is a hard failure with the traceback's last
   frame.

Return payload is deliberately small (the builder's own system template mandates
token-efficient tools, and today none of its tools obey it):

```python
ToolResponse(is_error=not ok, content={
    "ok": bool,
    "errors": [{"file": str, "check": str, "message": str}],   # blocking
    "warnings": [{"file": str, "check": str, "message": str}], # non-blocking
    "missing_dependencies": [str],
    "summary": "3 errors, 1 warning",
})
```

Never return file contents — the agent can `read_example`/`preview_files` if it
needs to look.

### 1.2 Wiring the gate

- `tasks/build_agent.yaml`: call `validate_agent` before `finish`; loop on errors
  (bounded, max 3 attempts) rather than handing garbage to the reviewer.
- `tasks/finalize_agent.yaml`: `validate_agent` **must** return `ok: true` before
  `write_agent_files` is called. This is the enforcement point.
- `configs/agent_builder.yaml`: add `validate_agent` to `tools`.
- New CLI subcommand `hugin validate <agent_path>` in `cli/cli.py` so humans and
  CI can run the same checks on any agent directory, generated or handwritten.

The LLM reviewer (`review_agent`) survives, but its remit narrows to what a
machine cannot judge: *does this agent actually match the description?* All the
mechanical checks currently in `templates/reviewer_system.yaml` (§2 required
builtins, §3 parameter schema, §4 return statement, §5 valid Python) move to the
validator and are deleted from the prompt.

### 1.3 Dependency declaration

Generated agents routinely import `yfinance`, `pandas`, `requests` — none
guaranteed present. `validate_agent`'s `missing_dependencies` gets written to a
`requirements.txt` in the generated agent directory and surfaced in its README
and in the `hugin create` success screen. We do not auto-install.

### 1.4 Defect fixes

**`write_agent_files.py` — stop destroying directories.** Replace the
unconditional `shutil.rmtree(output_dir)` with:

```python
def write_agent_files(stack, output_path, agent_name="",
                      overwrite: bool = False, dry_run: bool = False)
```

- Non-existent or empty target → write.
- Existing non-empty target and `overwrite=False` → `is_error=True` listing the
  conflicting paths. No data loss.
- `overwrite=True` → move the existing directory to
  `<output_path>.bak.<timestamp>` and write fresh. Never `rmtree` without a
  backup. (Timestamp comes from `datetime.now()`; the sibling backup keeps the
  operation reversible.)
- `dry_run=True` → return the file list that *would* be written.

**Other fixes** (each small, each independently testable):

- `configs/agent_builder.yaml`: add `list_examples`, `read_example` to `tools`.
- `tasks/build_agent.yaml` + `cli/create_agent.py`: implement `full_implementation`
  (stub mode emits `raise NotImplementedError` bodies) or remove it. Recommend
  **remove** — a stub agent is not useful and the flag has never worked.
- `write_agent_files.py` README template: `uv run hugin run --task <task_name>
  --task-path <output_path>`, using the actual generated task name.
- `generate_tool.py`: map declared schema types to real hints
  (`string→str`, `integer→int`, `number→float`, `boolean→bool`,
  `array→List[Any]`, `object→Dict[str, Any]`), and include
  `traceback.format_exc()[-2000:]` in the except-branch payload so failures are
  diagnosable.
- `cli/create_agent.py`: source model choices from
  `llm/models/model_registry.py` rather than the hardcoded lists at lines
  167-170.
- `cli/create_agent.py`: add non-interactive flags (`--name`, `--description`,
  `--model`, `--builder-model`, `--output`, `--yes`) so the wizard is scriptable
  and coverable by an end-to-end test.
- `tools/test_agent.py`: take explicit `config_name`/`task_name` arguments
  instead of `configs[0]`/`tasks[0]`, and stop registering the tested agent's
  templates into the builder's own registry.

---

## Phase 2 — One knowledge base (closes task 013)

### 2.1 Canonical location

Move the reference documentation **into the package** so it ships in the wheel
and is readable at runtime by an installed Hugin:

```
src/gimle/hugin/knowledge/
├── __init__.py            # get_knowledge_path(), list_references(), read_reference()
├── references/
│   ├── config-reference.md
│   ├── task-reference.md
│   ├── template-reference.md
│   ├── tool-reference.md
│   └── patterns.md
└── templates/             # minimal-config.yaml, tool-implementation.py, …
```

`skills/hugin-agent-creator/` keeps `SKILL.md` and `plugin.json` but its
`references/` and `templates/` become pointers: `SKILL.md` instructs the coding
agent to read from the installed package path (resolved via
`python -c "from gimle.hugin.knowledge import get_knowledge_path; …"`), with the
in-repo path as the development fallback.

Add `package-data` entries in `pyproject.toml` for `knowledge/**/*.md` and
`knowledge/**/*`.

A test asserts both surfaces resolve to the same directory and that every
reference file named in `SKILL.md` exists.

### 2.2 `read_reference` tool

```python
def read_reference(topic: str, stack: "Stack") -> ToolResponse
```

`topic` ∈ `{config, task, template, tool, patterns}`. Returns the document body.
This is the one place a large payload is justified — it is read at most twice per
build, and it is what prevents the builder from inventing schema.

### 2.3 Real example search (task 013)

- Delete `FALLBACK_EXAMPLES` (the 130-line hardcoded list in `list_examples.py`).
  Build the index by scanning `examples/` and `apps/` at call time: read each
  `README.md` first heading + first paragraph, and record which of
  `configs/ tasks/ templates/ tools/` are present, whether the tasks use
  `task_sequence`, whether any tool returns `AgentCall`. That metadata is derived,
  so it cannot go stale.
- Add `search_examples(query)` — substring/keyword match over the index plus file
  bodies, returning `[{example, file, line, snippet}]` with short snippets.
- Cache the index in `env_vars` for the session.

### 2.4 Read user-supplied local files (task 013)

Add `builtins.read_file:read_file` and `builtins.list_files:list_files` (both
already exist in `tools/builtins/`) to `configs/agent_builder.yaml`, and add a
`reference_files` parameter to `build_agent` + a `--reference-file` flag on
`hugin create`, so a user can point the builder at an API spec, a sample dataset,
or an existing script to model the agent on.

### 2.5 Builder prompt shrinks

`templates/builder_system.yaml` stops being a (partial, drifting) copy of the
schema and becomes routing instructions:

> Before generating: call `list_examples`, then `read_example` on the 1-2 closest
> matches, then `read_reference` for each file type you will emit. Do not invent
> schema fields — if it is not in the reference, it does not exist.

---

## Phase 3 — Architectural depth

### 3.1 Widen `generate_task`

Add optional parameters, each validated in Phase 1's checks:

| Field | Purpose |
|---|---|
| `task_sequence: List[str]` | Multi-stage pipeline |
| `next_task: str` | Single successor |
| `pass_result_as: str` | Name the successor's parameter receiving this result |
| `chain_config: str` | Config to run a chained task under |
| `system_template: str` | Per-task system prompt override |

Validation: every name in `task_sequence`/`next_task`/`chain_config` must exist
among the generated files, and `pass_result_as` must name a declared parameter of
the successor task. Emitting a pipeline that references a task nobody generated
is exactly the class of bug the validator exists to catch.

### 3.2 Widen `generate_config`

Add `interactive`, `state_namespaces`, `enable_builtin_agents`, `options`. Stop
force-appending `save_text`/`save_file` (`generate_config.py:34-42`) — keep only
`builtins.finish:finish` mandatory, and let the architecture decide the rest. The
current behaviour gives every agent two tools it usually never calls, which
Phase 5's dead-tool analysis would then flag.

### 3.3 Architecture selection

New `architecture` parameter on `build_agent`, type `categorical` (already
supported by `generate_task`'s schema validation), with choices:

| Architecture | Emits | Reference example |
|---|---|---|
| `single_shot` | one config, one task, flat tools | `examples/basic_agent` |
| `pipeline` | `task_sequence` across stages | `examples/task_sequences` |
| `delegating` | a tool returning `AgentCall`, or `builtins.launch_agent` | `examples/sub_agent` |
| `interactive` | `interactive: true` + `builtins.ask_user` | `examples/human_interaction` |
| `stateful` | artifacts via `save_insight` / `query_artifacts` | `examples/artifacts` |
| `shell` | the sandboxed bash tool | `examples/bash_agent` |

The wizard offers `auto` (default): the builder reads the description, picks, and
must state its reasoning. `review_agent`'s narrowed remit includes checking that
the choice fits the description. Architectures compose — `architecture` is a
list, not a single value.

### 3.4 Sub-agent-capable tool generation

`generate_tool.py` currently hardcodes a `try/except` wrapper returning
`ToolResponse`, which makes it impossible to emit a tool that returns an
`AgentCall` — the documented way to spawn a child agent (CLAUDE.md: "Never run a
sub-agent synchronously inside a tool"). Add `return_type: "tool_response" |
"agent_call"`; for `agent_call`, emit the `Union[ToolResponse, AgentCall]`
signature and the config/task lookup preamble, mirroring
`apps/agent_builder/tools/test_agent.py`.

---

## Phase 4 — Edit an existing agent

### 4.1 `load_agent_files`

```python
def load_agent_files(agent_path: str, stack: "Stack") -> ToolResponse
```

Reads an existing agent directory into `env_vars["generated_files"]`, keyed
identically to the generate_* tools' output (`configs/x.yaml`, `tools/y.py`, …).
Every existing generation tool then becomes an *edit* tool for free: regenerating
`configs/x.yaml` overwrites that key and leaves everything else untouched.

Returns only a manifest (paths + line counts), never bodies.

### 4.2 Incremental writes

`write_agent_files` gains `changed_only: bool = True`: compare each generated
file against what is on disk and write only differences, reporting
`{"written": [...], "unchanged": [...]}`. Combined with §1.4, editing an agent
can no longer destroy files the builder did not generate.

### 4.3 `edit_agent` task and CLI

New `tasks/edit_agent.yaml` with parameters `agent_path`, `instruction`, and
optional `reference_files`. Flow: `load_agent_files` → `list_examples`/
`read_reference` as needed → targeted regeneration → `validate_agent` →
`write_agent_files(changed_only=True)` → `test_agent`.

CLI: `hugin create --edit <path> --instruction "add a tool that …"`.

### 4.4 Interactive builder

Set `interactive: true` on a new `agent_builder_interactive` config and add
`builtins.ask_user:ask_user`, so the builder can ask a clarifying question
instead of guessing when a description is ambiguous. Opt-in via
`hugin create --interactive`; the default stays non-interactive so scripted and
test runs are unaffected.

---

## Phase 5 — Trace-driven improvement

The goal: run a generated agent for a while, then have the creator read its
Hugin traces and improve it.

### 5.1 `analyze_traces`

```python
def analyze_traces(
    storage_path: str,
    stack: "Stack",
    agent_name: Optional[str] = None,
    config_name: Optional[str] = None,
    limit: int = 50,
) -> ToolResponse
```

Uses the existing `Storage` API (`list_sessions`, `list_agents`,
`list_interactions`, `load_interaction`) against a `LocalStorage` rooted at
`storage_path`. Computation is **deterministic aggregation, not LLM
summarisation** — the LLM sees a compact report, never raw traces (a single run's
interactions can be megabytes).

Metrics:

| Metric | Why it drives an improvement |
|---|---|
| `finish_type` distribution (`success`/`failure`, from `builtins.finish`) | Baseline success rate |
| Runs terminating by step exhaustion rather than `finish` | Prompt or tool-loop problem |
| Steps-to-finish distribution (p50/p90/max) | Efficiency; a rising p90 means the agent is flailing |
| Per-tool call count and error rate, with top-N distinct error messages | Points at the specific tool to regenerate |
| Tools in the config never called across all runs | Dead tools to delete from the config |
| Tool results exceeding N chars | Violates the builder's own token-efficiency rule; rewrite to return a path |
| Repeated identical `ToolCall` (name + args) within one run | Detected loops |
| Tasks whose `AskOracle` produced no tool call | Prompt not landing |

Report shape (small, bounded — truncate every list to top-N):

```python
{"runs_analyzed": int, "success_rate": float,
 "step_exhaustion_rate": float, "steps": {"p50": int, "p90": int, "max": int},
 "tools": [{"name": str, "calls": int, "errors": int,
            "top_errors": [str], "avg_result_chars": int}],
 "dead_tools": [str], "loops_detected": [{"tool": str, "count": int}],
 "oversized_results": [{"tool": str, "max_chars": int}]}
```

Note in the docs that `HUGIN_CAPTURE_RENDERED_PROMPTS=1` enriches this
materially — with it, `OracleResponse` carries `rendered_system_prompt` and
`rendered_user_message`, so unresolved template references become visible as a
metric rather than a guess.

### 5.2 `improve_agent` task

`tasks/improve_agent.yaml`, `chain_config: agent_builder`:

1. `analyze_traces` on the target agent's storage.
2. `load_agent_files` on the agent directory (Phase 4).
3. Propose a ranked, *evidence-linked* change list — each proposed change must
   cite a metric (e.g. "delete `fetch_summary` from the config: 0 calls across 50
   runs"; "rewrite `render_report` to return a path: max result 41k chars").
4. Apply via the generate_* tools.
5. `validate_agent` → `write_agent_files(changed_only=True)` → `test_agent`.
6. `finish` with a before/after summary.

### 5.3 CLI

```bash
hugin improve <agent_path> --storage-path ./storage/<name> [--limit 50] [--dry-run]
```

`--dry-run` runs steps 1-3 and prints the evidence-linked proposal without
touching files. That is also the useful standalone mode: "what is wrong with this
agent?"

---

## Testing strategy

Follow the existing pattern — the three `tests/test_agent_builder_*.py` files use
direct tool invocation with fixtures from `tests/conftest.py`, and `MockModel`
for LLM calls.

| Phase | Tests |
|---|---|
| 1 | `test_validate_agent.py`: one test per check, each with a deliberately broken fixture agent (bad template ref, unresolvable tool, undeclared Jinja var, malformed signature, missing dependency) plus a known-good fixture that must pass clean. `test_write_agent_files_safety.py`: existing non-empty dir is never destroyed; `overwrite=True` produces a `.bak.<ts>`; `dry_run` writes nothing. |
| 2 | Both knowledge surfaces resolve the same path; every reference named in `SKILL.md` exists; `search_examples` finds a known string in a known example. |
| 3 | Build each architecture with `MockModel` and assert the emitted YAML contains the expected fields and passes `validate_agent`. |
| 4 | Round-trip: `load_agent_files` → regenerate one file → `write_agent_files(changed_only=True)` touches exactly one file and leaves an unrelated hand-added file intact. |
| 5 | `analyze_traces` against a synthetic storage directory built by running a fixture agent with `MockModel`, asserting each metric. |

Every phase must pass `uv run pre-commit run --all-files` and `uv run pytest -x -q`.
Note: the mypy hook has a known pre-existing failure on `openai/_client.py`
unrelated to this work.
