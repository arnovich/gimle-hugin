---
github_issue: null
title: Persist the rendered system + user prompt that was actually sent to the LLM
state: CLOSED
labels: [enhancement, observability]
author: erikarne
created: 2026-05-11
closed: 2026-05-11
resolution: Implemented in PR #45 (branch task/018_persist_rendered_prompt) — see spec.md / plan.md in this folder.
---

# Persist the rendered prompt sent to the LLM

## Why

`OracleResponse` interactions store only the assistant's response — not the
rendered system prompt and user message(s) that were actually sent to
`chat_completion`. When a prompt-rendering bug triggers (e.g. the bare
template-name silent failure fixed in #42), nothing in the persisted session
reveals it: you have to monkey-patch `chat_completion` to see what was sent.
That's what turned #42 into a ~half-day debug in `gimle-heimdall` PR #14.

## What

On `AskOracle.step()` (`src/gimle/hugin/interaction/ask_oracle.py`), capture:

- the rendered `system_prompt` (already computed there via
  `PromptRenderer.render_system_prompt`)
- the rendered user message content (the list returned by
  `render_user_message` / `render_stack_context` for this interaction)

…and persist it — either as fields on `OracleResponse`
(`src/gimle/hugin/interaction/oracle_response.py`) or new fields on `AskOracle`
— so it round-trips through storage and shows up in the monitor UI
(`src/gimle/hugin/cli/monitor_agents.py`, `src/gimle/hugin/ui/page.py`).

## Open questions

- Verbosity: rendered prompts can be large. Gate behind a debug flag /
  config option, or always store but only render in the monitor on demand?
- Storage cost: full prompt per `AskOracle` step. Acceptable, or store a
  hash + the prompt only when it differs from the previous step?

## Success criteria

- [ ] Given a session that hit a prompt-rendering bug, the persisted
      session shows the literal-vs-rendered system/user prompt without any
      monkey-patching.
- [ ] Monitor UI surfaces the rendered prompt for an `AskOracle`/`OracleResponse`.
- [ ] Old sessions (without the new field) still load.

## Context

Surfaced as a follow-up in `tasks/closed/017-template-name-rendering-silent-failure.md`
("Related observation").
