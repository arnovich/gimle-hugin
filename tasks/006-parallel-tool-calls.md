---
github_issue: 6
title: Support parallel tool calls from LLMs
state: OPEN
labels: [enhancement]
author: arnovich
created: 2026-01-28
---

# Support parallel tool calls from LLMs

When LLMs return multiple tool calls in a single response, currently only the first is executed.

Example: Qwen3:14b often returns both save_insight and finish together, but only save_insight runs.

Solution: Chain all tool calls using existing TaskChain infrastructure:

- Detect multiple tool calls in OracleResponse
- Create chain of ToolCall interactions
- Execute sequentially without extra LLM roundtrips

Benefits:

- Fewer agent steps
- Lower API costs
- Honors model intent
