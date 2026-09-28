---
title: Chained tasks drop declared parameters — a successor's required parameter arrives as None
state: ongoing
claimed_by: codex/task037
claimed_at: 2026-09-28T09:57:44Z
branch: task/037_chained_parameters
labels: [bug, framework, agent-builder, validation]
priority: high
---

# Chained tasks drop declared parameters

## Context

`TaskChain` injects the previous stage's result under `pass_result_as` and
nothing else. A successor that declares any other parameter — including one the
first stage was given, and including one marked `required: true` — receives it
with no value, and `{{ param.value }}` renders as `None`.

Nothing catches it: not the framework, not `hugin validate`, not the agent
builder's LLM review stage.

## Evidence

From a generated two-stage agent (`release_notes_writer`, built 2026-08-24) run
with `--parameters '{"commit_file": "…", "version": "0.3.0"}'`:

```
### TaskDefinition classify_commits_task   (stage 1)
    commit_file: value='/tmp/.../commits.txt'
    version:     value='0.3.0'

### TaskDefinition write_release_notes_task (stage 2)
    version:            value=None            <-- declared required
    classified_commits: value="{'finish_type': 'success', …}"
    _chain_sequence_index: value='0'
```

Stage 2's prompt therefore rendered `Release version: None`. The output was
still correct — the model wrote `# Release 0.3.0` — but only because stage 1's
*result text* happened to say "Classified 28 commits for release 0.3.0", and the
model recovered the version from the blob passed as `classified_commits`. That
is luck. A stage 1 that summarised itself differently would have produced
release notes titled `# Release None`.

## Cause

`interaction/task_chain.py:113-127`:

```python
new_params = deepcopy(task_template.parameters)     # schema only, no values
if self.previous_result and current_task.pass_result_as:
    ...                                              # only this one gets a value
```

Values live on the *current* task's parameters and are not carried into the
successor. The chained `Task` is otherwise built from the registry template, so
every declared parameter starts empty.

There is no runtime complaint. Parameter validation runs when an agent is
created from a task (`AGENTS.md`, "Task Parameters": *"Required parameters must
be provided or task creation fails"*), and a chained stage does not go through
that path — worth confirming as part of this task, since a required parameter
silently becoming `None` is the surprising half of this bug.

## Why both gates missed it

- `validate_agent._check_task_chains` (`tools/validate_agent.py:731`) checks that
  every name in a `task_sequence` resolves to a task that exists, and that
  `chain_config` resolves to a config. It does not check that a successor's
  **required** parameters can be supplied by anyone. The agent validated with 0
  errors and 0 warnings.
- The builder's reviewer stage read the preview and returned APPROVED, calling
  out that "task parameters match exactly what was requested" — the reviewer
  cannot see runtime parameter flow, and its prompt tells it the mechanics are
  already guaranteed by the validator.

So the failure is not that a model wrote a bad agent; it is that a legitimate,
documented-looking chain has a hole neither gate covers.

## Options

Not mutually exclusive; pick deliberately.

1. **Carry values forward in `TaskChain`.** A successor parameter with no value,
   whose name matches a parameter on the current task, inherits that value.
   Cheap, and matches what anyone writing `version` in both stages expects.
   Needs a decision on shadowing: does an explicit `default` on the successor
   win over the inherited value?
2. **Make the validator refuse it.** Flag a successor whose `required: true`
   parameter has no `default`, is not the `pass_result_as` target, and is not
   supplied by option 1. This is the check that would have caught it before any
   file was written.
3. **Teach the builder the rule.** Whatever the framework ends up doing, the
   system template and `generate_task`'s guidance should state it, so generated
   chains stop relying on the successor's prompt to re-derive values from a
   result blob.

Option 2 is worth doing regardless of 1, since it also covers hand-written
agents.

## Tasks

- [x] Confirm what a chained stage does today with a required parameter that has
      no value — silently `None`, or an error that is being swallowed.
- [x] Decide between carrying values forward, refusing at validation, or both.
- [x] Implement, with tests covering: value inherited by name, `pass_result_as`
      still wins for its own name, and a successor `default` interacting with an
      inherited value.
- [x] Add the validator check for an unsatisfiable required successor parameter.
- [x] Update the builder's guidance (`templates/builder_system.yaml`,
      `tasks/build_agent.yaml` step 5) to match whatever the framework does.
