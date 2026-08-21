"""Record which files a machine wrote, and when.

Once `hugin improve --apply` can edit an agent, "did a person write this line
or did Hugin?" stops being answerable from the directory alone. Six months
later that is the question someone actually has: a tool behaves oddly, and
whether it was hand-tuned or generated decides whether to fix it or regenerate
it.

The record is a single JSON file at the agent root rather than markers injected
into the generated files themselves. Markers in content would change the very
bytes whose hash is being recorded, would be deleted by anyone tidying up, and
would put machine bookkeeping into a file the user reads and edits.

This deliberately does **not** make writes stricter. `hugin create --edit` is
documented as working on hand-written agents, and refusing to touch anything
Hugin did not write would break exactly that. What the manifest gives is
*visibility*: an edit can say "this file has been changed by hand since Hugin
wrote it" and let whoever is reading the diff decide.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

MANIFEST_NAME = ".hugin-manifest.json"

# Bumped only if the shape changes incompatibly. An unreadable or newer
# manifest is treated as absent rather than fatal -- provenance is useful
# bookkeeping, and losing it must never stop someone editing their agent.
MANIFEST_VERSION = 1


def manifest_path(agent_dir: Path) -> Path:
    """Return where the manifest lives for an agent directory."""
    return Path(agent_dir) / MANIFEST_NAME


def digest_text(content: str) -> str:
    """Return the recorded hash for a file's content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def read_manifest(agent_dir: Path) -> Dict[str, Any]:
    """Return the stored manifest, or an empty one.

    Every failure mode collapses to "no manifest": missing, unreadable,
    corrupt, or written by a newer Hugin. None of those are worth refusing to
    edit an agent over.
    """
    path = manifest_path(agent_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    if data.get("version") != MANIFEST_VERSION:
        return {}
    files = data.get("files")
    if not isinstance(files, dict):
        return {}
    return data


def recorded_files(manifest: Dict[str, Any]) -> Dict[str, str]:
    """Return ``{key: sha256}`` for everything the manifest records."""
    files = manifest.get("files")
    if not isinstance(files, dict):
        return {}
    return {
        str(key): str(entry["sha256"])
        for key, entry in files.items()
        if isinstance(entry, dict) and isinstance(entry.get("sha256"), str)
    }


def update_manifest(
    agent_dir: Path,
    written: Dict[str, str],
    command: str,
    now: Optional[str] = None,
) -> Dict[str, Any]:
    """Record ``written`` as machine-authored, keeping earlier entries.

    Entries for files this run did not touch are preserved: an agent built by
    one command and later edited by another has both provenances, and
    flattening them to the most recent command would lose the distinction the
    manifest exists to keep.
    """
    agent_dir = Path(agent_dir)
    stamp = now or datetime.now(timezone.utc).isoformat()
    manifest = read_manifest(agent_dir)
    files = dict(manifest.get("files") or {})

    for key, content in written.items():
        files[key] = {
            "sha256": digest_text(content),
            "generated_by": command,
            "generated_at": stamp,
        }

    updated = {
        "version": MANIFEST_VERSION,
        "generated_by": command,
        "generated_at": stamp,
        "files": dict(sorted(files.items())),
    }
    try:
        manifest_path(agent_dir).write_text(
            json.dumps(updated, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        # Losing the record is not worth failing a write that succeeded.
        return manifest
    return updated


def hand_modified(agent_dir: Path, current: Dict[str, str]) -> List[str]:
    """Return files whose content differs from what the manifest recorded.

    Only files the manifest knows about can be reported: a file Hugin never
    wrote is not "modified", it is simply not ours, and calling it modified
    would flag every hand-written agent as suspicious.
    """
    recorded = recorded_files(read_manifest(agent_dir))
    return sorted(
        key
        for key, content in current.items()
        if key in recorded and recorded[key] != digest_text(content)
    )


def untracked(agent_dir: Path, current: Dict[str, str]) -> List[str]:
    """Return loaded files the manifest has no record of."""
    recorded = recorded_files(read_manifest(agent_dir))
    return sorted(key for key in current if key not in recorded)
