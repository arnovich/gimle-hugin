---
title: Storage-directory metadata can load arbitrary Python into the monitor
state: ongoing
claimed_by: codex/task039
claimed_at: 2026-09-28T10:44:00Z
branch: task/039_storage_extension_trust
priority: high
labels: [security, bug, storage]
related: ["038"]
---

# Storage-directory metadata can load arbitrary Python into the monitor

## Context

`LocalStorage._save_session` writes `.hugin_metadata.json` at the **storage
root**, carrying a `package_paths` list (`storage/local.py:201-219`). Two CLI
entry points read that file back and import from every path it names:

- `cli/monitor_agents.py:68-88` — reads `package_paths` and calls
  `Environment._load_extensions(package_path)` for each.
- `cli/interactive/state.py:1074-1086` — the same, via `Environment.load`.

`Environment._load_extensions` (`agent/environment.py:204-222`) imports Python
from the directory it is handed; `Environment.load` additionally mutates
`sys.path` and imports tool modules by bare name (`:327-356`).

This is safe today only because a single trusted process writes the storage
directory. It stops being safe the moment storage has more than one writer —
which is exactly what task 038 proposes, and what any shared-storage or
network-backed `Storage` implementation would introduce (task 004).

The escalation matters: a board writer injecting text into an agent is
contained by the agent's sandbox. A board writer appending a `package_paths`
entry gets arbitrary code imported **into the operator's own CLI process**, next
time anyone runs `hugin monitor --storage-path <shared>` or `hugin interactive`
against that directory — outside the sandbox entirely, with the operator's
credentials and API keys.

Found during the panel review of task 038. It is a defect on its own merits:
even single-writer, a storage directory restored from an untrusted archive or
shared over a network filesystem carries the same exposure.

## Outcome

- [x] The monitor and the interactive TUI no longer derive importable package
      paths from anything inside the storage directory.
- [x] Extension paths come from local CLI arguments or local config only, and a
      `.hugin_metadata.json` found in storage is either ignored for this purpose
      or requires explicit opt-in naming the path.
- [x] A test asserts that a `.hugin_metadata.json` containing an attacker-chosen
      `package_paths` entry does not cause an import when the monitor starts.
- [x] If the opt-in path is kept, `hugin monitor` states in its output which
      extension paths it loaded and where the instruction came from.

## Notes

- Task 038 depends on this: its plan makes `Storage` a multi-writer message
  board, and states that a cross-machine board must not be enabled until this
  is closed.
- Related: the same "storage content is trusted input" assumption shows up in
  `Interaction.from_dict` (`interaction/interaction.py:189-221`), which
  dispatches on a persisted `type` field into the process-global interaction
  registry and loads artifacts before the type check. 038 handles that for its
  own wire format by parsing envelopes with a dedicated strict parser rather
  than the generic loader; a general audit of that assumption is out of scope
  here.

## Plan

- Remove the monitor's storage-metadata extension loader, including its late
  reloads on agent, artifact, and interaction requests. Load extensions only
  from repeatable explicit `--extension-path` arguments at startup, reporting
  the selected paths and their CLI/API source.
- Resume TUI agents only with the existing explicit `--task-path`; without
  that trusted directory, keep browsing available and explain how to enable
  resumption. Never fall back to metadata after a failed load.
- Forward the trusted task directory from `hugin run --monitor` to preserve
  custom artifact rendering. Document the opt-in and retain stored package
  paths as provenance only.
- Add sentinel-import regressions for monitor startup, later HTTP requests,
  and TUI resume, plus positive explicit-path and CLI-forwarding tests. Run
  focused and full tests and pre-commit, then an independent review panel.

## Validation

- Reproduced an actual sentinel Python import from attacker-chosen storage
  metadata before the fix. The regression now passes; the new suite contains
  13 startup/request/resume/browsing/explicit-path/CLI/helper cases.
- `TMPDIR=/private/tmp uv run pytest -x -q`: **1,774 passed, 53 skipped**.
- All pre-commit hooks pass for the changed files. All-file pre-commit still
  reports baseline failures: 113 existing flake8 docstring findings, the
  untyped function in `scripts/sync_packaged_examples.py:51`, and existing
  secret-detector fixtures in `test_replay.py` and `test_trace_analysis.py`.
  The hook-generated unrelated `.secrets.baseline` update was discarded.
- A real localhost monitor returned HTTP 200 with metadata present and did
  not import its sentinel. A second launch with `--extension-path` imported
  the explicitly named package and identified it in startup output.
- Independent review is pending. The pre-existing RapMachine `artifacts/`
  and `components/` directories are not extension-loader conventions
  (`artifact_types/` and `ui_components/`); this change does not expand those
  conventions. App launchers now pass their package paths explicitly.

## Review

Three-role panel (correctness/security, compatibility/testing, maintainability/performance): no blocking findings. Trusted-path and attacker-sentinel regressions independently verified.

## Conversation

### note · codex/task039 · 2026-09-28T10:44:00Z

Claimed to implement, test, and panel-review a separate PR; merge awaits owner review.

### note · codex/task039 · 2026-09-28T11:20:06Z

Implemented explicit trusted-path loading, removed metadata imports, and verified 1,774 tests plus live monitor HTTP startup; ready for independent panel review.

### note · codex/task039 · 2026-09-28T11:31:02Z

Panel complete; preparing the implementation PR for owner review.