- [x] Update `AGENTS.md`'s "Task Parameters" and the `pass_result_as` note to
      state the rule.

## Outcome

- [x] A two-stage agent whose second stage declares a parameter the first stage
      was given either receives that value, or fails to validate — not `None` at
      run time.
- [x] `hugin validate` reports an error for a chain that cannot supply a
      successor's required parameter.
- [x] The eval's golden set includes a multi-stage case that would fail if the
      value were dropped.

## Plan

- Resolve each successor from a cloned registry task. Carry non-None values
  only into parameters declared by that successor; inherited values override
  its defaults/existing values, and `pass_result_as` overrides both. Preserve
  raw result dictionaries for compatibility with existing string-declared
  result parameters, including empty result dictionaries.
- Apply the existing input conversion and required-parameter validation before
  switching config or adding the next TaskDefinition. Copy mutable values so
  neither the predecessor nor registry template is changed. Read the current
  task from the interaction's branch when chaining.
- Extend static validation to follow actual sequence order and next-task
  links. A required successor input must have a local value/default, a possible
  inherited value, or the immediate predecessor's result. Track availability
  through intervening stages and injected undeclared result parameters; avoid
  infinite traversal of cycles. Optional entry inputs are possible sources,
  with runtime validation deciding whether they were actually supplied.
- Add red/green runtime and validator tests for required values, defaults,
  falsy and mutable inputs, result precedence, branch isolation, sequences,
  cycles, and malformed schemas. Add a release-version pipeline to the golden
  set and a deterministic real-session regression that checks its second
  stage's rendered prompt without relying on an LLM to recover the version.
- Document the precedence and declaration rule in AGENTS.md and the builder's
  system/task/tool guidance. Run focused checks, the full suite, all-file and
  changed-file pre-commit checks, and a review panel before opening the PR.

## Implementation and verification

- Chained tasks clone the receiver, carry only declared non-None inputs with
  independent copies, inject `pass_result_as` last, and use the existing input
  conversion/required-parameter checks before changing config or stack state.
- Both TaskResult and TaskChain look up the task on their own branch. Registry
  templates and predecessor values remain unchanged, including mutable inputs.
- Static validation follows configured chain entry paths and sequence order,
  tracks available declared and injected parameters through intermediate
  stages, checks shared-predecessor paths independently, and terminates on
  cycles. Optional entry parameters are possible caller inputs; runtime checks
  whether they were actually supplied.
- Added 32 regression cases across parameter inheritance and the golden release
  pipeline. The golden set now includes `versioned_release_pipeline`; its
  deterministic runtime test asserts the second-stage prompt contains the
  exact version while the first-stage result contains no version. This does
  not claim a live builder-model evaluation; the existing eval harness scores
  generated artifacts statically.
- Red/green coverage reproduced the original parameter-loss and validation
  failures. The final full suite passes: **1,761 passed, 53 skipped**, using
  `TMPDIR=/private/tmp uv run pytest -x -q`.
- Manual CLI check: `hugin validate` returns 1 and names the missing `version`
  on a broken two-stage chain, then returns 0 with no warnings when the
  predecessor declares that input.
- Repository-wide pre-commit findings remain the existing baseline: 113 flake8
  findings, one missing return annotation in `scripts/sync_packaged_examples.py`,
  and four detect-secrets findings in existing replay/trace-analysis tests.
  All hooks pass on the 13 changed files. No checks are disabled and no
  secret baseline changes are included.

## Review

The panel covered runtime correctness, validator/test validity, and
maintainability. All three reviewers found the same P2 edge case: an empty
`task_sequence` must fall back to `next_task`, matching runtime execution.
Normalized that case, added a regression that failed before the fix and passed
with it, and reran the full suite. No other blocking findings remained.

## Conversation

### note · codex/task037 · 2026-09-28T10:15:43Z

Implemented and panel-reviewed; all 32 new regressions and the full suite pass.
Precedence is result injection, inherited value, then local value/default.
The CLI now rejects chains with an unsourced required input. Preparing the PR.
