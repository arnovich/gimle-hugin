---
title: Storage-directory metadata can load arbitrary Python into the monitor
state: open
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

- [ ] The monitor and the interactive TUI no longer derive importable package
      paths from anything inside the storage directory.
- [ ] Extension paths come from local CLI arguments or local config only, and a
      `.hugin_metadata.json` found in storage is either ignored for this purpose
      or requires explicit opt-in naming the path.
- [ ] A test asserts that a `.hugin_metadata.json` containing an attacker-chosen
      `package_paths` entry does not cause an import when the monitor starts.
- [ ] If the opt-in path is kept, `hugin monitor` states in its output which
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
