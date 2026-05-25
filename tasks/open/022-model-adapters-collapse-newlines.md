---
title: Model adapters collapse newlines in assistant text content
state: OPEN
labels: [bug, llm]
author: arnovich
created: 2026-05-25
---

# Model adapters collapse newlines in assistant text content

All three LLM model adapters strip newlines from the assistant's free-text
response on the plain-text (non-tool-call) return path, unconditionally and
without comment:

- `src/gimle/hugin/llm/models/anthropic.py:146` — `content=text_content.replace("\n", " ")`
- `src/gimle/hugin/llm/models/openai.py:162` — `content=text_content.replace("\n", " ")`
- `src/gimle/hugin/llm/models/ollama.py:1053` — `content=(response.message.content or "").replace("\n", " ")`

Because the behaviour is identical across providers, it appears to be a
deliberate (or long-standing) convention rather than a one-off slip — but it is
undocumented and silently lossy.

## Why it's a problem

The assistant's `ModelResponse.content` is therefore **never returned verbatim**
when it spans multiple lines. Any consumer that needs structured multi-line text
back from the model — markdown, code blocks, lists, or "one item per line"
output — receives a single space-joined line instead, with no error and no
warning.

**Concrete instance:** a programmatic proposer in `gimle-bifrost`
(`bifrost/benchmarks/discovery/llm_proposer.py`) asked the model for candidate
circuits "one per line" and parsed on `\n`. Because the adapter collapsed the
newlines, every response parsed to a single unparseable blob and the proposer
returned **zero** candidates — a silent, total failure that offline tests missed
(the test fake didn't replicate the collapse). It was worked around there by
switching to a `;` delimiter, but the underlying framework behaviour remains.

## Why it has gone unnoticed

The **tool-call path is unaffected**: when the model calls a tool, the arguments
are returned as a dict (`tool_use_content.input`, e.g. `anthropic.py:135`), not
newline-collapsed. Most Hugin agents route their real output through tools
(write-file, etc.), so the lossy free-text path rarely bites — until a consumer
relies on the assistant's text content directly.

## Tasks

- [ ] Decide the intended contract: should `ModelResponse.content` preserve the
      model's text verbatim (newlines included)?
- [ ] If yes: stop collapsing newlines in all three adapters; move any
      single-line requirement (e.g. log formatting) to the display/logging layer
      so the returned content stays faithful.
- [ ] If single-line is sometimes wanted: make it opt-in (e.g. a
      `collapse_newlines` flag on the model/config, default off) rather than
      always-on, and document it.
- [ ] Apply the decision consistently across `anthropic.py`, `openai.py`,
      `ollama.py`.
- [ ] Add a test asserting multi-line assistant content round-trips as expected
      (using `MockModel`/fixtures), so a regression can't reintroduce the silent
      collapse.

## Success Criteria

- [ ] A consumer can recover the assistant's multi-line text content verbatim
      (or the collapse is explicitly opt-in and documented).
- [ ] Behaviour is consistent across all three provider adapters.
- [ ] Covered by a test that would fail if newlines were silently collapsed.

## Notes

Discovered 2026-05-25 while building the bifrost discovery LLM-proposer. Severity
is moderate: it does not affect tool-call-driven agents, but it is a silent
correctness trap for any text-content consumer and is surprising/undocumented.
