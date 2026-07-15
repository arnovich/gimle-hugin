# Notes: the harness blend (parked for phase 5)

The open question behind this task is bigger than the tool: **are we moving
toward a blend of a Pi-like harness — markdown files and bash commands — and
the traditional tool-calling setup?** v1 deliberately does not answer it. This
file keeps the thinking so it isn't lost.

## What "the blend" actually means

Treat the filesystem as a shared, inspectable medium between the framework and
the agent, in two directions:

- **Down (framework → files, read-only projection).** The task, prior
  artifacts, insights and sub-agent results get rendered into the workspace as
  markdown. The agent can `grep memory/` instead of calling `query_artifacts`
  — often cheaper, always more expressive.
- **Up (files → framework, harvest at explicit boundaries).** Whatever the
  agent leaves in `outbox/` becomes an `Artifact` at the end of the tool call
  or the end of the agent.

Sketch:

```
/workspace/
  TASK.md              # projected (ro) — the task definition
  ENVIRONMENT.md       # projected (ro) — what's installed, what's allowed
  memory/*.md          # projected (ro) — artifacts, insights
  outbox/              # harvested → Artifacts
  common/              # cross-agent hand-offs
  agents/<id>/         # per-agent cwd
```

## The one rule that keeps it coherent

**One direction of authority per object.** Storage is authoritative for
projected things and the files are a *render*, regenerated per turn. The
filesystem is authoritative for harvested things and nothing else writes them.

If both sides can write the same object, artifacts will drift between storage
and disk and we will spend a month on reconciliation. Enforce it structurally:
the projection mount is genuinely read-only, not read-only by convention.

## Why it's worth doing at all

`bash` is a universal escape hatch, so the tool registry stops needing to
anticipate everything — `read_file`, `list_files` and `search_files` largely
collapse into it for capable models.

But structured tools keep two advantages bash never gets:

1. **Typed arguments** the model can't fumble.
2. **Results that land in the stack as inspectable interactions**, rather than
   as an opaque stdout blob that `hugin monitor` cannot visualise.

So the end state isn't "replace tools with bash". It's:

> **bash for exploration and mechanical work; structured tools wherever the
> framework needs to observe, validate or persist the result.**

That line is what should drive the follow-up to task 005 (which builtins are
still worth having).

## Open questions for phase 5

- Does the projection regenerate every turn, or only when storage changes?
  (Every turn is simpler and probably fast enough; measure before optimising.)
- Is `ENVIRONMENT.md` generated from the `Policy` object, so the agent's map of
  what it may run can never drift from what it actually may run? (Strongly
  suspect yes — a hand-written description of the allowlist *will* rot.)
- Does the harvest run at the tool-call boundary or the agent boundary? The
  tool-call boundary gives faster feedback; the agent boundary gives cleaner
  semantics.
- What does the *system prompt* say? Giving an agent bash without telling it
  what is on the box is a recipe for a dozen wasted turns of `which`. This is
  the same problem `ENVIRONMENT.md` solves — the projection and the prompt
  should share a source.
