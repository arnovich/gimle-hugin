"""End-to-end public-repository-safe probe with independent processes."""

import asyncio
import os
import stat

from gimle.hugin.swarm.experiment import run_experiment
from gimle.hugin.swarm.material import read_node, write_node


def test_separate_process_admission_probe():
    """Exercise the same reproducible harness a contributor runs locally."""
    report = asyncio.run(run_experiment())
    assert report["status"] == "passed"
    assert set(report["checks"]) == {
        "mutual_tls_and_grant_binding",
        "policy_recovery_isolated",
        "permission_denied",
        "foreign_swarm_denied",
    }


def test_generated_tls_material_is_private_and_reloadable(
    swarm_material, probe_files
):
    """Even a permissive process umask cannot expose generated node keys."""
    m = swarm_material
    old = os.umask(0)
    try:
        files = write_node(probe_files / "node", m.alice, m.policy)
    finally:
        os.umask(old)
    assert stat.S_IMODE(files.directory.stat().st_mode) == 0o700
    for path in files.directory.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    node, policy = read_node(files)
    assert node.node_id == m.alice.node_id
    assert policy == m.policy
    # The invitation and offline-root signing keys were never serialized.
    assert set(p.name for p in files.directory.iterdir()) == {
        "key.pem",
        "chain.pem",
        "root.pem",
        "public.json",
    }


def test_child_is_reaped_when_caller_fails(
    swarm_material, probe_files, monkeypatch
):
    """A failing caller cannot leave a child running with credentials on disk."""
    import pytest

    from gimle.hugin.swarm.experiment import child_server

    m = swarm_material
    files = write_node(probe_files / "server", m.bob, m.policy)
    processes = []
    original = asyncio.create_subprocess_exec

    async def capture(*args, **kwargs):
        process = await original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)

    async def scenario():
        with pytest.raises(RuntimeError, match="intentional"):
            async with child_server(files):
                raise RuntimeError("intentional")
        assert len(processes) == 1
        assert processes[0].returncode is not None

    asyncio.run(scenario())


def test_startup_timeout_is_redacted_and_reaps_child(
    swarm_material, probe_files, monkeypatch
):
    """Slow/failed startup has a bounded stage code and leaves no child behind."""
    import pytest

    from gimle.hugin.swarm import experiment

    m = swarm_material
    files = write_node(probe_files / "server", m.bob, m.policy)
    processes = []
    original = asyncio.create_subprocess_exec

    async def capture(*args, **kwargs):
        process = await original(*args, **kwargs)
        processes.append(process)

        async def never_ready():
            await asyncio.Event().wait()
            return b""

        monkeypatch.setattr(process.stdout, "readline", never_ready)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)
    monkeypatch.setattr(experiment, "CHILD_START_TIMEOUT", 0.01)

    async def scenario():
        with pytest.raises(
            experiment.ProbeFailure, match="^child_start_failed$"
        ):
            async with experiment.child_server(files):
                pytest.fail("startup should time out")
        assert processes[0].returncode is not None

    asyncio.run(scenario())
