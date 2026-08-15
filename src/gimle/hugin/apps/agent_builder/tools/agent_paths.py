"""Path confinement and name validation for generated agent files.

The builder assembles a ``{relative_path: content}`` dict whose keys come from
LLM-chosen names, then writes it to a user-supplied directory. Both halves are
untrusted input to a filesystem write, so both are checked here rather than at
each call site.

``pathlib`` does not normalise ``..`` and an absolute operand *replaces* the
left-hand side entirely -- ``Path("/a/b") / "/etc/passwd"`` is ``/etc/passwd`` --
so a naive ``output_dir / key`` join writes anywhere the process can reach. The
confinement below mirrors ``sandbox.local.LocalSandbox._confine``: realpath
first so a planted symlink resolves to its target, then verify the result is
still under the root.
"""

import os
import re
import shlex
from pathlib import Path
from typing import Dict, List, Optional

# A generated key is "<dir>/<file>.<yaml|py>", one level deep, relative.
#
# Deliberately permissive about *style* and strict about *shape*. An earlier
# version required snake_case throughout, which conflated two unrelated jobs:
# confinement (a security property -- reject traversal, absolute paths and
# anything that leaves the output directory) and naming taste. Because a
# rejected key aborts the whole write, an LLM naming one tool `getWeather`
# discarded an otherwise complete agent, and `hugin validate` rejected
# hand-written agents containing a perfectly loadable `tools/my-tool.py`.
# Every character allowed here is still safe: no separator, no traversal, no
# absolute path.
GENERATED_KEY = re.compile(
    r"^[A-Za-z0-9_]+/[A-Za-z0-9_][A-Za-z0-9_.\-]*\.(?:yaml|py)$"
)

# Written by the builder itself rather than generated, so exempt from the
# generated-key shape rule (dunder and top-level names would never match it).
# These are fixed constants chosen here, never LLM input, so exempting them
# gives up nothing: confinement still applies to where they resolve.
FRAMEWORK_FILES = (
    "__init__.py",
    "tools/__init__.py",
    "README.md",
    "VALIDATION_REPORT.md",
)


class PathConfinementError(Exception):
    """A generated path escapes, or would escape, its output directory."""


def validate_generated_key(key: str) -> Optional[str]:
    """Return an error message for an unusable generated-file key, else None.

    Rejects absolute keys, traversal, and anything outside the snake_case
    ``<dir>/<name>.<yaml|py>`` shape the generators are supposed to emit.
    """
    if not key or key != key.strip():
        return f"empty or padded file key: {key!r}"
    if os.path.isabs(key) or key.startswith("~"):
        return (
            f"absolute file key {key!r}: an absolute path replaces the "
            "output directory instead of nesting under it"
        )
    if "\\" in key:
        return f"backslash in file key {key!r}: use forward slashes"
    normalised = os.path.normpath(key)
    if normalised.startswith("..") or normalised != key:
        return (
            f"file key {key!r} does not normalise to itself "
            f"(got {normalised!r}): traversal is not allowed"
        )
    if not GENERATED_KEY.match(key):
        return (
            f"file key {key!r} must be '<dir>/<name>.yaml' or "
            "'<dir>/<name>.py', one directory deep"
        )
    return None


def is_exempt(key: str) -> bool:
    """Return True for files the builder writes rather than generates.

    Single source for the exemption, which was previously spelled out twice --
    in opposite orders -- in :func:`validate_generated_keys` and
    :func:`confine`, so the two could disagree about the same key.
    """
    return key in FRAMEWORK_FILES


def validate_generated_keys(keys: List[str]) -> List[str]:
    """Return every error across ``keys``, empty when all are usable."""
    errors = []
    for key in keys:
        if is_exempt(key):
            continue
        error = validate_generated_key(key)
        if error:
            errors.append(error)
    return errors


def confine(root: Path, key: str) -> Path:
    """Resolve ``key`` under ``root``, or raise :class:`PathConfinementError`.

    ``root`` is realpath'd first so the comparison is between two fully
    dereferenced paths; a symlink planted inside the tree that points outside it
    therefore resolves to an outside path and is rejected.
    """
    if not is_exempt(key):
        error = validate_generated_key(key)
        if error:
            raise PathConfinementError(error)

    real_root = Path(os.path.realpath(root))
    resolved = Path(os.path.realpath(real_root / key))
    if resolved != real_root and not str(resolved).startswith(
        str(real_root) + os.sep
    ):
        raise PathConfinementError(
            f"generated file {key!r} escapes the output directory"
        )
    return resolved


def check_output_path(output_path: str) -> Optional[str]:
    """Return an error message for an unsafe output directory, else None.

    ``output_path`` reaches the tool as a plain task parameter, so it may name
    any directory on the machine. Refuse the handful that are never a legitimate
    target for a generated agent and are catastrophic to write into.
    """
    if not output_path or not output_path.strip():
        return "no output path specified"

    # expanduser() first, and everywhere. Without it realpath("~") yields
    # "<cwd>/~" rather than $HOME, so the home-directory and .git guards below
    # silently passed every ~-prefixed path -- while the symlink probe further
    # down *did* expand it, leaving the two halves of this function checking
    # different directories. "~/agents/demo" is exactly what a model passes
    # when the user says "put it in ~/agents/demo".
    expanded = Path(output_path).expanduser()
    resolved = Path(os.path.realpath(expanded))

    if resolved == Path(resolved.anchor):
        return f"refusing to write an agent to the filesystem root: {resolved}"

    home = Path(os.path.realpath(Path.home()))
    if resolved == home:
        return f"refusing to write an agent directly to the home dir: {home}"

    if (resolved / ".git").exists():
        return (
            f"refusing to write an agent into a repository root: {resolved} "
            "contains .git -- point at a subdirectory instead"
        )

    # A symlinked component means the final location is not the one the user
    # named, which defeats every other check here.
    for parent in [expanded, *expanded.parents]:
        if parent.is_symlink():
            return (
                f"refusing to write through a symlinked path component: "
                f"{parent}"
            )
    return None


def materialise(
    generated_files: Dict[str, str],
    agent_name: str,
    description: str,
    output_path: str,
    task_name: Optional[str] = None,
) -> Dict[str, str]:
    """Return the complete file set for an agent, framework files included.

    Shared by the writer and (from PR 1.3) the validator so the tree that gets
    checked is byte-for-byte the tree that gets written -- they cannot drift
    into disagreeing about what an agent directory contains.
    """
    files = dict(generated_files)
    files["__init__.py"] = f'"""Generated Hugin agent: {agent_name}."""\n'
    files["tools/__init__.py"] = '"""Agent tools."""\n'
    files["README.md"] = _readme(
        agent_name, description, output_path, task_name
    )
    return files


def run_command(output_path: str, task_name: Optional[str]) -> str:
    """Return the one true command for running a generated agent.

    Single source for a string that was previously spelled four different ways
    across the writer, the CLI success screen and two docs pages -- one of which
    named a ``run-agent`` entrypoint that does not exist.
    """
    command = ["uv", "run", "hugin", "run"]
    if task_name:
        command.extend(["--task", task_name])
    command.extend(["--task-path", output_path])
    return shlex.join(command)


def _readme(
    agent_name: str,
    description: str,
    output_path: str,
    task_name: Optional[str],
) -> str:
    """Build the generated agent's README."""
    return f"""# {agent_name}

{description}

## Running the Agent

```bash
{run_command(output_path, task_name)}
```

## Structure

- `configs/` - Agent configuration
- `tasks/` - Task definitions
- `templates/` - System prompts
- `tools/` - Custom tools

Generated by Hugin Agent Builder.
"""
