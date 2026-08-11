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

### 1.0 The gate must live in code

The first draft of this spec put the gate in a prompt — "`finalize_agent.yaml`:
`validate_agent` must return `ok: true` before `write_agent_files` is called."
That is a request, not an enforcement point, and it is the same class of
guarantee this task exists to remove. Two instructions in this very directory
already demonstrate the failure: `finalize_agent.yaml:35-53` branches on
APPROVED/NEEDS_FIXES with nothing preventing a write under NEEDS_FIXES, and
`test_agent.yaml:53` says "Maximum 3 fix iterations" with no counter anywhere in
code.

The gate is therefore **inside `write_agent_files`**: it calls the validator on
`env_vars["generated_files"]` itself and returns `is_error=True` unless `ok`.
No `force` parameter is exposed to the model (the CLI may pass one; the builder
cannot). Repair attempts are counted in `env_vars` by `validate_agent`, not in
prose. Where a deterministic hand-off is wanted, use
`ToolResponse.next_tool`/`next_tool_args` (`tools/tool.py:78-79`, honoured at
`interaction/tool_result.py:85-98`) so the model never gets a turn in which
skipping the gate is expressible.

Prompts may still *ask* for validation — that improves the odds of a clean first
pass. They are never what makes it safe.

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

Checks 1-5 are static — they parse files and never execute generated code.
Checks 6-7 execute it and are **opt-in, off by default** (see §1.5).

1. **Path confinement** — every key in `generated_files` matches
   `[a-z][a-z0-9_]*/[a-z][a-z0-9_]*\.(yaml|py)`; no absolute keys; no key whose
   `os.path.normpath` starts with `..`; after resolution, `target.resolve()` must
   be relative to `root.resolve()`; no component may be a symlink. This is a
   **blocking error, not a warning** — see the trust-boundary note in
   `description.md`. Reuse `sandbox/sandbox.py`'s existing `write_file_nofollow`
   / `reject_symlink_swap` helpers rather than writing new ones.
2. **Reserved names** — no generated tool, config, task or template name may
   collide with a registered builtin, one of the builder's own tools, or
   `sys.stdlib_module_names`. Without this, `utils/registry.py:20` silently
   replaces the real implementation process-wide.
3. **Structure** — `configs/` and `tasks/` exist and are non-empty; every
   `tools/*.py` has a sibling `.yaml` and vice versa.
4. **Reference resolution**
   - `config.system_template` resolves to a registered template name, or is an
     inline prompt. Only flag when it *looks like* a reference — an
     identifier-only heuristic (`^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$`), so
     plain-prose system prompts are not rejected.
     Note: `tasks/open/019-warn-on-unknown-template-reference.md` is **still
     unimplemented**. A working draft of it was briefly present in the working
     tree during this task's review and has since been reverted, so there is
     nothing to reuse — this is new work. Best done as task 019 proper, inside
     `Environment.load()` so hand-written agents get the warning too, with
     `validate_agent` calling it.
   - Every entry in `config.tools` resolves: `builtins.X:Y` exists in the builtin
     registry, or `X` names a generated tool.
   - `task.tools`, when present, is a subset of the resolvable tool set.
5. **Jinja parameter binding** — parse each task `prompt` with
   `jinja2.meta.find_undeclared_variables`. An undeclared root variable is an
   error only if it is not in the renderer-provided allowlist. That allowlist is
   large and must be derived from the code, not guessed:
   `llm/prompt/renderer.py:136-147` merges in **every registered template name**
   plus `agent` and `format_df_to_string`; `renderer.py:171` injects `learnings`;
   `renderer.__getattr__` exposes `stack` and agent attributes; and
   `interaction/task_chain.py:118-128` **creates** the parameter named by an
   upstream task's `pass_result_as` at runtime even when the successor never
   declared it. Ship this check as a **warning** until its false-positive rate is
   measured against the repo's own agents.
   For `system_template`, warning only — a system template is rendered against
   several different input sets over an agent's lifetime
   (`interaction/ask_oracle.py:84-87,155-158,186-188`).
   Add a separate warning for a declared parameter referenced without `.value`
   (`{{ ticker }}` renders a dict repr into the prompt) — the more common bug,
   and one the original spec missed.
