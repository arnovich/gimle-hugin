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

`Storage.delete_artifact` exists, but it is not yet a safe pruning primitive by
itself: persisted interactions retain artifact ids and currently expect those
ids to load. Physical garbage collection must either clean those references or
introduce an archival/tombstone mechanism.

## Progress

- [x] Structural supersession: same-scope learning ids can be retired without
      deletion; active selection and dream dedup both exclude them.
- [x] Ranking that distinguishes human feedback from birth confidence: human
      ratings are authoritative once present; otherwise agent ratings are the
      fallback, and equal scores use evidence count plus a stable artifact-id
      tie-break rather than recency.
- [ ] Safe physical pruning with interaction-reference integrity.

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

Nothing deletes a learning, ever. Observed in gimle-heimdall's newspaper personas
(2026-08-14): 23 learnings each for `newspaper_columnist` and `newspaper_quant`,
9 for `newspaper_editor`, of which **5** are ever injected. The other 18 are
inert — they cost storage and dream-prompt space (they are shown to the worker
for dedup since #91) and influence nothing downstream.

### Why #91 raised the stakes rather than settling them

Before #91 the dream saw only the injected top 5, so it re-derived lessons that
had fallen below the cut — it restated its own learning thirteen minutes after
writing it. #91 shows it all of them (`DEDUP_BUDGET = 100`), which stopped the
duplication. But that means the **dreamer** now knows all 23 while the
**personas** still see 5 chosen largely by recency. The two halves of the memory
system disagree about what the agent knows.

## The honest blocker

There is no signal for *"did this learning help?"*. Confidence is self-assessed at
birth and never revisited. Any ranking better than recency needs one, and none of
the obvious candidates is free:

- **Human ratings** — already supported, but require someone to sit in the monitor.
  Fine for a curated app, useless for a nightly batch.
- **Usage/outcome feedback** — did an edition that injected learning X score better?
  Requires the app to attribute an outcome back to a specific injected learning,
  which Hugin cannot do generically.
- **Dream-assessed decay** — let the dream, which already reads all of them, mark
  one superseded or wrong. Cheapest, and it fits: #90's prompt already licenses
  *"say so explicitly in the new learning's prose"* when a memory overtakes a prior
  learning. But that supersession is **prose only** — nothing links the new artifact
  to the old one or retires it, so both stay in the pool competing on equal footing.

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
3. **Actual pruning.** Only once 1 and 2 exist. Deleting on recency-derived rank
   would delete the good old ones first, which is the current bug with a harder
   edge. Deletion must also preserve or deliberately rewrite artifact references
   held by persisted interactions.

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
