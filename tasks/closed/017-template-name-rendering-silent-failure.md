---
github_issue: null
title: Bare template-name references in task.prompt and config.system_template silently send the literal name to the LLM
state: CLOSED
labels: [bug, prompts]
author: erikarne
created: 2026-05-09
closed: 2026-05-11
resolution: Fixed in PR #42 (commit 7e116df) — see the Resolution section below.
---

# Bare template-name references silently send the literal name to the LLM

## Summary

Writing `prompt: research_prompt` (a bare template name) in a task YAML
or `system_template: builder_system` in a config YAML produces no error
and looks correct, but the LLM receives the **literal name string** —
not the rendered template content. Hugin's own test
(`tests/test_prompt.py:334`) shows the working pattern is
`"{{ research_prompt.template }}"`, but every YAML example in
`apps/agent_builder/configs/agent_builder.yaml` and friends uses the
broken bare-name form.

This is a silent-correctness bug. The agent still runs, the model
still emits tool calls, the session still completes — but it improvises
entirely from tool schemas because no actual instructions reached it.

## Reproduction

```python
# Run any task that uses a bare-name reference, intercept chat_completion.
from unittest.mock import patch

CAPTURED = {}
def fake(system_prompt, messages, tools, llm_model):
    CAPTURED.setdefault("system_prompt", system_prompt)
    CAPTURED.setdefault("messages", list(messages))
    return {"role": "assistant", "content": "stub", "tool_call": None,
            "tool_call_id": None, "input_tokens": 0, "output_tokens": 0,
            "extra_content": []}

# Build any session whose task YAML has `prompt: foo_prompt`
# and whose config has `system_template: bar_system`.
with patch("gimle.hugin.llm.completion.chat_completion", side_effect=fake):
    session.run(max_steps=1)

assert CAPTURED["system_prompt"] == "bar_system"          # bare name leaks
assert CAPTURED["messages"][0]["content"][0]["text"] == "foo_prompt"  # bare name leaks
```

Verified against `apps/agent_builder` (system prompt = `'builder_system'`,
14 chars) — the agent works in spite of this because tools like
`generate_config` / `generate_template` are leading enough that the
model improvises sensibly.

## Root cause

Two paths share the same root:

1. **System prompt** — `PromptRenderer.render_system_prompt()` calls
   `stack.get_system_template()`, which returns
   `agent.config.system_template` as a plain string (`"builder_system"`).
   That string is then passed to `render_prompt(prompt_text, inputs)`.
   `render_jinja_recursive("builder_system", inputs)` short-circuits
   because `contains_jinja("builder_system")` is False — the bare name
   has no `{{ }}` syntax, so it returns the name verbatim.

2. **User prompt** — When `AskOracle.create_from_task_definition` is used,
   it sets `prompt = Prompt(type="template", text=task.prompt)` (no
   `template_name`). `render_user_message` then takes the
   `template_name is None` branch and calls `render_task_prompt`, which
   does `task_prompt = task_definition.prompt; render_prompt(task_prompt, ...)`.
   Same short-circuit — the bare name is returned.

The pattern that does work — and is exercised by
`tests/test_prompt.py::test_render_prompt_with_template` — is
`"{{ template_name.template }}"`. Jinja then dereferences the registered
`Template` dataclass via `.template`, returns the content, and the
recursive renderer expands inner `{{ }}` against the live inputs.

## Impact

- `apps/agent_builder/configs/agent_builder.yaml` (and presumably every
  config that ships with Hugin) has a system prompt that never reaches
  the LLM. agent_builder works because tools carry the intent.
- Downstream apps (`apps/financial_newspaper/tasks/create_layout.yaml`
  uses `prompt: create_layout_prompt`) hit the same trap and ship
  silently broken.
- We hit this in `gimle-heimdall` PR #14 — spent ~half a day debugging
  why the model "ignored" the prompt before discovering it never
  arrived. Linked discussion / writeup is in
  `gimle-heimdall/docs/superpowers/specs/2026-05-08-insights-agent-topology-rework-design.md`.

## Suggested fixes (not mutually exclusive)