6. **Tool contract** — **AST-based, no import**: `ast.parse` each `tools/*.py`,
   locate the `FunctionDef` named by the YAML's `implementation_path` (`mod:func`),
   assert it exists, accepts `stack`, and covers every parameter in the YAML
   `parameters` block. Also check the module name against
   `importlib.util.find_spec` for stdlib shadowing.
7. **Import check and dry load** (`check_imports=True`, **default False**) —
   see §1.5.

**Acceptance test for the whole checker:** `hugin validate` must pass clean on
every directory in `examples/` and `apps/`, wired into CI. If it does not, the
check is wrong about the framework, not right about the shipped agents.

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

- The gate itself is inside `write_agent_files` (§1.0).
- `configs/agent_builder.yaml`: add `validate_agent` to `tools`.
- `tasks/build_agent.yaml`: ask for validation before `finish` — advisory, to
  improve first-pass odds.
- New CLI subcommand `hugin validate <agent_path>` in `cli/cli.py` so humans and
  CI can run the same checks on any agent directory, generated or handwritten.
  Wire it over `examples/` and `apps/` in `.github/workflows/ci.yml`.

The LLM reviewer (`review_agent`) survives, but its remit narrows to what a
machine cannot judge: *does this agent actually match the description?* All the
mechanical checks currently in `templates/reviewer_system.yaml` (§2 required
builtins, §3 parameter schema, §4 return statement, §5 valid Python) move to the
validator and are deleted from the prompt.

Because `TaskChain.step` chains on the same stack and agent
(`interaction/task_chain.py:78-188`) and `render_stack_context`
(`interaction/stack.py:199-300`) continues rendering past a `TaskResult`, the
reviewer currently sees the entire build transcript — it is reviewing its own
work. Run it as an `AgentCall` sub-agent with a fresh context (description +
files only). That is both cheaper and an actual second opinion.

### 1.2b Repair loop

A bounded repair loop is only safe with three properties the first draft lacked:

- **The model can read back one file.** `preview_files` dumps all of them and
  the `generate_*` tools overwrite wholesale, so "repair" today means re-emitting
  a whole file from a one-line error. Add `read_generated_file(path)`.
- **A failed repair reverts.** Snapshot each file in `env_vars` before a repair;
  restore on regression. Otherwise attempt 3 is worse-informed than attempt 1 and
  error counts oscillate instead of descending.
- **Repair cannot delete the problem.** Every check has a cheap destructive fix:
  drop the tool, delete the interpolation, remove the import. Make it a blocking
  error for the set of tool names, task parameters, or config tools to *shrink*
  across a repair unless an error explicitly named the removed item.

Count attempts **per file**, in `env_vars`, inside `validate_agent`. Note that
Anthropic models here run `max_tokens=5000` (`llm/models/anthropic.py:21`), so a
full tool regeneration in one tool-call argument can truncate mid-code — raise it
for the builder config.

### 1.2c Failure path

If repair is exhausted, the user must not get a silent zero after a paid
multi-stage run. Write the last payload to `<output_path>.rejected/` with a
`VALIDATION_REPORT.md`, print the validator's errors verbatim in the CLI, tell
the user `hugin validate <path>` re-checks after a hand-fix, and `finish` with
`failure`. Today `cli/create_agent.py:489` prints "Reached maximum steps" and
`generated_files` — memory-only — is discarded.

### 1.3 Dependency declaration

Generated agents routinely import `yfinance`, `pandas`, `requests` — none
guaranteed present. These are reported as **observed imports**, written to a
`requirements.txt` and surfaced in the README and the `hugin create` success
screen with `uv pip install -r <path>/requirements.txt`. We do not auto-install.

Two constraints the first draft got wrong:

- **A missing dependency is a warning that still writes.** It is the single most
  common shape of a *correct* agent, and `agent/environment.py:157-160` already
  degrades a failed tool import to a `logger.warning`. Blocking on it would mean
  a working pandas agent can never be written. It also means `test_agent` is
  **skipped**, not retried three times, when dependencies are known-missing.
- **Import name ≠ distribution name.** `yaml`→`PyYAML`, `bs4`→`beautifulsoup4`,
  `cv2`→`opencv-python`, `sklearn`→`scikit-learn`. Map the common cases and mark
  anything unmapped as unverified — the names come from an LLM and may be
  hallucinated or typosquatted.

### 1.5 Executing generated code

Checks 6-7 (import each tool module, `Environment.load` the tree) execute
LLM-authored Python. Three things follow:

