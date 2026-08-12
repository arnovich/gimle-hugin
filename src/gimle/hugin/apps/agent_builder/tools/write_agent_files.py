"""Write generated files to disk."""

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from gimle.hugin.apps.agent_builder.tools.agent_paths import (
    PathConfinementError,
    check_output_path,
    confine,
    materialise,
    validate_generated_keys,
)
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

logger = logging.getLogger(__name__)


def _first_task_name(generated_files: Dict[str, str]) -> Optional[str]:
    """Return the stem of the first generated task, for the run command."""
    for key in sorted(generated_files):
        if key.startswith("tasks/") and key.endswith(".yaml"):
            return Path(key).stem
    return None


def _classify(
    files: Dict[str, str], output_dir: Path
) -> Tuple[Dict[str, str], List[str], List[str]]:
    """Split ``files`` into those needing a write and those already correct.

    Returns ``(to_write, unchanged, escaping)``. A file whose on-disk content
    already matches is left alone entirely, so re-running the builder over an
    unchanged agent touches nothing and mtimes stay meaningful.
    """
    to_write: Dict[str, str] = {}
    unchanged: List[str] = []
    escaping: List[str] = []

    for key, content in files.items():
        try:
            target = confine(output_dir, key)
        except PathConfinementError as error:
            escaping.append(str(error))
            continue
        if target.exists():
            try:
                # Explicit utf-8, matching how content is written. The locale
                # default made this comparison wrong off UTF-8, and a
                # UnicodeDecodeError is a ValueError -- not an OSError -- so it
                # escaped the handler below and aborted the whole agent run.
                if target.read_text(encoding="utf-8") == content:
                    unchanged.append(key)
                    continue
            except (OSError, UnicodeDecodeError):
                # Unreadable, or not text -- treat as needing a write so the
                # error surfaces at write time rather than as a traceback.
                pass
        to_write[key] = content

    return to_write, unchanged, escaping