1. **Auto-lookup in `render_prompt`** — if `prompt_text` matches a
   registered template name exactly (no Jinja syntax), look it up and
   render `template.template` instead. This makes the naive YAML form
   work as users expect. Risk: shadowing if a user happens to write a
   string that collides with a template name.

2. **Validate at load time** — `Environment.load` could refuse to
   register a config/task whose `system_template`/`prompt` is a bare
   string that matches a known template name AND has no Jinja syntax,
   pointing the user at the `{{ X.template }}` form.

3. **Doc + audit** — fix every bundled YAML to use
   `"{{ X.template }}"`, add a section to the README/CLAUDE.md, and
   leave the renderer alone. Lowest-risk, highest-toil.

## Related observation (separate, smaller issue)

`OracleResponse` interactions store only the assistant response — not
the rendered system+user prompt that was actually sent. When the bug
above triggers, nothing in the persisted session reveals it; you have
to monkey-patch `chat_completion`. Worth logging the rendered prompt
on `AskOracle.step()` (gated by debug flag if it's verbose).

## Resolution

Implemented **suggested fix 1**: `PromptRenderer.render_prompt()` now
expands a bare `prompt_text` to the registered template's body when the
string contains no Jinja syntax and matches a template name exactly.
This covers both call paths (`render_system_prompt` and
`render_task_prompt`) at their single chokepoint, so all bundled YAML
that uses the bare-name form (every shipped config) now works
unchanged. `Prompt(type="template", template_name=...)` already
resolved correctly and is untouched.

Also documented the two equivalent reference forms (bare name vs.
`{{ X.template }}`), the shadowing escape hatch, and the one-shot nature
of bare-name expansion in `CLAUDE.md` -> Prompt Templates, and
reconciled the now-accurate docstrings on `Config.system_template`,
`Task.prompt`, and `Task.system_template`.

Fixed one template that had been relying on the broken behavior:
`apps/agent_builder/templates/builder_system.yaml` contained literal
example Jinja (`{{ param.value }}`) in its body as documentation. The
body was never rendered before, so it never blew up; now that it is
rendered the `param.value` attribute access on an undefined `param`
raises. Reworded it to prose (the recursive renderer cannot emit literal
`{{ }}` in its output — even `{% raw %}` gets re-rendered on the next
pass — so the example had to go). A smoke test renders every bundled
config's system prompt and every bare-name task prompt; all pass. (Note:
`apps/data_analyst`, `apps/financial_newspaper`, `apps/rap_machine`,
`apps/the_hugins` fail to load via `Environment.load(<relative path>)`
from an arbitrary cwd — a pre-existing tool-import path issue,
reproducible on `main`, unrelated to this change; their templates were
audited statically and contain only bare-variable interpolation, which
renders to empty strings rather than erroring.)

Tests added in `tests/test_prompt.py`:
`test_render_prompt_with_bare_template_name`,
`test_render_prompt_literal_text_not_a_template_name`,
`test_render_task_prompt_with_bare_template_name`,
`test_render_system_prompt_with_bare_template_name`, and
`TestSystemPromptReachesModel::test_bare_system_template_reaches_model`
(end-to-end: builds a session, runs a step with a patched
`chat_completion`, asserts the rendered body — not the literal name —
reaches the model).

### Out of scope / follow-ups

- The `OracleResponse` observation above (persist the rendered prompt
  for debuggability) — should become its own task; it's what turned
  this into a half-day debug in heimdall.
- Suggested fix 2 (load-time validation) is *not* implemented and is
  still worthwhile: a *misspelled* bare name (`system_template:
  basci_system`) still silently sends the typo to the LLM, because it
  matches no template and isn't Jinja. Worth a warning at
  `Environment.load`.
- `render_jinja_recursive` renders to a fixpoint of "no Jinja syntax
  left", so a template can never emit literal `{{ }}`/`{% %}` in its
  output (even `{% raw %}` only survives one pass). Fine today, but if a
  prompt ever legitimately needs to show Jinja syntax to the model,
  the recursive renderer needs a real escape mechanism (or a fixpoint /
  depth guard).