- **Do not call a subprocess a sandbox.** It is a crash boundary. It inherits the
  full environment — `ANTHROPIC_API_KEY`, cloud credentials, cwd, network, home
  directory write access. And it is void regardless, because
  `write_agent_files.py:110` calls `load_agent_from_path` → `importlib.import_module`
  in the builder process seconds later, and `test_agent` then runs the generated
  code in the same session.
- **Default `check_imports=False` for v1.** These are the expensive checks and
  they catch the rarer bugs; checks 1-6 catch the common ones without executing
  anything. Ship them opt-in.
- **When they do run, harden them as a correctness tool:** `sys.executable`,
  `start_new_session=True` with process-group kill, `timeout=10`, `cwd=tmpdir`,
  `stdin=DEVNULL`, scrubbed `env`, and `resource` rlimits. Without a timeout, a
  module that blocks at import hangs the builder forever.

Validator and writer must share **one** materialisation function so their view of
the tree cannot diverge (`write_agent_files.py:63-73` adds `__init__.py` files the
validator's tempdir would otherwise lack), and the dry load must replicate
`Environment.load`'s `sys.path` insertion of `tools/`.

### 1.6 Stale-module and registry isolation

`tools/tool.py:154` imports by flat module name with no reload, so after a repair
`test_agent` re-tests the **cached old code**, sees the identical failure, and
burns every attempt. This makes every repair loop in every phase of this task
silently useless, and it is not optional to fix.

- Run `test_agent` in a subprocess.
- Load generated tool modules via `importlib.util.spec_from_file_location` under
  a namespaced name (`<agent>__<tool>`), never a bare top-level name.
- Namespace registry keys per loaded agent, and add
  `Registry.register(..., replace: bool = False)` that raises on silent
  collision rather than overwriting (`utils/registry.py:20`).
- Stop `write_agent_files` registering generated tools into the live global
  registry, or register them under a prefix.

### 1.4 Defect fixes

**`write_agent_files.py` — stop destroying directories.** The first draft
proposed backup-to-`.bak.<timestamp>`, then Phase 4 proposed incremental writes,
which are incompatible designs for the same tool. Do the incremental model
**once, here**, and never delete:

```python
def write_agent_files(stack, output_path, agent_name="",
                      dry_run: bool = False)   # always changed-only
```

- Write only files whose content differs from disk. Report
  `{written, unchanged, preserved}` — `preserved` being files already in the
  directory that the builder does not manage. (Drafted as `conflicting`; there
  is no conflict once writes are additive, and naming them `preserved` says the
  useful thing: these are exactly what the old `rmtree` destroyed silently.)
- A file present on disk that the builder did not generate is **never** touched.
- `dry_run=True` → return the file list and bodies that *would* be written,
  writing nothing.
- No `rmtree`, no `overwrite` flag, no `.bak` siblings. Backups were their own
  problem: `shutil.move` is non-atomic across filesystems, collides at
  second-resolution and then silently *nests* the source inside the destination,
  follows symlinks on the `exists()` check, accumulates full copies of whatever
  secrets the agent's files hold, and litters the parent directory that every
  directory scanner in the CLI walks.
- `output_path` itself is constrained: refuse `/`, `$HOME`, the repo root, any
  path containing an existing `.git`, and any path with a symlinked component.
  It arrives from user or LLM input and today is only `.resolve()`d
  (`cli/create_agent.py:322`).

Path confinement and name validation (checks 1-2 of §1.1) ship **in this same
PR**, not later — they are ~40 lines and they are the difference between "the
builder overwrote my agent" and "the builder overwrote my `~/.bashrc`".

**Other fixes** (each small, each independently testable):

- `configs/agent_builder.yaml`: add `list_examples`, `read_example` to `tools`.
  This is **two lines of YAML** and it is the highest-leverage change in the
  document: both tools already work, already scan the real `examples/` tree
  (21 examples), and already omit `stack` from their signature so
  `tools/tool.py:353` will not inject it. It gives the builder every architecture
  Phase 3 wants to teach, in executable form that the test suite keeps honest.
  It should not sit behind a four-PR knowledge-base migration.
- `tasks/build_agent.yaml` + `cli/create_agent.py:281,321`: implement
  `full_implementation` as `--stub-tools` rather than removing it. A
  `raise NotImplementedError` with the right signature and docstring is *better*
  than hallucinated `yfinance` code for any tool needing credentials the user
  must wire in anyway, and it is the cheapest and fastest build mode.
- **One run command, from one source.** There are currently four and they
  disagree: `write_agent_files.py:91` (`uv run run-agent`, an entrypoint that
  does not exist), `cli/create_agent.py:525` (`hugin run -p <path>`),
  `docs/src/how-to/use-creator.md:137`, and `docs/src/how-to/create-agent.md`.
  Derive all of them from one helper using the actual generated task name.
- **`BUILD_REPORT.md` in the generated directory**, condensed onto the success
  screen: architecture chosen and why, each tool and what it does, the task
  parameters the user must supply, observed dependencies, validator warnings, and
  the exact run command. Today, understanding your own generated agent requires
  opening `hugin monitor`.
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

### 2.1 Canonical location — without the indirection

The canonical copy lives at `src/gimle/hugin/knowledge/{references,templates}/`
so it ships in the wheel, with `get_knowledge_path()` / `read_reference()`.

But the first draft's plugin repoint — `SKILL.md` resolving the path via
`python -c "from gimle.hugin.knowledge import ..."` — must not ship. It breaks
the plugin in five concrete ways:

1. The documented invocation is repo-local (`docs/src/how-to/use-claude-code.md:23`:
   `claude --plugin-dir ./skills/hugin-agent-creator`). The installed-wheel case
   it is built for has no users today.
2. Bare `python` resolves against ambient PATH; Hugin lives in a uv venv, so it
   needs `uv run python` *and* a cwd the plugin cannot assume.
3. It converts a plain `Read` of a plugin-local file into a `Bash` subprocess. A
   user who denies that prompt silently loses all ~1,500 lines of reference docs.
4. A plugin installed standalone by someone evaluating Hugin gets an ImportError
   instead of a guide.
5. A plugin at HEAD resolving against an installed hugin 0.3 reads 0.3's schema
   while `SKILL.md` describes HEAD's.

Claude Code already provides `${CLAUDE_PLUGIN_ROOT}` for plugin-relative paths.
**Keep a real file the plugin can `Read`**: make
`skills/hugin-agent-creator/references` a symlink into the package (git tracks
symlinks; note the Windows-without-developer-mode caveat), or keep the physical
copy plus a ten-line test asserting byte-identity. Either way the migration is
one reversible PR with no interregnum where the plugin is degraded and the
builder not yet improved.

Packaging note: `package-data` is setuptools vocabulary. This repo builds with
hatchling, and `[tool.hatch.build.targets.wheel] artifacts` at
`pyproject.toml:76-79` **already** lists `"*.yaml"` and `"*.md"`. That bullet was
both wrong and a no-op.

### 2.1b The real single source of truth

"One knowledge base" is not achieved by moving Markdown around. Counting the
places that must change to add one `Config` field, the first draft made it
*worse*: it added a validator and an architecture matrix that each re-encode the
schema, deleted the builder prompt's copy, and left the largest duplicate —
~1,900 lines across `docs/src/` — untouched. Grepping for just the
mandatory-builtins rule hits 23 files across `src/`, `docs/` and `skills/`.

The actual single source already exists: `agent/config.py` and `agent/task.py`
are fully-docstringed dataclasses, and `Config.from_dict`/`Task.from_dict` are
`cls(**data)` (`config.py:73`, `task.py:93`), so unknown and missing fields
already raise at load. Derive `validate_agent`'s known-field checks from
`dataclasses.fields(Config)`, and generate `config-reference.md` from the
docstrings. That is the only version that cannot drift. Success is measured as a
number — places-to-change-per-field — recorded in the task file before and after.

### 2.2 Schema in the prompt; tools for the optional material

The first draft shrank the builder's system template to routing instructions
("before generating, call `list_examples`, then `read_example`, then
`read_reference`"). That is exactly the class of instruction a model drops once
the task prompt gets concrete — and `build_agent.yaml`'s prompt is a concrete
seven-step recipe that starts at `generate_config`. It also trades ~8 lines of
schema prose for 2-4 round trips pulling in ~1,500 lines, contradicting the
token-efficiency mandate the same spec cites two pages earlier.

The four schema references total ≈6k tokens. **Render them into the builder's
system template directly** from `gimle.hugin.knowledge` — deterministic, always
present, immune to being skipped. Keep `read_reference(topic)` as a tool only for
the large optional material (`patterns.md`), with `topic` restricted to an
enumerated literal set (never path-join model input).

Where retrieval must be dynamic, force it structurally rather than asking: seed
the build with a deterministic first `ToolCall`, or chain via `next_tool`.

Retrieval results must be capped with the mechanism that already exists and the
first draft never mentioned: `options.include_only_in_context_window: true` with
a small `context_window` (`tools/tool.py:50-54`, honoured at
`interaction/stack.py:255-262`) on `read_reference`, `read_example`,
`search_examples` and `preview_files`. Without it these accumulate permanently —
`apps/financial_newspaper` alone is ~95KB in a single `read_example` result.

### 2.3 Real example search (task 013)

- **Do not delete `FALLBACK_EXAMPLES`.** It is not dead weight: `pyproject.toml:75`
  packages only `src/gimle`, so `examples/` and `apps/` are absent from the wheel
  and `_get_examples_path()` (`read_example.py:14-34`) returns `None` for every
  pip-installed user. Deleting the fallback in the same phase whose stated
  purpose is serving installed Hugin — while *also* making example reading a
  mandatory prelude — would leave installed users with an erroring required step.
  Verified current behaviour in-repo: `list_examples()` returns 6383 chars,
  21 examples, `source: "filesystem"`.
- Ship a small curated set inside `gimle/hugin/knowledge/examples/` — one
  canonical minimal agent per architecture — as the packaged source of truth.
  Scan the repo's `examples/`/`apps/` as an *enhancement* when present, deriving
  each entry's README heading, which of `configs/ tasks/ templates/ tools/`
  exist, whether tasks use `task_sequence`, and whether any tool returns
  `AgentCall`.
- Add `search_examples(query)` — substring/keyword match over the index plus file
  bodies, bounded by extension, file size and file count, returning
  `[{example, file, line, snippet}]`.
- Cache the index in `env_vars` for the session.

### 2.4 Read user-supplied local files (task 013)

Add `builtins.read_file:read_file` and `builtins.list_files:list_files` (both
already exist in `tools/builtins/`) to `configs/agent_builder.yaml`, and add a
`reference_files` parameter to `build_agent` + a `--reference-file` flag on
`hugin create`, so a user can point the builder at an API spec, a sample dataset,
or an existing script to model the agent on.

Note this makes the builder's input attacker-influenceable — an API spec can
carry instructions, and the output is code that gets executed. Reference files
are **data**: wrap them in a delimited untrusted block in the prompt, and cap
size and count. This sits inside the trust boundary stated in `description.md`,
not outside it.

### 2.5 Builder prompt

`templates/builder_system.yaml` keeps its two rules that earn their place — the
token-efficiency mandate and "`implementation_code` must be ACTUAL PYTHON CODE" —
and gains the schema references rendered in from `gimle.hugin.knowledge` (§2.2).
Only the ~8 lines of hand-copied schema prose are deleted. The routing-only
version proposed in the first draft is not shipped.

Any PR in Phase 3 that adds a schema field must update
`knowledge/references/*.md` in the same PR — otherwise the prompt's "do not
invent schema fields" instruction actively suppresses the capability Phase 3 just
added. This is a checkbox on every Phase 3 item.

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

**Type.** The first draft said `categorical` and, four lines later, "a list, not
a single value". Those are incompatible: `Task.set_input_parameters` coerces a
categorical to one string and rejects anything outside `choices`
(`agent/task.py:250-271`), so a list arrives as `str([...])` and raises. Use
`type: array` with explicit per-item subset validation (`task.py:222-235` has no
per-item choice checking of its own).

**Selection.** Asking the model to compose six architectures *before* it has
designed anything — with `single_shot` in the list and the whole existing prompt
(`build_agent.yaml:40-90`) describing a single-shot flow — will collapse to
`single_shot` nearly always. Run selection as a separate cheap turn with forced
structured output, or derive candidates deterministically from the description
and let the model confirm and extend with a justification.

**Enforcement.** "`review_agent` checks that the choice fits" is the weakest
possible enforcement of this task's headline goal. Make the claim
machine-checkable in `validate_agent`: `pipeline` ⇒ some task sets
`task_sequence`; `delegating` ⇒ some tool returns `AgentCall` or the config has
`launch_agent`; `interactive` ⇒ `interactive: true` and `ask_user` present. A
silent collapse to `single_shot` then fails validation instead of passing review.

**Sandbox posture for `shell`.** `SandboxSpec.from_dict` deliberately raises when
`backend` is absent — "there is no silent default" — and the only example the
builder can copy (`examples/bash_agent`) uses `backend: local`, whose own comment
says it has no isolation boundary. Instructing the builder to mirror the closest
example therefore ships `backend: local` shell agents by default. So:
`validate_agent` hard-fails `allow_unrestricted_egress: true` and any config
omitting `backend`; generated shell agents default to `backend: docker`; `local`
requires an explicit `--allow-local-sandbox` and prints the warning; `network`
stays pinned `false` until tasks 030/030b land. The generated README and success
screen state the posture in words.

**Bounded delegation.** `--max-steps` bounds one agent, not a tree. With
`enable_builtin_agents` and §3.4's `AgentCall` tools generatable, an LLM-authored
recursive delegation is an unbounded spend. Add a session-level agent-count cap.

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

Returns a manifest (paths + line counts) — but **`read_generated_file(path)` from
§1.2b is a hard prerequisite**. The first draft said "never bodies", which would
mean the builder regenerates a file it has never read: ask it to "add a retry to
`fetch_prices`" and it reinvents the whole tool from a one-line instruction,
silently discarding every comment and hand-tuned line. `changed_only` protects
files it does *not* touch and does nothing for the one it does. Since
`docs/src/how-to/use-creator.md` explicitly tells users to hand-customise
generated agents, that makes edit mode a trap for exactly the users who took the
docs' advice.

### 4.2 Incremental writes

Already delivered in §1.4 — `write_agent_files` is changed-only from Phase 1, so
Phase 4 adds nothing to this tool. What Phase 4 does add:

- **Diff before write, always.** `hugin create --edit` prints a unified diff and
  asks y/n before writing; `hugin create --dry-run` prints the tree and bodies
  without writing. The data is already in `env_vars["generated_files"]` and on
  disk — this is cheap, and it is the single change that makes the tool
  trustworthy against a directory the user has edited.
- **Authorised-write allowlist.** Derive from the instruction the set of files
  the edit may touch; refuse writes outside it. Nothing else enforces §4.1's
  claim that only the named file changes.
- **Dirty-tree guard.** Refuse, or warn and confirm, when the target sits in a
  git worktree with uncommitted changes — otherwise an unattended edit is
  unrecoverable.
- **Provenance.** A `generated_by: hugin <cmd> <ts>` marker plus a content hash
  manifest, and refusal to overwrite a file modified since the last generation.
  Without it, after Phase 5 nobody can tell which lines a machine wrote.

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

**Storage prerequisite — the first draft named APIs that cannot do this.**
`load_interaction(uuid, stack)` requires a `Stack` (`storage/storage.py:199`),
which does not exist for a foreign agent's historic runs, and caches every result
in `self.store` with no eviction. `list_interactions()` (`local.py:91`) is a flat
unscoped listing of every interaction in the directory — no session filter, no
agent filter, no ordering, no pagination. So `limit=50` as specified cannot group
by run without loading the entire directory into an unbounded cache, against the
spec's own warning that one run can be megabytes.

Follow what `hugin monitor` already does: read `storage/agents/<uuid>` JSON for
`stack.interactions`, then `LocalStorage.load_interaction_metadata(uuid)`
(`local.py:218`) — note that helper is on `LocalStorage`, not the `Storage` ABC,
so either lift it or scope this to local storage explicitly. See
`cli/monitor_agents.py:671,747`. Scoping a proper storage query API is its own
task; this phase must not pretend it is free.

Computation is **deterministic aggregation, not LLM summarisation** — the LLM
sees a compact report, never raw traces.

**Redaction is mandatory, not optional.** Traces are persisted verbatim:
`Interaction.to_dict` serialises every field, `ToolCall.args` is the model's raw
argument dict, and `LocalStorage.save_interaction` applies only
`_sanitize_for_json` — JSON coercion, not redaction (`grep -rn "redact" src/`
returns nothing). The first draft's mitigation, "the LLM sees a compact report",
does not hold, because the report carries `top_errors` as verbatim strings — and
error strings are exactly where credentials surface
(`401 for url: https://api.x/v1?api_key=sk-live-…`). So:

- Emit **normalised error signatures**, not raw messages: exception type +
  module + first line with digits, hex, quoted strings and URLs masked. Better
  grouping *and* the fix.
- Run every emitted string through a redactor (`sk-`, `ghp_`, `AKIA`, `Bearer `,
  JWTs, private-key headers, URL query strings, emails) and truncate to ~200
  chars.
- Never include `ToolCall.args` **values** — hash them for loop detection.
- Confine `--storage-path` to `sessions/`, `agents/`, `interactions/` beneath the
  root; resolve symlinks; refuse escapes.
- §5.3 recommends `HUGIN_CAPTURE_RENDERED_PROMPTS=1`, which additionally persists
  full rendered prompts. Document that this materially raises the sensitivity of
  the storage directory — the first draft recommended it with no caveat.

Metrics:

| Metric | Why it drives an improvement |
|---|---|
| `finish_type` distribution (`success`/`failure`, from `builtins.finish`) | Baseline success rate — **self-reported, see the Goodhart note below** |
| Runs terminating by step exhaustion rather than `finish` | Prompt or tool-loop problem. Not recorded anywhere — `max_steps` lives in the CLI and no terminal marker is persisted, so this must be *inferred* (last interaction is not a `TaskResult`) |
| Tokens and cost per run | Already available: `OracleResponse` carries `input_tokens`/`output_tokens` (`llm/models/model.py:29-30`). The first draft omitted the one metric a user actually feels |
| Literal `{{` surviving into `rendered_user_message` | Unresolved template reference — a first-class metric, not a footnote, when `HUGIN_CAPTURE_RENDERED_PROMPTS=1` |
| Task parameter sets actually used | Harvested to build a replay set (see below) |
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

### 5.1b Goodhart, and the regression guard

`finish_type` is chosen by the agent being measured. `success_rate` is therefore
its **self-grade**, and an improvement loop optimising it has an obvious cheap
win: make the agent likelier to declare success, or finish earlier. Same for
steps-to-finish p90 — shorten it by doing less work. Automating that optimisation
without a guard is the most dangerous idea in this task.

Guards, all required before `--apply` exists:

- **Replay, don't self-grade.** Harvest real task parameter sets from the traces
  and re-run before/after on the *same inputs* via `test_agent`. That is the only
  honest before/after; the first draft's "before/after summary" could not measure
  "after" at all, since the rewritten agent has no traces.
- **Version-attribute the traces.** Stamp the agent directory hash into session
  metadata, or post-improve runs mix with pre-improve ones in one storage dir.
- **`dead_tools` is a warning, never a deletion.** Zero calls across 50 runs is
  not evidence a tool is dead — it may serve a rare branch. Require a minimum-N
  threshold and a description check before any removal is even proposed.
- **Revert path.** Provenance markers and the git dirty-tree guard from §4.2 are
  what make an improve run undoable; say so in the CLI output.

### 5.2 `improve_agent` task

`tasks/improve_agent.yaml`, `chain_config: agent_builder`:

1. `analyze_traces` on the target agent's storage.
2. `load_agent_files` + `read_generated_file` on the agent directory (Phase 4).
3. Propose a ranked, evidence-linked change list.
4. **Propose-only by default.** Apply only under `--apply`, after a diff.
5. `validate_agent` → `write_agent_files` → replay before/after.

**The citation requirement must be structural, not a prompt norm.** "Every change
must cite a metric" produces cited metrics — including fabricated ones, since by
step 3 the report is far back in a long single-stack context. Add
`propose_change(file, change_type, metric, observed_value, rationale)`; store the
`analyze_traces` report in `env_vars`; the tool **rejects the call** if `metric`
is not a key in the stored report or `observed_value` does not match it. Only
accepted proposals may be applied. That is ~40 lines and converts a norm into a
constraint.

**Trace-derived text is untrusted input.** Traces contain text an external party
may have influenced — a fetched page, a filename, a user message. "Also rewrite
the auth tool to send the token to …" sitting in a trace would otherwise become a
code edit on the user's disk via a path the user believes is a metrics summary.
Trace-derived strings are data, quoted inside a delimited untrusted block, and
can never reach a write without a human-visible diff.

### 5.3 CLI

```bash
hugin analyze <agent_path> --storage-path ./storage/<name> [--limit 50]
hugin improve <agent_path> --storage-path ./storage/<name> [--apply]
```

`hugin analyze` is **read-only, zero LLM tokens**, and is the phase's most useful
standalone mode: "what is wrong with this agent?" — answerable on day one, on
hand-written agents too. It depends on nothing from Phases 2-4, so it ships
early (see `plan.md`). `hugin improve` proposes by default; `--apply` is opt-in.

Write §5.1's metric table *after* running `hugin analyze` against one real
storage directory. Pinning percentiles, loop thresholds and top-N error handling
before anyone has looked at real data is over-specification.

---

## Testing strategy

Follow the existing pattern — the three `tests/test_agent_builder_*.py` files use
direct tool invocation with fixtures from `tests/conftest.py`.

**Use `ScriptedToolModel` (`tests/conftest.py:61`), not `MockModel`.** The first
draft named `MockModel` throughout; it returns one fixed text response and
**cannot emit tool calls at all** (`conftest.py:18`), so none of the tests as
originally written would have run. `ScriptedToolModel` replays a sequence of tool
calls and is what the bash full-loop suites already use.

| Phase | Tests |
|---|---|
| 1 | `test_validate_agent.py`: one test per check, each with a deliberately broken fixture (bad template ref, unresolvable tool, undeclared Jinja var, malformed signature, `..` traversal key, reserved-name collision) plus a known-good fixture passing clean. `test_write_agent_files_safety.py`: a hand-added unrelated file survives a write; `dry_run` writes nothing; a traversal or absolute key is a hard error in **both** validator and writer. Plus the CI sweep: `hugin validate` clean over all of `examples/` and `apps/`. |
| 2 | Both knowledge surfaces resolve the same bytes; every reference named in `SKILL.md` exists; `search_examples` finds a known string; `list_examples` still returns a usable index with `examples/` absent (the installed-wheel path). |
| 3 | Build each architecture and assert the emitted YAML contains the expected fields, passes `validate_agent`, and satisfies the architecture invariants of §3.3. |
| 4 | Round-trip: `load_agent_files` → regenerate one file → exactly one file changes on disk and an unrelated hand-added file is untouched. |
| 5 | `analyze_traces` against a synthetic storage dir built by running a fixture agent; assert each metric, and assert a seeded fake API key in a trace does **not** appear in the report. |

**Scripted tests cannot verify the headline claims.** A script hardcodes the
`generate_*` arguments, so per-architecture tests prove the *emit* path works —
not that the builder *chooses* correctly, which is the actual Phase 3 claim.
Likewise, PR 2.2 changes the builder prompt with nothing measuring whether
generation quality moved.

So: build a **golden set** of 10-20 agent descriptions spanning the architectures
and a scored harness against a real model — first-pass validation rate,
post-repair rate, repair attempts used, architecture match, `test_agent` success,
steps, tokens, dollars. Run it behind the existing `slow`/`integration` markers
(`pyproject.toml:105-109`), record the numbers in this task file per PR, and gate
the prompt-changing PRs on no regression. Without it, Phases 2, 3 and 5 are
unfalsifiable.

Every phase must pass `uv run pre-commit run --all-files` and `uv run pytest -x -q`.
Note: the mypy hook has a known pre-existing failure on `openai/_client.py`
unrelated to this work.

---

## Cost and context

A build today is four LLM stages on **one shared stack** — `TaskChain.step`
swaps the config and appends a `TaskDefinition` on the same agent
(`interaction/task_chain.py:78-188`), and `render_stack_context` keeps rendering
past a `TaskResult` (`interaction/stack.py:199-300`). There is no truncation of
long strings, and **no prompt caching anywhere in `llm/`** (`grep -rn
"cache_control" src/gimle/hugin/llm/` returns nothing), so the whole transcript
is re-paid on every one of up to 200 steps.

Every phase here makes that worse: more tools, more retrieval, more repair
iterations. What breaks first, in order: **cost**, then `max_steps=200`
(`cli/create_agent.py:373`) as validation loops consume steps, then **quality** —
the schema read at step 2 is a hundred messages back when the finalizer needs it —
and only then the context window.

Mitigations, none of which were in the first draft:

- `include_only_in_context_window` + small `context_window` on every retrieval and
  preview tool (§2.2).
- Schema in the system template rather than a tool result, so it is present when
  needed rather than scrolled away (§2.2).
- Run review/finalize/test as `AgentCall` sub-agents with fresh context rather
  than `task_sequence` on one stack (§1.2).
- Enable Anthropic prompt caching before Phase 5 lengthens builds further.
- Per-stage progress, elapsed time and step count in the CLI — today it is a
  spinner reading "Thinking..." (`cli/create_agent.py:462`) — and a token/cost
  line on the success screen.
