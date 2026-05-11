---
github_issue: null
title: Warn at load time when a config/task references a template name that isn't registered
state: OPEN
labels: [enhancement, dx]
author: erikarne
created: 2026-05-11
---

# Warn on bare template references that match no registered template

## Why

#42 made bare template-name references work: `system_template: my_template` /
`prompt: my_prompt` (a bare string, no Jinja) now resolves to the registered
template's body. But a **misspelled** bare name — `system_template:
basci_system` instead of `basic_system` — still silently sends the literal
typo string to the LLM, because it matches no registered template and contains
no Jinja, so the renderer passes it through verbatim. Same silent-failure class
as #42, just narrower (and now arguably more surprising, since the non-typo
case works).

## What

After `Environment.load()` has registered all templates, configs, and tasks
(`src/gimle/hugin/agent/environment.py`), validate that each `config.system_template`,
`task.system_template`, and `task.prompt` that *looks like a bare template
reference* — i.e. contains no Jinja syntax, no newlines, and reads like an
identifier — actually matches a registered template name. If it doesn't, emit
a warning pointing at the likely typo (closest registered name?) and the
`{{ X.template }}` form.

Validation must run *after* the full load, not while registering configs — a
config may be registered before the template it names.

## Watch out for

- Don't false-positive on legitimate short literal prompts (e.g. a task whose
  prompt genuinely is `"Summarize this."`). Heuristic: single token, snake_case,
  no spaces → likely a template reference; anything with a space → a literal.
  Worst case it's a `logger.warning`, not an error, so a false positive is cheap.
- Consider whether this should be a hard error in strict mode and a warning
  otherwise.

## Success criteria

- [ ] Loading an environment with `system_template: <typo>` logs a clear
      warning naming the offending config/task and the unknown template.
- [ ] No warnings for the bundled apps/examples (they all reference real
      templates) or for tasks with inline-prose prompts.

## Context

"Suggested fix 2" in `tasks/closed/017-template-name-rendering-silent-failure.md`.
