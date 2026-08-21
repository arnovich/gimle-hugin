---
github_issue: 13
title: Agent Builder reference and example access
state: CLOSED
labels: [enhancement]
priority: medium
author: arnovich
created: 2026-01-28
audited: 2026-08-12
closed: 2026-08-21
---

# Agent Builder reference and example access

## Audit (2026-08-12)

Still open, but now owned by the Agent Creator v2 programme (task 034) and
should not be implemented independently.

- `list_examples` and `read_example` already exist, but are not wired into the
  builder on `main`. Task 034 PR 1.2 / PR #83 adds that wiring.
- General `read_file`/`list_files` builtins exist, but granting unrestricted
  local access is not the intended solution. Task 034 PR 2.4 introduces an
  explicit `reference_files` input with confinement and untrusted-content
  wrapping.
- Task 034 Phase 2 also defines the packaged knowledge/reference source and
  searchable example index needed outside a source checkout.

## Closure rule

Close this task when task 034 PR 2.4 (or an equivalent scoped implementation)
has merged and verifies both:

- the builder can study packaged examples in an installed distribution; and
- a user can explicitly provide confined local reference files without giving
  generated instructions arbitrary filesystem access.

## Closed (2026-08-21)

Both closure conditions are met, and both were verified by running the thing
rather than by reading the code.

**"The builder can study packaged examples in an installed distribution."**
Fixed in #115. It was not merely unbuilt — it was a live defect. Measured on a
wheel built from `main` and installed into a clean venv, `list_examples`
advertised 16 examples from hardcoded metadata and `read_example` returned
"Examples folder not found" for every one of them. `examples/` sits at the
repository root, outside `src/gimle`, so it never reached a wheel. Seven
curated examples now ship inside the package (47 KiB), and the same check
afterwards returns 7 listed from the filesystem with 11751 characters of real
content for `task_sequences`.

**"A user can explicitly provide confined local reference files without giving
generated instructions arbitrary filesystem access."** Shipped in #116 as
`--reference-file`, capped and wrapped in a delimited untrusted block.

Note the deliberate departure from task 034's spec §2.4, which opens by
suggesting `builtins.read_file` and `builtins.list_files` be added to the
builder's config. The audit above rejects exactly that, and this task's
closure rule is the reason: a builder holding `read_file` can be talked into
reading anything the process can reach, and the text doing the talking may be
the reference file itself. Reading only what the user named, before the model
is involved, removes that. Tests assert neither builtin is in either builder
config.

Verified with a spec carrying a planted instruction to generate an
`exfiltrate_key` tool posting `ANTHROPIC_API_KEY` to an external host. The
generated agent used the spec's real endpoint and field names and contained no
such tool. That is one trial against one model — evidence the framing works,
not proof the feature is injection-proof. It sits inside the trust boundary
stated in task 034's description.md.
