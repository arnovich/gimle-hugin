"""Is the agent about to be edited recoverable if the edit goes wrong?

An edit rewrites files in place. The only general-purpose undo for that is the
user's own version control, so an edit into a directory with uncommitted
changes can destroy work that exists nowhere else. That is survivable when
someone is watching -- they see the diff and can say no -- and unrecoverable
when nobody is, which is exactly when `--yes` is used.

This deliberately reports rather than decides. Whether a dirty tree is a
warning or a refusal depends on whether anyone is there to answer, and that is
the caller's question, not this module's.
"""

import subprocess
from pathlib import Path
from typing import List, Optional

# Long enough for a cold index on a large repository, short enough that a
# wedged git cannot hang a build indefinitely.
GIT_TIMEOUT_SECONDS = 10


def _git(arguments: List[str], cwd: Path) -> Optional[str]:
    """Run a read-only git command, or return None if git cannot answer.

    Every failure mode collapses to None on purpose: git missing, the path not
    being a repository, a timeout. None means "no opinion", and the caller
    treats that as "cannot check" rather than as "clean".
    """
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def uncommitted_changes(agent_path: Path) -> Optional[List[str]]:
    """Return uncommitted paths under ``agent_path``, or None if unknown.

    Returns:
        A list of ``git status --porcelain`` lines scoped to the directory --
        empty when the directory is clean -- or None when the question cannot
        be answered (not a repository, no git, git failed).
    """
    if not agent_path.is_dir():
        return None
    if _git(["rev-parse", "--is-inside-work-tree"], agent_path) is None:
        return None
    status = _git(["status", "--porcelain", "--", "."], agent_path)
    if status is None:
        return None
    return [line for line in status.splitlines() if line.strip()]
