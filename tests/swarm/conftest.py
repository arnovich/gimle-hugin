"""Ephemeral swarm credentials; never load developer credentials."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip("cryptography")
pytest.importorskip("aiohttp")
pytest.importorskip("rfc8785")

from gimle.hugin.swarm.credentials import Authority  # noqa: E402


@pytest.fixture
def swarm_material():
    """Mint unrelated nodes and a policy under a fresh test-only root."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    root = Authority.create(now)
    invite = root.invite({"research": ["read", "post"]}, now)
    return SimpleNamespace(
        now=now,
        root=root,
        invite=invite,
        alice=invite.join(now),
        bob=invite.join(now),
        policy=root.policy(now),
    )


@pytest.fixture
def probe_files(tmp_path):
    """Erase all ephemeral key files even when a transport test fails."""
    from tempfile import TemporaryDirectory

    with TemporaryDirectory(dir=tmp_path) as directory:
        from pathlib import Path

        yield Path(directory)
