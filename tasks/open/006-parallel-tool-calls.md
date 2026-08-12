---
github_issue: 6
title: Support batched tool calls end-to-end
state: OPEN
labels: [enhancement]
priority: high
author: arnovich
created: 2026-01-28
audited: 2026-08-12
---

# Support batched tool calls end-to-end

## Audit (2026-08-12)

Still relevant and cross-cutting. PR 58 removed silent loss: Anthropic and
OpenAI requests disable parallel tool use, and all adapters keep the first call
and warn if a provider still returns extras. That is a safe compatibility guard,
not support for a response containing multiple tool calls. `ModelResponse` and
the interaction flow still model only one call.

## Required design

- Represent an ordered list of tool calls, preserving every provider call ID
  and the single assistant message that emitted the batch.
- Render the batch and all corresponding tool results back in each provider's
  required message shape (Anthropic, OpenAI-compatible APIs, and Ollama).
- Choose an explicit execution policy. Sequential execution is the safest first
  implementation; true concurrency should be a later opt-in for independently
  safe calls.
- Define what happens when an earlier call errors, waits for background work,
  asks a human, finishes the agent, or mutates shared state.
- Persist/resume a partially executed batch without replaying completed calls.

`TaskChain` may help schedule work, but it is not by itself the response model:
the provider-visible assistant batch and its multiple matched result messages
must remain intact.

## Success criteria

- A response such as `save_learning` + `finish` executes in deterministic order
  without another LLM round trip and without dropping either call.
- Adapter tests cover compliant batches and provider violations for Anthropic,
  OpenAI, and Ollama.
- Interaction serialization, branch behavior, errors, waiting/resume, and
  multiple result IDs are covered by tests.
- The single-call path remains backward compatible.
