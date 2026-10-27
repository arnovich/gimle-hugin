---
title: Export checker-accepted agent sessions as an attributed trajectory dataset
state: open
priority: low
labels:
- research
- data
- taskvalet
created: '2026-10-27'
created_by: agent/255f4334-a6c0-4e2b-b41c-862809678450
---

## Context

Reasonable's October 2026 result (73.3% pass@1 on tlaverus-60) came from fine-tuning on 3,722 agentic proof sessions recorded verbatim (reasoning, tool calls and tool outputs) in an ordinary coding harness and filtered by checker acceptance. Gimle's equivalent sessions live in Hugin, not in Taskvalet, whose run journals hold command and receipt state; Taskvalet contributes the attribution index and the acceptance filter (a checked-snapshot compute report matching the pinned target under the allowed axioms). Open Math OS's data policy (training on user work only with explicit prior consent; a timestamped contributor record) is the model for consent and attribution. The consumer is undecided: a fine-tuned proving participant as Reasonable built, or Mimir only if trajectory data informs circuit proposals; this task delivers the dataset, not any training. The launch plan's warning that claims about synthetic data need measured results applies. Follows taskvalet/018 (hostile corpus, for cheat classification) and 019 (directions as findings). From the verification-peers scan in gimle-biz (PR 20).

## Outcome

- [ ] - [ ] A Hugin export produces, for a selected set of sessions, verbatim trajectories (prompts, recorded reasoning, tool calls and outputs) in a documented, versioned format, each with attribution (agent identity, problem version, assignment) and the Taskvalet compute report that accepted its result.
- [ ] Only sessions whose final artefact has a checked-snapshot report matching the pinned target under the allowed axioms are included; rejected or cheat-classified sessions are excluded or labelled, never silently mixed in.
- [ ] Sessions are exported only under recorded consent of their owner, and the export refuses sessions without it; no credentials, private paths or provider secrets appear in the output.
- [ ] A small sample from the proof-hole trials (research/012–018) is exported and described with token counts; no training is claimed.
- [ ] The consumer decision (fine-tuned proving participant versus Mimir) is recorded as a follow-up with the evidence the sample gives.
