---
github_issue: 3
title: Finish long-term memory retrieval and lifecycle
state: OPEN
labels: [enhancement]
priority: medium
author: arnovich
created: 2026-01-28
audited: 2026-08-12
---

# Finish long-term memory retrieval and lifecycle

## Audit (2026-08-12)

Still relevant, but the original description predates most of the memory
system. Hugin now has `Text`, `Code`, `File`, `Image`, and `Learning` artifact
types plus artifact feedback; keyword/rating-aware queries; and the task 021
`hugin dream` pipeline for scoped learning consolidation and prompt injection.
Adding unspecified "more memory types" is no longer a useful scope.

## Remaining problem

The next memory work should make retrieval and lifecycle predictable as the
corpus grows:

- Define and index queryable metadata such as agent/task scope, provenance,
  creation time, rating, and artifact type.
- Measure current keyword retrieval on representative corpora before choosing
  embeddings or another semantic index. Any new index needs a rebuild/migration
  path and deterministic fallback.
- Add lifecycle rules for duplicate or superseded learnings, retention, and
  deletion; keep provenance when memories are consolidated.
- Make dreaming incremental (for example, a persisted corpus watermark) instead
  of repeatedly reconsidering the same full corpus.
- Budget injected memory by tokens as well as item count/characters, and expose
  enough diagnostics to explain why a memory was selected.

## Success criteria

- Retrieval quality and latency have a repeatable benchmark.
- Scoped queries cannot leak memories from unrelated runs.
- Re-running consolidation without new source material is idempotent or a
  documented no-op.
- Superseding/deleting a memory has defined persistence and provenance behavior.
