"""The O_NOFOLLOW confined file IO helpers that guard the put/get TOCTOU.

``put_file``/``get_file`` realpath-confine a path, then open it — a symlink
swapped into the final component between check and open would escape. These pin
that ``O_NOFOLLOW`` refuses to follow such a swap and that the failure surfaces
as a workspace-escape denial, not a raw OSError.
"""

import errno
import os

import pytest

from gimle.hugin.sandbox.sandbox import (
    PolicyDenied,
    read_file_nofollow,
    reject_symlink_swap,
    write_file_nofollow,
)


class TestNoFollowIO:
    """Reading/writing refuses to follow a final-component symlink."""

    def test_roundtrip_on_a_regular_file(self, tmp_path):
        """A regular file reads back exactly what was written."""
        path = str(tmp_path / "f.bin")
        write_file_nofollow(path, b"hello-bytes")
        assert read_file_nofollow(path) == b"hello-bytes"

    def test_read_refuses_a_symlink(self, tmp_path):
        """Reading through a symlink fails with ELOOP, not the target's bytes."""
        outside = tmp_path / "secret.txt"
        outside.write_text("classified")
        link = str(tmp_path / "link")
        os.symlink(str(outside), link)
        with pytest.raises(OSError) as excinfo:
            read_file_nofollow(link)
        assert excinfo.value.errno == errno.ELOOP

    def test_write_refuses_a_symlink_and_leaves_the_target(self, tmp_path):
        """Writing through a symlink fails and does not touch the target."""
        outside = tmp_path / "target.txt"
        outside.write_text("original")
        link = str(tmp_path / "link")
        os.symlink(str(outside), link)
        with pytest.raises(OSError) as excinfo:
            write_file_nofollow(link, b"evil")
        assert excinfo.value.errno == errno.ELOOP
        assert outside.read_text() == "original"  # never written through


class TestRejectSymlinkSwap:
    """ELOOP becomes a denial; every other error propagates unchanged."""

    def test_eloop_becomes_policy_denied(self):
        """A symlink swap (ELOOP) is surfaced as a workspace escape."""
        error = OSError(errno.ELOOP, "too many symbolic links")
        with pytest.raises(PolicyDenied, match="symlink"):
            reject_symlink_swap("notes.txt", error)

    def test_other_errors_propagate(self):
        """A missing file (ENOENT) is not masked as a denial."""
        error = FileNotFoundError(errno.ENOENT, "no such file")
        with pytest.raises(FileNotFoundError):
            reject_symlink_swap("notes.txt", error)
