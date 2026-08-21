"""Read an existing agent directory into the builder's working payload.

Every ``generate_*`` tool writes into ``env_vars["generated_files"]``, and the
writer writes that dict out. Filling the same dict from disk therefore turns
each generator into an *edit* tool for free: regenerating ``configs/x.yaml``
replaces that one key and leaves every other file exactly as it was read.

This returns a manifest -- paths and sizes -- and never file bodies. Bodies
come from ``read_generated_file``, one file at a time, because dumping a whole
directory into context is what ``preview_files`` already does badly at 24k
characters. The builder is expected to read a file before regenerating it;
without that it reinvents a whole tool from a one-line instruction and
silently discards every hand-tuned line, which is exactly the trap for users
who followed the docs' advice to customise a generated agent.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Tuple

from gimle.hugin.apps.agent_builder.manifest import (
    hand_modified,
    untracked,
)
from gimle.hugin.apps.agent_builder.tools.agent_paths import (
    PathConfinementError,
    confine,
    is_exempt,
    validate_generated_key,
)
from gimle.hugin.apps.agent_builder.tools.write_agent_files import (
    adopt_existing_files,
)
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

# One agent's worth of source. Well above any agent the builder produces
# (the largest golden-set agent is ~15k), and low enough that pointing this
# at the wrong directory fails loudly instead of filling the context window.
MAX_TOTAL_CHARS = 400_000

# A single generated file this large is not something an edit can usefully
# reason about, and is a strong sign the path is not an agent directory.
MAX_FILE_CHARS = 100_000

# Never walked into: build artefacts and the agent's own run history. Storage
# in particular can be hundreds of megabytes of trace JSON.
SKIP_DIRECTORIES = frozenset(
    {"storage", "artifacts", "__pycache__", ".git", ".venv", "node_modules"}
)


def _collect(agent_dir: Path) -> Tuple[Dict[str, str], List[str]]:
    """Return the loadable files under ``agent_dir`` and the reasons for skips.

    Skips rather than fails on anything unloadable. A hand-maintained agent
    directory legitimately holds files the builder does not manage -- notes,
    fixtures, a Makefile -- and refusing to load because one of them exists
    would make edit mode unusable on exactly the directories it is for.
    """
    files: Dict[str, str] = {}
    skipped: List[str] = []

    for root, directories, names in os.walk(agent_dir):
        directories[:] = sorted(
            name
            for name in directories
            if name not in SKIP_DIRECTORIES and not name.startswith(".")
        )
        for name in sorted(names):
            absolute = Path(root) / name
            key = str(absolute.relative_to(agent_dir))
            if is_exempt(key):
                # README, BUILD_REPORT, __init__ and friends are produced by
                # the writer at write time, never carried in the payload --
                # the validator rejects them as generated keys outright. In
                # edit mode the writer emits none of them, so leaving them
                # here means they stay on disk exactly as they are.
                skipped.append(f"{key}: preserved, not managed by an edit")
                continue
            if validate_generated_key(key):
                skipped.append(f"{key}: not a file the builder manages")
                continue
            if absolute.is_symlink():
                skipped.append(f"{key}: symlink")
                continue
            try:
                # Confine even though the key came from our own walk: a
                # directory component may be a symlink out of the tree.
                confine(agent_dir, key)
                content = absolute.read_text(encoding="utf-8")
            except PathConfinementError:
                skipped.append(f"{key}: resolves outside the agent directory")
                continue
            except (OSError, UnicodeDecodeError) as error:
                skipped.append(f"{key}: unreadable ({error})")
                continue
            if len(content) > MAX_FILE_CHARS:
                skipped.append(
                    f"{key}: {len(content)} characters exceeds the "
                    f"{MAX_FILE_CHARS} limit"
                )
                continue
            files[key] = content

    return files, skipped


def load_agent_files(
    stack: "Stack", agent_path: str, replace: bool = True
) -> ToolResponse:
    """Load an existing agent directory into the working payload.

    Args:
        stack: Agent stack (auto-injected)
        agent_path: Directory of the agent to edit
        replace: Discard any payload already in progress. Loading on top of a
            half-built agent would silently mix two agents into one directory.

    Returns:
        ToolResponse with a manifest of what was loaded, or an error.
    """
    if not agent_path or not agent_path.strip():
        return ToolResponse(
            is_error=True, content={"error": "no agent path specified"}
        )

    agent_dir = Path(agent_path).expanduser()
    if not agent_dir.exists():
        return ToolResponse(
            is_error=True,
            content={"error": f"no such directory: {agent_dir}"},
        )
    if not agent_dir.is_dir():
        return ToolResponse(
            is_error=True,
            content={"error": f"not a directory: {agent_dir}"},
        )

    env_vars = stack.agent.environment.env_vars
    existing = env_vars.get("generated_files") or {}
    if existing and not replace:
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    "files are already in progress; loading on top of them "
                    "would mix two agents into one directory"
                ),
                "in_progress": sorted(existing),
            },
        )

    files, skipped = _collect(agent_dir)
    if not files:
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    f"{agent_dir} holds no agent files -- expected "
                    "configs/, tasks/, templates/ or tools/"
                ),
                "skipped": skipped[:20],
            },
        )

    total = sum(len(content) for content in files.values())
    if total > MAX_TOTAL_CHARS:
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    f"{agent_dir} holds {total} characters of agent files, "
                    f"over the {MAX_TOTAL_CHARS} limit -- is this an agent "
                    "directory?"
                ),
                "files": len(files),
            },
        )

    env_vars["generated_files"] = files
    env_vars["loaded_agent_path"] = str(agent_dir)
    adopt_existing_files(env_vars, agent_dir, files)

    edited_by_hand = hand_modified(agent_dir, files)
    return ToolResponse(
        is_error=False,
        content={
            "agent_path": str(agent_dir),
            "manifest": _manifest(files),
            "characters": total,
            "skipped": skipped,
            # Files a person changed after Hugin wrote them. Regenerating one
            # of these discards hand-written work, so they are worth reading
            # before touching -- and worth leaving alone if the instruction
            # does not require them.
            "hand_modified": edited_by_hand,
            "not_written_by_hugin": untracked(agent_dir, files),
            "message": (
                f"Loaded {len(files)} file(s). Read a file with "
                "read_generated_file before regenerating it -- regenerating "
                "unread discards whatever is already in it."
            ),
        },
    )


def _manifest(files: Dict[str, str]) -> List[Dict[str, object]]:
    """Return one entry per loaded file: path, lines and characters."""
    return [
        {
            "path": key,
            "lines": files[key].count("\n") + 1,
            "characters": len(files[key]),
        }
        for key in sorted(files)
    ]