def _as_bool(value: object) -> bool:
    """Coerce an LLM-supplied argument to a bool.

    Tool arguments arrive unconverted, so a plain truthiness test made the
    string "false" enable dry-run and silently skip the write while reporting
    success.
    """
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _write_text(target: Path, content: str) -> None:
    """Write ``content`` without following a symlink at the final component.

    Mirrors ``sandbox.write_file_nofollow`` but leaves the mode to the umask.
    That helper hardcodes 0o600 for sandbox workspaces; generated agents are
    ordinary project files, and 0600 made them unreadable to the service
    account or container user that later runs them.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    handle = os.open(str(target), flags, 0o666)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(content)


def write_agent_files(
    stack: "Stack",
    output_path: str,
    agent_name: str = "",
    dry_run: bool = False,
) -> ToolResponse:
    """Write the generated agent files to ``output_path``.

    Writes are *incremental and additive*: only files whose content differs from
    disk are written, and nothing is ever deleted. A file the user added or
    hand-edited that the builder did not generate is left untouched, which is
    what makes re-running the builder over an existing agent safe.

    This replaces an unconditional ``shutil.rmtree(output_path)`` that destroyed
    whatever the target directory previously held.

    Args:
        stack: Agent stack (auto-injected)
        output_path: Directory where agent files should be written
        agent_name: Optional name of the agent (for the README)
        dry_run: Report what would be written without touching the filesystem

    Returns:
        ToolResponse with the written / unchanged / preserved breakdown
    """
    env_vars = stack.agent.environment.env_vars
    generated_files = env_vars.get("generated_files", {})
    user_input = env_vars.get("user_input", {})

    if not agent_name:
        agent_name = user_input.get("agent_name", "agent")

    if not generated_files:
        return ToolResponse(
            is_error=True,
            content={"error": "No files have been generated yet"},
        )

    path_error = check_output_path(output_path)
    if path_error:
        return ToolResponse(is_error=True, content={"error": path_error})

    key_errors = validate_generated_keys(list(generated_files))
    if key_errors:
        return ToolResponse(
            is_error=True,
            content={
                "error": "Generated file names are not writable",
                "invalid_keys": key_errors,
            },
        )

    files = materialise(
        generated_files,
        agent_name=agent_name,
        description=user_input.get("description", "A Hugin agent"),
        output_path=output_path,
        task_name=_first_task_name(generated_files),
    )

    output_dir = Path(output_path).expanduser()
    to_write, unchanged, escaping = _classify(files, output_dir)
    if escaping:
        return ToolResponse(
            is_error=True,
            content={
                "error": "Generated files escape the output directory",
                "escaping": escaping,
            },
        )

    preserved = _existing_unmanaged(output_dir, files)

    if _as_bool(dry_run):
        return ToolResponse(
            is_error=False,
            content={
                "output_path": str(output_dir),
                "dry_run": True,
                "would_write": sorted(to_write),
                "unchanged": sorted(unchanged),
                "preserved": preserved,
                "message": (
                    f"Would write {len(to_write)} file(s) to {output_dir}"
                ),
            },
        )

    written: List[str] = []
    try:
        for key, content in to_write.items():
            target = confine(output_dir, key)
            target.parent.mkdir(parents=True, exist_ok=True)
            # O_NOFOLLOW closes the gap between the confinement check above and
            # the write: a symlink swapped into the final component afterwards
            # fails the open rather than being written through.
            _write_text(target, content)
            written.append(key)
    except (OSError, PathConfinementError) as error:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Failed writing agent files: {error}",
                "written_before_failure": written,
            },
        )

    removed = _remove_superseded(env_vars, files, output_dir)
    registered = _register(stack, output_dir)

    return ToolResponse(
        is_error=False,
        content={
            "output_path": str(output_dir),
            "written": sorted(written),
            "unchanged": sorted(unchanged),
            "removed": removed,
            "preserved": preserved,
            "message": f"Wrote {len(written)} file(s) to {output_dir}",
            "registered_config": registered,
        },
    )


def _remove_superseded(
    env_vars: Dict[str, Any], files: Dict[str, str], output_dir: Path
) -> List[str]:
    """Delete files this builder wrote earlier but no longer generates.

    Dropping ``rmtree`` removed the invariant that the directory holds exactly
    the current generation. Without this, a builder that regenerates under new
    names mid-session leaves the old config and tools behind, and
    ``load_agent_from_path`` registers *both* -- returning whichever the
    directory happens to yield last, so the user can be handed the obsolete,
    known-broken iteration.

    Only files this tool wrote in this session are removed: the record comes
    from ``env_vars``, never from scanning the directory, so a file the user
    added or hand-edited is still never touched.
    """
    previous = set(env_vars.get("written_keys") or [])
    current = set(files)
    env_vars["written_keys"] = sorted(current)

    removed = []
    for key in sorted(previous - current):
        try:
            target = confine(output_dir, key)
        except PathConfinementError:
            continue
        try:
            if target.is_file():
                target.unlink()
                removed.append(key)
        except OSError as error:
            logger.warning("Could not remove superseded %s: %s", key, error)
    return removed


def _existing_unmanaged(output_dir: Path, files: Dict[str, str]) -> List[str]:
    """List files already on disk that the builder does not manage.

    Surfaced so the caller can see what was deliberately left alone -- the
    previous implementation deleted exactly these without saying so.
    """
    if not output_dir.exists():
        return []
    managed = set(files)
    found = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(output_dir))
        if relative not in managed and "__pycache__" not in relative:
            found.append(relative)
    return found


def _register(stack: "Stack", output_dir: Path) -> Optional[str]:
    """Register the freshly written agent with the live environment.

    Best effort: a generated agent that cannot be loaded is a validation
    concern (PR 1.3), not a reason to report the write itself as failed.
    """
    try:
        environment = stack.agent.environment
        name = environment.load_agent_from_path(str(output_dir))
        if name:
            logger.info("Registered new agent '%s' in environment", name)
        return name
    except Exception as error:  # noqa: BLE001 - registration is advisory
        logger.warning("Could not register generated agent: %s", error)
        return None
