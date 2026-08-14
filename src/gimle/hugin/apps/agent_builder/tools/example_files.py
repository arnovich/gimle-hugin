"""Secure, bounded access to the example catalogue.

Example contents are included in model context and persisted in interaction
history, so they must be treated as untrusted input even when the catalogue
location was explicitly configured.  All directory components are opened
without following symlinks and all file reads share explicit limits.
"""

import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

MAX_CATALOGUE_ENTRIES = 256
MAX_CATALOGUE_BYTES = 512 * 1024
MAX_EXAMPLE_FILES = 128
MAX_EXAMPLE_BYTES = 512 * 1024
MAX_FILE_BYTES = 128 * 1024


class UnsafeExamplePath(ValueError):
    """Raised when an example path is not a regular, confined path."""


class ExampleReadLimit(ValueError):
    """Raised when example content exceeds the configured read budget."""


@dataclass
class ReadBudget:
    """Track a shared file-count and byte budget across one tool call."""

    max_files: int
    max_bytes: int
    files_read: int = 0
    bytes_read: int = 0

    @property
    def bytes_remaining(self) -> int:
        """Return how many bytes may still be read."""
        return self.max_bytes - self.bytes_read

    def record(self, size: int) -> None:
        """Charge one successfully read file to this budget."""
        if self.files_read >= self.max_files:
            raise ExampleReadLimit(
                f"Example contains more than {self.max_files} readable files"
            )
        if size > self.bytes_remaining:
            raise ExampleReadLimit(
                f"Example content exceeds {self.max_bytes} bytes"
            )
        self.files_read += 1
        self.bytes_read += size


def _directory_flags() -> int:
    """Return flags required for a descriptor-relative directory open."""
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise UnsafeExamplePath(
            "Secure example reads are unsupported on this platform"
        )
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _file_flags() -> int:
    """Return flags required for a no-follow file open."""
    if not hasattr(os, "O_NOFOLLOW"):
        raise UnsafeExamplePath(
            "Secure example reads are unsupported on this platform"
        )
    return os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC


def _is_component(name: str) -> bool:
    """Return whether ``name`` is exactly one portable path component."""
    return bool(
        name
        and name not in (".", "..")
        and "/" not in name
        and "\\" not in name
    )


@contextmanager
def open_directory(path: Path) -> Iterator[int]:
    """Open ``path`` one component at a time without following symlinks."""
    absolute = Path(os.path.abspath(path))
    parts = absolute.parts
    if not parts or parts[0] != os.sep:
        raise UnsafeExamplePath("Examples path must be absolute")

    fd = os.open(os.sep, _directory_flags())
    try:
        for part in parts[1:]:
            if not _is_component(part):
                raise UnsafeExamplePath("Examples path is invalid")
            next_fd = os.open(part, _directory_flags(), dir_fd=fd)
            os.close(fd)
            fd = next_fd
    except OSError as exc:
        os.close(fd)
        raise UnsafeExamplePath(
            "Examples path contains a missing, non-directory, or symlinked component"
        ) from exc
    except Exception:
        os.close(fd)
        raise

    try:
        yield fd
    finally:
        os.close(fd)


@contextmanager
def open_child_directory(parent_fd: int, name: str) -> Iterator[int]:
    """Open one child directory without following a symlink."""
    if not _is_component(name):
        raise UnsafeExamplePath("Example names must be one path component")
    try:
        fd = os.open(name, _directory_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise UnsafeExamplePath(
            f"Example directory '{name}' is missing, invalid, or symlinked"
        ) from exc
    try:
        yield fd
    finally:
        os.close(fd)


def child_directory_names(
    parent_fd: int, *, limit: int = MAX_CATALOGUE_ENTRIES
) -> list[str]:
    """List bounded, non-symlinked child directory names."""
    names: list[str] = []
    for name in sorted(os.listdir(parent_fd)):
        if len(names) >= limit:
            break
        if not _is_component(name):
            continue
        try:
            metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISDIR(metadata.st_mode):
            names.append(name)
    return names


def has_child_directory(parent_fd: int, name: str) -> bool:
    """Return whether ``name`` is a real child directory, never a symlink."""
    if not _is_component(name):
        return False
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISDIR(metadata.st_mode)


def read_text_file(
    parent_fd: int,
    name: str,
    budget: ReadBudget,
    *,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> str:
    """Read one regular UTF-8 file through ``parent_fd`` within ``budget``."""
    if not _is_component(name):
        raise UnsafeExamplePath("Example filenames must be one path component")
    if budget.files_read >= budget.max_files:
        raise ExampleReadLimit(
            f"Example contains more than {budget.max_files} readable files"
        )

    try:
        fd = os.open(name, _file_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise UnsafeExamplePath(
            f"Example file '{name}' is missing, invalid, or symlinked"
        ) from exc

    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise UnsafeExamplePath(
                f"Example file '{name}' is not a regular file"
            )

        read_limit = min(max_file_bytes, budget.bytes_remaining)
        if metadata.st_size > read_limit:
            raise ExampleReadLimit(
                f"Example file '{name}' exceeds the read limit"
            )

        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(fd, min(64 * 1024, read_limit + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > read_limit:
                raise ExampleReadLimit(
                    f"Example file '{name}' exceeds the read limit"
                )

        data = b"".join(chunks)
        budget.record(len(data))
        return data.decode("utf-8")
    finally:
        os.close(fd)


def read_optional_text_file(
    parent_fd: int,
    name: str,
    budget: ReadBudget,
    *,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> Optional[str]:
    """Read a file if present; reject symlinks and other unsafe file types."""
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    return read_text_file(
        parent_fd, name, budget, max_file_bytes=max_file_bytes
    )


def source_examples_path() -> Path:
    """Return the examples directory belonging to this source checkout."""
    return Path(__file__).parents[6] / "examples"


def discover_examples_path() -> Optional[Path]:
    """Find an explicitly configured or source-checkout example catalogue.

    The current working directory is intentionally never consulted: a library
    embedded in another project must not silently ingest that project's files.
    """
    candidates = []
    configured = os.environ.get("HUGIN_EXAMPLES_PATH")
    if configured:
        candidates.append(Path(configured))

    source_path = source_examples_path()
    source_root = source_path.parent
    if (source_root / "pyproject.toml").is_file():
        candidates.append(source_path)

    for candidate in candidates:
        try:
            with open_directory(candidate):
                return Path(os.path.abspath(candidate))
        except (OSError, UnsafeExamplePath):
            continue
    return None
