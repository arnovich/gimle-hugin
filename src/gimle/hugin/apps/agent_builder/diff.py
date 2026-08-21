"""Render what an edit is about to do to a directory, before it does it.

The builder writes from inside the agent run, so by the time the CLI regains
control the files are already changed. For a *new* agent that is fine -- the
directory did not exist. For an edit it is not: the target is someone's
working agent, possibly hand-customised, and the single thing that makes the
tool trustworthy against it is showing the change and asking first.

The comparison is between the payload in memory and the bytes on disk, so it
reflects what the writer would actually do rather than what the model says it
did.
"""

import difflib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# A single file's diff long enough to bury the rest of the review. Truncated
# with a count rather than dropped, so a large rewrite is visible *as* a large
# rewrite instead of looking like a small one.
MAX_DIFF_LINES = 200


def _read(path: Path) -> Optional[str]:
    """Return the file's text, or None when it does not exist or is binary."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def diff_against_disk(
    generated_files: Dict[str, str], output_dir: Path
) -> Tuple[List[str], List[str], List[str]]:
    """Split the payload into changed, added and unchanged keys.

    Returns:
        ``(changed, added, unchanged)``, each a sorted list of payload keys.
    """
    changed, added, unchanged = [], [], []
    for key in sorted(generated_files):
        current = _read(output_dir / key)
        if current is None:
            added.append(key)
        elif current == generated_files[key]:
            unchanged.append(key)
        else:
            changed.append(key)
    return changed, added, unchanged


def render_agent_diff(generated_files: Dict[str, str], output_dir: Path) -> str:
    """Return a unified diff of the pending edit, ready to print."""
    changed, added, unchanged = diff_against_disk(generated_files, output_dir)
    if not changed and not added:
        return "    No file differs from what is already on disk."

    lines: List[str] = []
    for key in changed:
        before = (_read(output_dir / key) or "").splitlines(keepends=True)
        after = generated_files[key].splitlines(keepends=True)
        body = list(
            difflib.unified_diff(
                before, after, fromfile=f"a/{key}", tofile=f"b/{key}"
            )
        )
        lines.extend(_truncate(body, key))

    for key in added:
        lines.append("--- /dev/null\n")
        lines.append(f"+++ b/{key}\n")
        body = [
            f"+{line}"
            for line in generated_files[key].splitlines(keepends=True)
        ]
        lines.extend(_truncate(body, key))

    rendered = "".join(lines).rstrip("\n")
    if unchanged:
        rendered += (
            f"\n\n    {len(unchanged)} file(s) unchanged: "
            f"{', '.join(unchanged)}"
        )
    return rendered


def _truncate(body: List[str], key: str) -> List[str]:
    """Cap one file's diff, saying how much was left out."""
    if len(body) <= MAX_DIFF_LINES:
        return body
    omitted = len(body) - MAX_DIFF_LINES
    return body[:MAX_DIFF_LINES] + [
        f"... {omitted} more diff line(s) for {key}, not shown\n"
    ]
