"""Write generated files to disk."""

import errno
import hashlib
import logging
import os
import shlex
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Tuple

from gimle.hugin.apps.agent_builder.tools.agent_paths import (
    PathConfinementError,
    check_output_path,
    confine,
    materialise,
    validate_generated_keys,
)
from gimle.hugin.apps.agent_builder.tools.validate_agent import (
    validate_files,
    validate_with_state,
)
from gimle.hugin.tools.tool import ToolResponse

if TYPE_CHECKING:
    from gimle.hugin.interaction.stack import Stack

logger = logging.getLogger(__name__)

_OWNERSHIP_STATE = "agent_builder_written_files"
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _first_task_name(generated_files: Dict[str, str]) -> Optional[str]:
    """Return the stem of the first generated task, for the run command."""
    for key in sorted(generated_files):
        if key.startswith("tasks/") and key.endswith(".yaml"):
            return Path(key).stem
    return None


def _classify(
    files: Dict[str, str], output_dir: Path, owned: Dict[str, str]
) -> Tuple[Dict[str, str], List[str], List[str], List[str]]:
    """Split files into writable, unchanged, conflicting, and escaping sets.

    A differing file is writable only when its current content still matches
    the hash recorded when this builder session wrote it. Unknown or edited
    files are conflicts, preventing a re-run from destroying user changes.
    """
    to_write: Dict[str, str] = {}
    unchanged: List[str] = []
    conflicts: List[str] = []
    escaping: List[str] = []

    for key, content in files.items():
        try:
            current = _read_confined(output_dir, key)
        except FileNotFoundError:
            to_write[key] = content
            continue
        except PathConfinementError as error:
            escaping.append(str(error))
            continue
        except OSError as error:
            conflicts.append(f"{key}: cannot inspect existing file: {error}")
            continue

        desired = content.encode("utf-8")
        if current == desired:
            unchanged.append(key)
        elif owned.get(key) == _digest(current):
            to_write[key] = content
        else:
            conflicts.append(key)

    return to_write, unchanged, conflicts, escaping


def _as_bool(value: object) -> bool:
    """Coerce an LLM-supplied argument to a bool.

    Tool arguments arrive unconverted, so a plain truthiness test made the
    string "false" enable dry-run and silently skip the write while reporting
    success.
    """
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _digest(content: bytes) -> str:
    """Return the ownership hash for file content."""
    return hashlib.sha256(content).hexdigest()


def _root_key(output_dir: Path) -> str:
    """Return a stable key that scopes ownership to one output directory."""
    return os.path.realpath(output_dir)


