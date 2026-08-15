---
title: Learnings accumulate forever and are selected by recency — prune and rank them
state: OPEN
labels: [dreaming, memory, enhancement]
priority: medium
---

# Learnings accumulate forever and are selected by recency

## Where this belongs

**Hugin, not the calling app.** The whole `Learning` lifecycle is Hugin's:
`save_learning` creates them, `dreaming/selector.py` ranks and budget-caps them,
`PromptRenderer` injects them via `{{ learnings }}`, and `run_dream` consolidates
them. An app that wanted to prune would have to reimplement `select_learnings`'
ranking just to know what is safe to delete, and would fix the problem only for
its own agents — every Hugin app that dreams rots identically. The defect is in
the ranking mechanism, which is here.

`Storage.delete_artifact` now detaches the artifact id from its persisted owning
interaction before deleting the artifact and its feedback. Local filesystem
detachment is atomic, failed detachment aborts deletion, and repeated deletion is
safe. The remaining physical-garbage-collection work is candidate and retention
policy, not reference integrity.

## Progress

- [x] Structural supersession: same-scope learning ids can be retired without
      deletion; active selection and dream dedup both exclude them.
- [x] Ranking that distinguishes human feedback from birth confidence: human
      ratings are authoritative once present; otherwise agent ratings are the
      fallback, and equal scores use evidence count plus a stable artifact-id
      tie-break rather than recency.
- [ ] Safe physical pruning.
  - [x] Reference-safe deletion: persisted/live interaction references are
        detached before artifact and feedback removal.
  - [ ] Opt-in, dry-run-first candidate and retention policy for superseded
        learnings.

## The problem

Two failures that look like one.

### 1. Selection was effectively by recency

Before the source-aware ranking phase, `select_learnings` sorted by
`(average_rating, created_at)` descending and kept
`DEFAULT_BUDGET = 5`. Ratings come from `_ratings_map`, which reads
`ArtifactFeedback` rows. In practice a learning has exactly **one** rating, written
by `save_learning` at creation from the dream's own self-assessed confidence:

```python
def _confidence_to_rating(confidence: float) -> int:
    return max(1, min(5, round(1 + clamped * 4)))
```

so 0.9 → 5, 0.8 → 4. Confidence clusters high (the dream is asked to be honest,
not harsh), which means ratings cluster at 4–5 and the **tie-break decides**:
`created_at` descending. Newest wins.

Nothing writes a second rating automatically. The only other `save_feedback`
callers are three human paths — `cli/rate_artifact.py`,
`cli/interactive/screens/artifact.py`, `cli/monitor_agents.py` — none of which
runs in a batch pipeline.

The consequence was that **a good old learning was permanently evicted once five
newer confident ones existed**, and could never come back, because nothing could
raise its rating and nothing lowered the newcomers'. Selection drifted toward
whatever was written last, not what worked.

Selection now groups feedback by `source`. Human ratings replace agent ratings
as the ranking signal once present, while the dream's confidence remains useful
for unreviewed learnings. Equal scores prefer human evidence, then more ratings,
then artifact id; `created_at` no longer affects selection.

### 2. The store grows without bound

No learning lifecycle currently deletes a learning. Observed in gimle-heimdall's
newspaper personas (2026-08-14): 23 learnings each for `newspaper_columnist` and
`newspaper_quant`, 9 for `newspaper_editor`, of which **5** are ever injected.
The inactive records still cost physical storage. Structurally superseded
learnings no longer enter selection or dream deduplication, but remain stored for
audit until an explicit pruning policy exists.

### Why #91 raised the stakes rather than settling them

Before #91 the dream saw only the injected top 5, so it re-derived lessons that
had fallen below the cut — it restated its own learning thirteen minutes after
writing it. #91 made deduplication consider the full active set. Structural
supersession and source-aware ranking have since aligned the active set and its
top 5; only physical retention of inactive audit records remains unresolved.

## The honest blocker

There is still no generic signal for *"did this learning help?"*. Confidence is
self-assessed at birth, human review is optional, and Hugin cannot infer an app's
outcome attribution. The implemented signals are deliberately conservative:

- **Human ratings** — already supported, but require someone to sit in the monitor.
  Fine for a curated app, useless for a nightly batch.
- **Usage/outcome feedback** — did an edition that injected learning X score better?
  Requires the app to attribute an outcome back to a specific injected learning,
  which Hugin cannot do generically.
- **Dream-assessed supersession** — implemented as exact-scope structural links.
  It safely identifies inactive predecessors without claiming a generic quality
  score, making superseded learnings the first defensible pruning candidates.

## Sketch, smallest useful first

1. **Structural supersession.** Give `save_learning` an optional
   `supersedes: List[str]`, and have `select_learnings` skip any learning that a
   valid same-scope supersession chain retires. This is the one increment that
   needs no new signal — the dream is already making the judgement, in prose,
   and throwing it away. It bounds the **active selection set** for the common
   case (refinement) without deleting anything, which keeps the audit trail; it
   does not yet bound physical storage.
2. **Ranking that is not recency.** Implemented with source-aware feedback:
   human ratings are authoritative once present, agent confidence is the
   fallback for unreviewed learnings, and deterministic ties no longer use
   `created_at`.
3. **Actual pruning.** Reference-safe deletion is now implemented: the owning
   persisted interaction is detached before the artifact disappears. The
   remaining increment is an explicit, opt-in, dry-run-first policy that selects
   structurally superseded learnings and applies a retention window before using
   that primitive. Ranking alone must never authorize deletion.

Structural links are monotonic and exact-scope: `C -> B -> A` leaves only C
active, while all three records remain auditable. `save_learning` rejects missing,
non-Learning, cross-scope, self-referential, and cyclic targets. Selection also
ignores invalid imported edges so malformed historical data cannot retire an
unrelated scope.

## Provenance

Found 2026-08-14 in gimle-heimdall while fixing the three-cause dreaming outage
(#90, #91 here; #1034, #1053 there). Not a regression from those — the store had
been accumulating unranked since dreaming shipped; #91 simply made the two halves'
disagreement visible. Raised and deliberately deferred rather than folded into a
fix, because choosing a quality signal is a design decision, not a bug fix.
