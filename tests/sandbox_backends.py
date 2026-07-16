"""Shared backend gating for the cross-backend sandbox suites.

Both the behaviour-contract suite (``test_sandbox_contract.py``) and the
full-loop drive (``test_bash_e2e_backends.py``) parametrize over the same three
backends with the same availability rules: ``local`` always runs; ``docker`` and
``ssh`` are ``slow``-marked and skip when their runtime is absent. This module
holds that one definition so the two suites can never drift apart on what
"available" means. It is not a test module (no ``test_`` prefix), so pytest does
not collect it.
"""

import os

import pytest

from gimle.hugin.sandbox import SandboxSpec

DAEMON_IMAGE = "python:3.12-slim"
SSH_HOST = os.environ.get("HUGIN_SSH_TEST_HOST")
SSH_KEY = os.environ.get("HUGIN_SSH_TEST_KEY")

# local always runs; docker/ssh are slow-marked so `-m "not slow"` narrows the
# default run to the always-available backend.
ALL_BACKENDS = [
    pytest.param("local", id="local"),
    pytest.param("docker", id="docker", marks=pytest.mark.slow),
    pytest.param("ssh", id="ssh", marks=pytest.mark.slow),
]
ISOLATING_BACKENDS = [
    pytest.param("docker", id="docker", marks=pytest.mark.slow),
    pytest.param("ssh", id="ssh", marks=pytest.mark.slow),
]


def docker_available() -> bool:
    """Return whether a docker SDK and a reachable daemon are both present."""
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


def opts_for(name: str) -> dict:
    """Return an ``options.bash`` dict for ``name``, or skip if runtime is absent.

    This is the primitive both suites share: the contract suite turns it into a
    :class:`SandboxSpec` directly, while the full-loop suite drops it into an
    agent's ``options.bash`` so the real config-resolution path builds the
    backend.
    """
    if name == "local":
        return {"backend": "local"}
    if name == "docker":
        if not docker_available():
            pytest.skip("requires a reachable docker daemon")
        return {"backend": "docker", "image": DAEMON_IMAGE, "memory": "512m"}
    if name == "ssh":
        if not SSH_HOST:
            pytest.skip("set HUGIN_SSH_TEST_HOST=user@box to run")
        return {"backend": "ssh", "host": SSH_HOST, "ssh_key": SSH_KEY}
    raise AssertionError(f"unknown backend param: {name}")


def spec_for(name: str) -> SandboxSpec:
    """Return a spec for ``name``, or ``pytest.skip`` if its runtime is absent."""
    return SandboxSpec.from_dict(opts_for(name))
