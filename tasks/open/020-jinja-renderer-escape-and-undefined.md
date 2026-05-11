---
github_issue: null
title: render_jinja_recursive can never emit literal Jinja syntax; reconsider Undefined behavior
state: OPEN
labels: [enhancement, tech-debt, prompts]
author: erikarne
created: 2026-05-11
---

# Give the Jinja renderer an escape mechanism (and reconsider Undefined)

## The problem

`render_jinja_recursive` (`src/gimle/hugin/llm/prompt/jinja.py`) renders to a
fixpoint of "no `{{ }}` / `{% %}` / `{# #}` left in the string". Consequence:
a template can never produce literal Jinja syntax in its output —
`{% raw %}{{ x }}{% endraw %}` renders to `{{ x }}` on pass 1, then gets
re-rendered (and `{{ x }}` with `x` undefined renders to `''`) on pass 2.

This bit us in #42: `apps/agent_builder/templates/builder_system.yaml` had
`{{ param.value }}` in its body as a **documentation example** showing the
agent-builder LLM how to write task prompts. The template body was never
rendered before #42, so it never blew up; once #42 made bare-name system
templates actually render, `param.value` (attribute access on an undefined
`param`) raised `UndefinedError`. We reworked it to prose, losing the literal
example.

## What to consider

1. **Escape mechanism that survives recursion.** Honor `{% raw %}…{% endraw %}`
   non-recursively (strip the markers only on the *final* pass), or a sentinel
   token that's substituted back to `{{`/`}}` at the very end, or stop the
   recursion at a fixpoint (if a render pass changes nothing, stop) plus a
   max-depth guard.
2. **`Undefined` behavior.** `render_jinja` uses Jinja's default `Undefined`:
   `{{ x }}` with `x` undefined → `''` (silent), but `{{ x.attr }}` → raises.
   That's an inconsistent foot-gun (it's exactly what blew up in #42).
   Consider `jinja2.ChainableUndefined` so `{{ x.attr }}` also renders empty —
   or, conversely, `StrictUndefined` everywhere so *both* fail loudly (which
   pairs well with task 019). Pick one consistent policy.
3. **The agent-builder case specifically.** Once an escape mechanism exists,
   restore the literal `{{ param.value }}` example in `builder_system.yaml`.

## Success criteria

- [ ] A template body can include literal `{{ … }}` text that reaches the
      model verbatim, via a documented mechanism, with a test.
- [ ] `{{ undefined.attr }}` behaves consistently with `{{ undefined }}`
      (both silent, or both loud — decided and documented).
- [ ] Existing prompt-rendering tests still pass.

## Context

Follow-up noted in `tasks/closed/017-template-name-rendering-silent-failure.md`.
