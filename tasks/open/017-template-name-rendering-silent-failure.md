---
github_issue: null
title: Bare template-name references in task.prompt and config.system_template silently send the literal name to the LLM
state: OPEN
labels: [bug, prompts]
author: erikarne
created: 2026-05-09
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
