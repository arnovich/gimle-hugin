"""Owner-only local files for private swarm provisioning."""

import fcntl
import os
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

MAX_LOCAL_FILE = 65536


class ProvisionError(RuntimeError):
    """Expose only a fixed reason code, never paths or secret material."""

    def __init__(self, code: str = "invalid_local_state") -> None:
        """Keep user-facing failures independent of underlying OS messages."""
        super().__init__(code)


def _check_components(path: Path) -> Path:
    """Refuse symlink components and secret output inside any Git checkout."""
    absolute = Path(os.path.abspath(path))
    for parent in (absolute, *absolute.parents):
        try:
            details = parent.lstat()
        except FileNotFoundError:
            continue
        mode = details.st_mode
        if stat.S_ISLNK(mode):
            raise ProvisionError("unsafe_path")
        if (
            stat.S_ISDIR(mode)
            and mode & 0o022
            and (
                not mode & stat.S_ISVTX
                or details.st_uid not in {0, os.getuid()}
            )
        ):
            raise ProvisionError("unsafe_path")
        if (parent / ".git").exists():
            raise ProvisionError("git_checkout_output")
    return absolute


def _write_once(path: Path, data: bytes) -> None:
    """Create one secret-bearing file without following links or replacing it."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def _sync_directory(directory: Path) -> None:
    descriptor = os.open(
        directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def create_directory(path: Path, files: dict[str, bytes]) -> None:
    """Publish a complete private directory in one rename."""
    if any(
        name in {"", ".", "..", "ready", "lock"} or "/" in name
        for name in files
    ):
        raise ProvisionError()
    path = _check_components(path)
    staging = path.with_name(
        "." + path.name + "." + secrets.token_hex(12) + ".partial"
    )
    published = False
    try:
        staging.mkdir(mode=0o700)
        for name, data in files.items():
            _write_once(staging / name, data)
        _write_once(staging / "lock", b"")
        _write_once(staging / "ready", b"v0\n")
        _sync_directory(staging)
        with _initialization_lock(path):
            if path.exists() or path.is_symlink():
                raise ProvisionError("already_initialized")
            os.rename(staging, path)
            _sync_directory(path.parent)
            published = True
    except (OSError, ValueError):
        raise ProvisionError("local_write_failed") from None
    finally:
        safe_cleanup = False
        if not published:
            try:
                _private_stat(staging, directory=True)
                safe_cleanup = True
            except ProvisionError:
                pass
        if safe_cleanup:
            for name in (*files, "lock", "ready"):
                try:
                    (staging / name).unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                staging.rmdir()
            except OSError:
                pass


@contextmanager
def _initialization_lock(path: Path) -> Iterator[None]:
    """Serialize publication when two processes initialize one destination."""
    lock_path = path.with_name("." + path.name + ".init.lock")
    descriptor = -1
    try:
        descriptor = os.open(
            lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
        )
        before = _private_stat(lock_path)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise ProvisionError("invalid_local_state")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    except OSError:
        raise ProvisionError("local_write_failed") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def create_file(path: Path, data: bytes) -> None:
    """Create a private invite or public bundle with exclusive ownership."""
    try:
        path = _check_components(path)
        _write_once(path, data)
        _sync_directory(path.parent)
    except (OSError, ValueError):
        raise ProvisionError("local_write_failed") from None


def _private_stat(path: Path, *, directory: bool = False) -> os.stat_result:
    """Reject substituted, shared or world-readable provisioning material."""
    try:
        result = path.lstat()
        expected = stat.S_ISDIR if directory else stat.S_ISREG
        if (
            not expected(result.st_mode)
            or result.st_uid != os.getuid()
            or result.st_mode & 0o077
            or (not directory and result.st_nlink != 1)
        ):
            raise ProvisionError("unsafe_permissions")
        return result
    except OSError:
        raise ProvisionError("invalid_local_state") from None


def read_file(path: Path, *, limit: int = MAX_LOCAL_FILE) -> bytes:
    """Read a bounded owner-only regular file through a no-follow descriptor."""
    try:
        before = _private_stat(path)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as source:
            after = os.fstat(source.fileno())
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise ProvisionError("invalid_local_state")
            raw = source.read(limit + 1)
        if len(raw) > limit:
            raise ProvisionError("invalid_local_state")
        return raw
    except OSError:
        raise ProvisionError("invalid_local_state") from None


def read_directory(path: Path) -> None:
    """Require a completed private directory before loading its contents."""
    _private_stat(path, directory=True)
    if read_file(path / "ready") != b"v0\n":
        raise ProvisionError("invalid_local_state")


@contextmanager
def locked_directory(path: Path, *, exclusive: bool) -> Iterator[None]:
    """Hold one stable local lock across an entire policy or identity transaction."""
    read_directory(path)
    lock_path = path / "lock"
    before = _private_stat(lock_path)
    try:
        descriptor = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "r+b") as handle:
            after = os.fstat(handle.fileno())
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise ProvisionError("invalid_local_state")
            flag = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(handle.fileno(), flag)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        raise ProvisionError("invalid_local_state") from None


def replace_file(path: Path, data: bytes) -> None:
    """Atomically replace one private snapshot and persist its directory."""
    temporary = path.with_name(path.name + "." + secrets.token_hex(12))
    try:
        _private_stat(path.parent, directory=True)
        _private_stat(path)
        _write_once(temporary, data)
        os.replace(temporary, path)
        _sync_directory(path.parent)
    except OSError:
        raise ProvisionError("local_write_failed") from None
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
