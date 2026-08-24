---
title: Chained tasks drop declared parameters — a successor's required parameter arrives as None
state: OPEN
labels: [bug, framework, agent-builder, validation]
priority: high
---

# Chained tasks drop declared parameters

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
created from a task (`CLAUDE.md`, "Task Parameters": *"Required parameters must
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

- [ ] Confirm what a chained stage does today with a required parameter that has
      no value — silently `None`, or an error that is being swallowed.
- [ ] Decide between carrying values forward, refusing at validation, or both.
- [ ] Implement, with tests covering: value inherited by name, `pass_result_as`
      still wins for its own name, and a successor `default` interacting with an
      inherited value.
- [ ] Add the validator check for an unsatisfiable required successor parameter.
- [ ] Update the builder's guidance (`templates/builder_system.yaml`,
      `tasks/build_agent.yaml` step 5) to match whatever the framework does.
- [ ] Update `CLAUDE.md`'s "Task Parameters" and the `pass_result_as` note to
      state the rule.

## Success Criteria

- [ ] A two-stage agent whose second stage declares a parameter the first stage
      was given either receives that value, or fails to validate — not `None` at
      run time.
- [ ] `hugin validate` reports an error for a chain that cannot supply a
      successor's required parameter.
- [ ] The eval's golden set includes a multi-stage case that would fail if the
      value were dropped.
