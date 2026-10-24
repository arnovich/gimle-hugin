---
title: Bind native Hugin tools to Taskvalet participants
state: ongoing
priority: high
labels:
- integration
- taskvalet
created: '2026-10-24'
created_by: agent/dc5f861b-de59-46fe-b239-2c8d005c8155
claimed_by: agent/dc5f861b-de59-46fe-b239-2c8d005c8155
claimed_at: '2026-10-24T13:03:51.733677+00:00'
branch: task/042_bind_native_hugin_tools_to_taskvalet_participants_cb58b316d1
console_approvals:
  7e4d75f6fcc2702ee8195fb5:
    request_id: d4d8fd73-b99d-4cd9-b90e-86dd0ee3f8d7
    operation: claim
    task: 042-bind-native-hugin-tools-to-taskvalet-participants
    executed_by: agent/dc5f861b-de59-46fe-b239-2c8d005c8155
    source: Console
    verification: agent_relay
    approval: 'Owner explicitly requested: let''s do Hugin for now and then let''s
      move on to 2 and 3. This task implements that native Hugin integration.'
    previous_claim: null
    expires_at: '2026-10-24T13:13:50.126456Z'
    observed_revision: 19aa1f2821f2ade24a44fbe7a44e6f19d8229d23ee4baef66f04240d77faf5bb:0d9a64f5ce2b2afe41e9b9b3fdd08f92fd89a950
    question_id: null
review_requested: true
pull_request: https://github.com/arnovich/gimle-hugin/pull/148
---

## Context

The owner requested the Hugin integration following Taskvalet external swarm participation, then an end-to-end Lean pilot and reusable knowledge loop. Hugin needs full tool schemas and per-agent bindings to the shared Taskvalet tool contract without storing credentials in model-visible configuration.

## Outcome

- [ ] Hugin supports complete JSON tool schemas through its providers; an operator can bind Taskvalet participation and asynchronous compute tools to one agent with identity isolation, structured errors and safe cleanup; behavioral tests and documentation cover multi-agent use and recovery.

## Plan

Implement native Taskvalet tools without putting runtime credentials into Hugin configs or storage.

1. Add optional complete input_schema to Hugin Tool, preserve it through serialization and provider formatting, and keep legacy parameter behavior unchanged. Tool implementations remain responsible for runtime validation.
2. Add a dependency-free Hugin Taskvalet provider protocol and scoped binding context. Each registered implementation uses a unique registry name with the stable model-facing alias, checks the exact calling Agent object, refuses duplicate binding, and unregisters only its own entries. The operator supplies an already-bound Taskvalet provider; models cannot choose servers, credentials or identities. Configs/tasks receive tool names explicitly, never credential objects.
3. Extend Taskvalet's common participant/tool contract with immediate Lean compute submission and single-read status/results, using an operator-pinned environment/checker/context/path/resource policy. Preserve exact submission bytes and request UUID in the existing durable journal; return without waiting for the computation. Surface expected errors as structured tool results, with unknown failures reported without leaking credentials or source.
4. Exercise real Hugin ToolCall/ToolResponse and provider schemas, multiple agents/alias isolation/cleanup, authenticated Taskvalet participation, compute submit -> unrelated checkpoint -> status, and lost-response recovery. Use scripted models and isolated services, with no paid live model calls during implementation.
5. Run independent workflow, security/recovery, and integration reviews, apply valid fixes, and follow Hugin's staff-review/fresh-worktree workflow for the final implementation. Run full tests, pre-commit checks, and package checks; open PRs and retain the task in Review.

After this increment, prepare the authorized deployment and bounded Causa/Forseti Lean pilot, then use pilot evidence to design the reviewed-knowledge retrieval/promotion loop. No LangChain adapter in this increment. Compute results remain evidence, not shared knowledge or proof authority.

## Conversation

### note · agent/dc5f861b-de59-46fe-b239-2c8d005c8155 · 2026-10-24T13:03:51Z

Owner approval relayed by agent (Console). Operation claim; request d4d8fd73-b99d-4cd9-b90e-86dd0ee3f8d7; previous claimant none.

Owner explicitly requested: let's do Hugin for now and then let's move on to 2 and 3. This task implements that native Hugin integration.

### note · agent/dc5f861b-de59-46fe-b239-2c8d005c8155 · 2026-10-24T14:06:21Z

Implemented native per-agent tool bindings and complete provider schemas; Taskvalet adds prepared asynchronous compute submit/status with durable receipt recovery. Three-role review found two recovery issues, both fixed with regressions. Final Hugin iteration is in gimle-hugin-taskvalet-final on the claimed branch; the original run journal remains authoritative. Focused and cross-package tests pass; full suites and CI-equivalent checks are running. All-files pre-commit has baseline docstring/secret-fixture failures and a mypy 1.16.1 dependency crash, reproduced on untouched origin/main. No production deployment or model calls yet.

### note · agent/dc5f861b-de59-46fe-b239-2c8d005c8155 · 2026-10-24T16:25:18Z

Native integration ready for review. Hugin: 1857 passed, 53 skipped; formatting/lint/types, 26 shipped-agent validation and changed-file commit hooks pass. Three-role panel cleared final iteration. Taskvalet companion PR https://github.com/arnovich/taskvalet/pull/7 adds prepared compute and sanitized tool responses; 517 tests covered including two unchanged timeout reruns, 105 browser tests and 3 authenticated cross-package tests pass. Existing unrelated all-files hook findings reproduced on base; fixed the old mypy hook crash by matching the locked development version. CI is pending. No owner acceptance, public release or production deployment performed.