def _owned_files(env_vars: Dict[str, Any], output_dir: Path) -> Dict[str, str]:
    """Return validated ownership hashes for ``output_dir``."""
    state = env_vars.get(_OWNERSHIP_STATE)
    if not isinstance(state, dict):
        return {}
    owned = state.get(_root_key(output_dir))
    if not isinstance(owned, dict):
        return {}
    return {
        key: value
        for key, value in owned.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _set_owned_files(
    env_vars: Dict[str, Any], output_dir: Path, owned: Dict[str, str]
) -> None:
    """Persist ownership hashes without mixing different output directories."""
    existing = env_vars.get(_OWNERSHIP_STATE)
    state = dict(existing) if isinstance(existing, dict) else {}
    root = _root_key(output_dir)
    if owned:
        state[root] = dict(sorted(owned.items()))
    else:
        state.pop(root, None)
    env_vars[_OWNERSHIP_STATE] = state


@contextmanager
def _open_directory_tree(path: Path, create: bool) -> Iterator[int]:
    """Open every directory component with ``O_NOFOLLOW``.

    Holding a descriptor for each next hop while it is opened closes the parent
    symlink race left by resolving a full path and protecting only its final
    component.
    """
    absolute = Path(os.path.abspath(path))
    descriptor = os.open(absolute.anchor, _DIRECTORY_FLAGS)
    try:
        for component in absolute.parts[1:]:
            if create:
                try:
                    os.mkdir(component, 0o777, dir_fd=descriptor)
                except FileExistsError:
                    pass
            next_descriptor = os.open(
                component, _DIRECTORY_FLAGS, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = next_descriptor
        yield descriptor
    except OSError as error:
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise PathConfinementError(
                f"refusing a symlinked output path component: {path}"
            ) from error
        raise
    finally:
        os.close(descriptor)


@contextmanager
def _open_confined_parent(
    root: Path, key: str, create: bool
) -> Iterator[Tuple[int, str]]:
    """Yield a no-follow descriptor and basename for a generated key."""
    confine(root, key)  # Validate the key and reject already-present escapes.
    parts = Path(key).parts
    with _open_directory_tree(root, create=create) as root_descriptor:
        descriptor = os.dup(root_descriptor)
        try:
            for component in parts[:-1]:
                if create:
                    try:
                        os.mkdir(component, 0o777, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                next_descriptor = os.open(
                    component, _DIRECTORY_FLAGS, dir_fd=descriptor
                )
                os.close(descriptor)
                descriptor = next_descriptor
            yield descriptor, parts[-1]
        except OSError as error:
            if error.errno in {
                errno.ELOOP,
                errno.ENOTDIR,
            }:
                raise PathConfinementError(
                    f"generated file {key!r} crosses a symlinked directory"
                ) from error
            raise
        finally:
            os.close(descriptor)


def _read_confined(root: Path, key: str) -> bytes:
    """Read a generated path without following any symlink component."""
    with _open_confined_parent(root, key, create=False) as (parent, name):
        try:
            descriptor = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent
            )
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise PathConfinementError(
                    f"generated file {key!r} is a symlink"
                ) from error
            raise
        with os.fdopen(descriptor, "rb") as stream:
            return stream.read()


def _write_confined(root: Path, key: str, content: str) -> None:
    """Atomically write content without following any symlink component.

    The temporary file and destination are addressed relative to a securely
    opened parent directory. ``os.replace`` replaces a final-component symlink
    rather than following it and avoids truncating a good file on a short write.
    """
    with _open_confined_parent(root, key, create=True) as (parent, name):
        temporary = f".{name}.hugin-{uuid.uuid4().hex}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o666,
            dir_fd=parent,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(
                temporary,
                name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
            )
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass


def _unlink_owned(root: Path, key: str, expected_hash: str) -> bool:
    """Remove an unmodified builder-owned file, returning whether it existed."""
    try:
        current = _read_confined(root, key)
    except FileNotFoundError:
        return False
    if _digest(current) != expected_hash:
        raise FileExistsError(f"superseded file was modified: {key}")
    with _open_confined_parent(root, key, create=False) as (parent, name):
        os.unlink(name, dir_fd=parent)
    return True


def write_agent_files(
    stack: "Stack",
    output_path: str,
    agent_name: str = "",
    dry_run: bool = False,
) -> ToolResponse:
    """Write the generated agent files to ``output_path``.

    Writes are incremental and ownership-aware. Unknown or user-modified files
    are never overwritten. Files written by this builder session may be updated
    while their content still matches its recorded hash, and may be removed when
    an unmodified file is superseded by a later generation.

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

    # The enforcement point. Validation lives here rather than in a prompt
    # instructing the model to check first, because a prompt is a request: the
    # model can skip it, and two instructions in this same directory already
    # show that happening. There is deliberately no parameter that turns this
    # off -- an escape hatch the model can reach is not a gate.
    report = validate_with_state(generated_files, env_vars)
    if not report["ok"]:
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    "Refusing to write: the generated agent does not "
                    f"validate ({report['summary']}). Fix these and call "
                    "write_agent_files again."
                ),
                "errors": report["errors"],
                "warnings": report["warnings"],
            },
        )

    files = materialise(
        generated_files,
        agent_name=agent_name,
        description=user_input.get("description", "A Hugin agent"),
        output_path=output_path,
        task_name=_first_task_name(generated_files),
        observed_imports=report.get("observed_imports"),
        warnings=[
            f"{w['file']}: {w['message']}" for w in report.get("warnings", [])
        ],
        include_framework=not env_vars.get("loaded_agent_path"),
    )

    output_dir = Path(output_path).expanduser()
    owned = _owned_files(env_vars, output_dir)
    to_write, unchanged, conflicts, escaping = _classify(
        files, output_dir, owned
    )
    if escaping:
        return ToolResponse(
            is_error=True,
            content={
                "error": "Generated files escape the output directory",
                "escaping": escaping,
            },
        )
    unauthorised = _unauthorised(to_write, env_vars)
    if unauthorised:
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    "Refusing to write files outside the authorised set. "
                    "Regenerate only what the instruction asked for, or "
                    "re-run without --only."
                ),
                "unauthorised": sorted(unauthorised),
                "authorised": sorted(env_vars.get("authorised_keys") or []),
            },
        )

    if conflicts:
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    "Refusing to overwrite files not owned by this builder "
                    "session, or files modified since it wrote them"
                ),
                "conflicts": sorted(conflicts),
            },
        )

    superseded, superseded_conflicts = _classify_superseded(
        owned, files, output_dir
    )
    if superseded_conflicts:
        return ToolResponse(
            is_error=True,
            content={
                "error": (
                    "Refusing to remove superseded files that were modified "
                    "after the builder wrote them"
                ),
                "conflicts": sorted(superseded_conflicts),
            },
        )

    preserved = [
        key
        for key in _existing_unmanaged(output_dir, files)
        if key not in superseded
    ]

    # ``await_confirmation`` is edit mode's hold: the writer previews, the CLI
    # shows the diff and asks, and only then clears the flag and calls again.
    # Kept separate from ``dry_run`` so the two cannot be confused -- a dry run
    # never writes, this one is waiting to.
    requested_dry_run = (
        _as_bool(dry_run)
        or _as_bool(user_input.get("dry_run", False))
        or _as_bool(env_vars.get("await_confirmation", False))
    )
    if requested_dry_run:
        preview = {
            "output_path": str(output_dir),
            "dry_run": True,
            "would_write": sorted(to_write),
            "would_remove": sorted(superseded),
            "unchanged": sorted(unchanged),
            "preserved": preserved,
            "message": f"Would write {len(to_write)} file(s) to {output_dir}",
        }
        env_vars["dry_run_result"] = preview
        return ToolResponse(is_error=False, content=preview)

    written: List[str] = []
    try:
        for key, content in to_write.items():
            _write_confined(output_dir, key, content)
            written.append(key)
    except (OSError, PathConfinementError) as error:
        partial_owned = dict(owned)
        partial_owned.update(
            _ownership_after_write(owned, files, unchanged, written)
        )
        _set_owned_files(
            env_vars,
            output_dir,
            partial_owned,
        )
        return ToolResponse(
            is_error=True,
            content={
                "error": f"Failed writing agent files: {error}",
                "written_before_failure": written,
            },
        )

    removed: List[str] = []
    removal_errors: List[str] = []
    for key, expected_hash in superseded.items():
        try:
            if _unlink_owned(output_dir, key, expected_hash):
                removed.append(key)
        except (OSError, PathConfinementError) as error:
            removal_errors.append(f"{key}: {error}")

    final_owned = _ownership_after_write(owned, files, unchanged, written)
    for key in removal_errors:
        failed_key = key.split(":", 1)[0]
        if failed_key in owned:
            final_owned[failed_key] = owned[failed_key]
    _set_owned_files(env_vars, output_dir, final_owned)

    if removal_errors:
        return ToolResponse(
            is_error=True,
            content={
                "error": "Failed removing superseded builder-owned files",
                "written": sorted(written),
                "removed": sorted(removed),
                "removal_errors": sorted(removal_errors),
                "preserved": preserved,
            },
        )

    # ``create_agent`` uses this marker to distinguish an actual write from a
    # model merely claiming that it finished. Set it only after every required
    # write and removal has completed successfully.
    env_vars["written_keys"] = sorted(files)
    # What actually changed on disk, as opposed to the whole payload. An edit
    # reports this: "wrote 1 file" is the evidence that it was surgical, and
    # `written_keys` (every file considered) cannot show that.
    env_vars["changed_keys"] = sorted(written)
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


def _unauthorised(
    to_write: Dict[str, str], env_vars: Dict[str, Any]
) -> List[str]:
    """Return the pending writes the caller did not authorise.

    ``--only`` bounds an edit's blast radius deterministically. The spec asked
    for this set to be *derived from the instruction*, which would mean asking
    a model which files a sentence implies -- a guess, enforcing itself. A list
    the caller states is the same protection without the guesswork, and an
    unattended edit is the case that needs it: an interactive one already shows
    a diff and asks.

    An empty or absent list authorises everything, so this is inert unless
    asked for.
    """
    authorised = env_vars.get("authorised_keys")
    if not authorised:
        return []
    allowed = set(authorised)
    return [key for key in to_write if key not in allowed]


def _classify_superseded(
    owned: Dict[str, str], files: Dict[str, str], output_dir: Path
) -> Tuple[Dict[str, str], List[str]]:
    """Return safely removable superseded files and modified conflicts."""
    removable: Dict[str, str] = {}
    conflicts: List[str] = []
    for key, expected_hash in owned.items():
        if key in files:
            continue
        try:
            current = _read_confined(output_dir, key)
        except FileNotFoundError:
            continue
        except (OSError, PathConfinementError) as error:
            conflicts.append(f"{key}: cannot inspect existing file: {error}")
            continue
        if _digest(current) == expected_hash:
            removable[key] = expected_hash
        else:
            conflicts.append(key)
    return removable, conflicts


def _ownership_after_write(
    previous: Dict[str, str],
    files: Dict[str, str],
    unchanged: List[str],
    written: List[str],
) -> Dict[str, str]:
    """Return ownership for files actually written or still builder-owned."""
    result: Dict[str, str] = {}
    for key in written:
        result[key] = _digest(files[key].encode("utf-8"))
    for key in unchanged:
        desired_hash = _digest(files[key].encode("utf-8"))
        if previous.get(key) == desired_hash:
            result[key] = desired_hash
    return result


def dump_rejected(
    generated_files: Dict[str, str], output_path: str
) -> Optional[str]:
    """Write an unwritable payload to a fresh ``<output_path>.rejected*``.

    A build that fails validation, errors, or runs out of steps has still cost
    the user a full multi-stage run. Leaving them with nothing on disk is worse
    than the destructive behaviour this all replaced: they cannot see what was
    produced, cannot hand-fix it, and cannot tell what went wrong. So the last
    payload is always landed somewhere they can look, next to -- never inside --
    the directory they asked for.

    Returns the directory written, or None if there was nothing to write.
    """
    if not generated_files or not output_path:
        return None

    report = validate_files(generated_files)
    try:
        rejected = _reserve_rejected_directory(output_path)
        for key, content in generated_files.items():
            try:
                _write_confined(rejected, key, content)
            except (PathConfinementError, OSError):
                # A key that cannot be confined is exactly what the rescue
                # path must not write; skip it rather than fall back to a
                # plain join, which is how the main write path used to escape.
                continue
        _write_confined(
            rejected,
            "VALIDATION_REPORT.md",
            _rejection_report(report, output_path, str(rejected)),
        )
    except (OSError, PathConfinementError) as error:
        logger.warning("Could not write rejected payload: %s", error)
        return None
    return str(rejected)


def _reserve_rejected_directory(output_path: str) -> Path:
    """Create a fresh rejected-payload directory without deleting anything."""
    expanded = Path(output_path).expanduser()
    base = Path(f"{str(expanded).rstrip('/')}.rejected")
    candidate = base
    while True:
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            candidate = Path(f"{base}-{uuid.uuid4().hex[:8]}")


def _rejection_report(
    report: Dict[str, Any], output_path: str, rejected_path: str
) -> str:
    """Explain why the build did not land, and what to do next."""
    lines = [
        "# Build did not complete",
        "",
        "These are the files the builder had produced when it stopped. They "
        "were not written to the target directory because they did not pass "
        "validation, or the build failed before it got that far.",
        "",
        f"Intended location: `{output_path}`",
        "",
        f"Validation: {report.get('summary', 'not run')}",
        "",
    ]
    errors = report.get("errors") or []
    if errors:
        lines += ["## Errors", ""]
        lines += [
            f"- `{e['file']}` ({e['check']}): {e['message']}" for e in errors
        ]
        lines.append("")
    warnings = report.get("warnings") or []
    if warnings:
        lines += ["## Warnings", ""]
        lines += [
            f"- `{w['file']}` ({w['check']}): {w['message']}" for w in warnings
        ]
        lines.append("")
    lines += [
        "## What to do",
        "",
        "Fix the errors above, then re-check with:",
        "",
        "```bash",
        f"uv run hugin validate {shlex.quote(rejected_path)}",
        "```",
        "",
        "Once it reports no errors, move the directory into place.",
    ]
    return "\n".join(lines) + "\n"


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
    """Deliberately does not register the generated agent. Returns None.

    Writing an agent used to load it straight into the live environment, which
    put its tools into the process-global ``Tool.registry``. A generated tool
    named after a builtin then replaced the real one for every agent in the
    process, and a second generated agent could shadow the first -- neither
    with any warning, because the registry overwrote silently.

    Nothing needs it: ``test_agent`` loads the agent itself, in its own
    environment, after invalidating stale modules. The write step's job is to
    put files on disk.
    """
    del stack, output_dir
    return None


def adopt_existing_files(
    env_vars: Dict[str, Any], output_dir: Path, files: Dict[str, str]
) -> None:
    """Record ``files`` as owned, at the content they were just read with.

    Edit mode reads an agent this builder session did not write, so nothing is
    owned and :func:`_classify` would call every existing file a conflict --
    the writer would refuse the whole edit. Adopting what was read is what
    makes an edit writable at all.

    It gives up less than it appears to. Ownership is keyed on the *hash* read
    at load time, so the guard still fires for the case it exists to catch: a
    file that changes between load and write (someone editing the directory
    while the builder runs) no longer matches and is refused. What is waived is
    only the claim "this session created it", which for an edit is never true.

    Args:
        env_vars: The environment's mutable env_vars mapping.
        output_dir: The directory the files were read from.
        files: The ``{key: content}`` mapping as read from disk.
    """
    owned = _owned_files(env_vars, output_dir)
    owned.update(
        {
            key: _digest(content.encode("utf-8"))
            for key, content in files.items()
        }
    )
    _set_owned_files(env_vars, output_dir, owned)
