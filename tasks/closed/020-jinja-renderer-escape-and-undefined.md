---
github_issue: null
title: render_jinja_recursive can never emit literal Jinja syntax; reconsider Undefined behavior
state: CLOSED
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

- [x] A template body can include literal `{{ … }}` text that reaches the
      model verbatim, via a documented mechanism, with a test.
- [x] A value passed via `template_inputs` can be marked literal so that any
      Jinja delimiters inside it reach the model verbatim and are never
      re-evaluated, with a test (the injection case task 021 depends on).
- [x] `{{ undefined.attr }}` behaves consistently with `{{ undefined }}`
      (decided: **both silent** via `ChainableUndefined`).
- [x] Existing prompt-rendering tests still pass.

## Resolution

Implemented in `src/gimle/hugin/llm/prompt/jinja.py`:

- **Literal escape via sentinels.** `{% raw %}…{% endraw %}` blocks and values
  marked with the new `literal()` helper have their delimiters swapped for NUL-
  wrapped sentinel tokens *before* the recursive render, then restored on the
  final pass — so literal Jinja survives recursion. `literal()` is stronger than
  `{% raw %}` for untrusted input: it holds even if the value embeds
  `{% endraw %}`. This is the seam task 021 ("dreaming") injects `{{ learnings }}`
  through.
- **Undefined policy = `ChainableUndefined`.** `{{ x }}` and `{{ x.attr }}` both
  render to `''` when undefined — consistent, low blast radius (existing
  `{% if optional.value %}` app templates and cold-start `{{ learnings }}` keep
  working). `StrictUndefined` was considered (pairs with task 019) but rejected
  for this PR as too disruptive.
- **agent-builder example restored.** `builder_system.yaml` again shows the
  literal `{% raw %}{{ foo.value }}{% endraw %}` example.

## Context

Follow-up noted in `tasks/closed/017-template-name-rendering-silent-failure.md`.

Unblocks `tasks/open/021-dreaming-memory-consolidation.md`, which injects
LLM-generated `Learning` text as a `{{ learnings }}` value via `literal()`.
