"""Write generated files to disk."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from gimle.hugin.apps.agent_builder.tools.agent_paths import (
    PathConfinementError,
    check_output_path,
    confine,
    materialise,
    validate_generated_keys,
)
from gimle.hugin.sandbox.sandbox import write_file_nofollow
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
                if target.read_text() == content:
                    unchanged.append(key)
                    continue
            except OSError:
                # Unreadable (permissions, a directory in the way) -- treat as
                # needing a write so the error surfaces at write time.
                pass
        to_write[key] = content

    return to_write, unchanged, escaping


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

    output_dir = Path(output_path)
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

    if dry_run:
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
            write_file_nofollow(str(target), content.encode())
            written.append(key)
    except (OSError, PathConfinementError) as error:
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Failed writing agent files: {error}",
                "written_before_failure": written,
            },
        )

    registered = _register(stack, output_dir)

    return ToolResponse(
        is_error=False,
        content={
            "output_path": str(output_dir),
            "written": sorted(written),
            "unchanged": sorted(unchanged),
            "preserved": preserved,
            "message": f"Wrote {len(written)} file(s) to {output_dir}",
            "registered_config": registered,
        },
    )


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
