"""Persistent swarm provisioning uses generated credentials and local files."""

import asyncio
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from gimle.hugin.swarm.admission import PolicyState, verify_credential
from gimle.hugin.swarm.material import write_node
from gimle.hugin.swarm.provisioning import (
    ProvisionError,
    create_admin,
    install_policy,
    issue_invite,
    join_swarm,
    load_node_state,
    refresh_policy,
    renew_node,
)
from gimle.hugin.swarm.transport import ProbeServer
from gimle.hugin.swarm.wire import encode


def test_first_node_persists_independent_identity(tmp_path):
    """A first node survives reload without retaining the invitation key."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    admin, invite, node_dir = (
        tmp_path / "admin",
        tmp_path / "first.invite",
        tmp_path / "node",
    )
    swarm_id = create_admin("research", admin, now)
    issue_invite(admin, {"research": ["read", "post"]}, [], invite, now)
    joined = asyncio.run(
        join_swarm(
            invite,
            node_dir,
            "10.42.0.0/16",
            now,
            initialize_first=True,
            bootstrap_path=admin / "bootstrap.json",
        )
    )
    loaded = load_node_state(node_dir, now)
    assert loaded.node.node_id == joined.node.node_id
    assert loaded.node.node_id != swarm_id
    assert (
        verify_credential(
            loaded.node.credential(),
            loaded.node.der,
            loaded.node.root,
            loaded.policy,
            now,
            "research",
            "post",
        )
        == loaded.node.node_id
    )
    assert sorted(path.name for path in node_dir.iterdir()) == [
        "lock",
        "node.key",
        "ready",
        "state.json",
    ]
    assert "PRIVATE KEY" not in (node_dir / "state.json").read_text()
    assert (node_dir / "node.key").stat().st_mode & 0o077 == 0
    repeated = asyncio.run(
        join_swarm(
            invite,
            node_dir,
            "10.42.0.0/16",
            now,
            initialize_first=True,
            bootstrap_path=admin / "bootstrap.json",
        )
    )
    assert repeated.node.node_id == joined.node.node_id


def test_policy_floor_survives_restart_and_rejects_fork(tmp_path):
    """Policy update is atomic and generation rollback fails after reload."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    admin, invite, node_dir = (
        tmp_path / "admin",
        tmp_path / "join.invite",
        tmp_path / "node",
    )
    create_admin("research", admin, now)
    issue_invite(admin, {"research": ["read"]}, [], invite, now)
    asyncio.run(
        join_swarm(
            invite,
            node_dir,
            "10.42.0.0/16",
            now,
            initialize_first=True,
            bootstrap_path=admin / "bootstrap.json",
        )
    )
    old_policy = json.loads((admin / "policy.json").read_text())
    newer = refresh_policy(admin, now + timedelta(days=1))
    install_policy(node_dir, admin / "policy.json", now + timedelta(days=1))
    assert load_node_state(node_dir, now + timedelta(days=1)).policy == newer
    (tmp_path / "old.json").write_text(json.dumps(old_policy))
    with pytest.raises(ProvisionError):
        install_policy(node_dir, tmp_path / "old.json", now + timedelta(days=1))


def test_secret_output_inside_git_worktree_is_refused(tmp_path, monkeypatch):
    """A caller cannot casually write an admin root into a public checkout."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    (tmp_path / ".git").mkdir()
    with pytest.raises(ProvisionError):
        create_admin("research", tmp_path / "accidental", now)
    assert not (tmp_path / "accidental").exists()


def test_secret_output_rejects_untrusted_writable_ancestor(tmp_path):
    """An untrusted parent cannot race a private directory into existence."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o777)
    shared.chmod(0o777)
    with pytest.raises(ProvisionError, match="unsafe_path"):
        create_admin("research", shared / "admin", now)
    assert not (shared / "admin").exists()


def test_second_node_fetches_seed_policy_without_registration(tmp_path):
    """A reachable seed supplies a signed floor for an independent node."""

    async def run() -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        admin, first_invite, first_dir = (
            tmp_path / "admin",
            tmp_path / "first.invite",
            tmp_path / "first",
        )
        create_admin("research", admin, now)
        issue_invite(
            admin, {"research": ["read", "post"]}, [], first_invite, now
        )
        first = await join_swarm(
            first_invite,
            first_dir,
            "127.0.0.0/8",
            now,
            initialize_first=True,
            bootstrap_path=admin / "bootstrap.json",
        )
        tls_files = write_node(tmp_path / "tls", first.node, first.policy)
        server_policy = PolicyState(first.node.root, first.policy, now)
        async with ProbeServer(first.node, server_policy, tls_files) as port:
            invite = tmp_path / "second.invite"
            issue_invite(
                admin,
                {"research": ["read", "post"]},
                [f"127.0.0.1:{port}"],
                invite,
                now,
            )
            second = await join_swarm(
                invite,
                tmp_path / "second",
                "127.0.0.0/8",
                now,
            )
            assert second.node.node_id != first.node.node_id
            assert second.policy == first.policy

    asyncio.run(run())


def test_unreachable_seed_never_triggers_first_node_fallback(tmp_path):
    """An ordinary join fails closed and does not leave initialized state."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    admin, invite, state = (
        tmp_path / "admin",
        tmp_path / "node.invite",
        tmp_path / "node",
    )
    create_admin("research", admin, now)
    issue_invite(
        admin,
        {"research": ["read"]},
        ["127.0.0.1:1"],
        invite,
        now,
    )
    with pytest.raises(ProvisionError, match="seed_unavailable"):
        asyncio.run(join_swarm(invite, state, "127.0.0.0/8", now))
    assert not state.exists()
    with pytest.raises(ProvisionError, match="seed_required"):
        asyncio.run(
            join_swarm(
                invite,
                state,
                "127.0.0.0/8",
                now,
                bootstrap_path=admin / "bootstrap.json",
            )
        )


def test_day_eight_join_uses_refreshed_seed_policy(tmp_path):
    """An old invite can join after its embedded seven-day floor expires."""

    async def run() -> None:
        issued = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(
            days=8
        )
        current = issued + timedelta(days=8)
        admin, old_invite, first_dir = (
            tmp_path / "admin",
            tmp_path / "first.invite",
            tmp_path / "first",
        )
        create_admin("research", admin, issued)
        issue_invite(admin, {"research": ["read"]}, [], old_invite, issued)
        first = await join_swarm(
            old_invite,
            first_dir,
            "127.0.0.0/8",
            issued,
            initialize_first=True,
            bootstrap_path=admin / "bootstrap.json",
        )
        updated = refresh_policy(admin, current)
        server_policy = PolicyState(first.node.root, first.policy, issued)
        server_policy.update(updated, current)
        tls_files = write_node(tmp_path / "tls", first.node, updated)
        async with ProbeServer(first.node, server_policy, tls_files) as port:
            invited = json.loads(old_invite.read_text())
            invited["seeds"] = [f"127.0.0.1:{port}"]
            old_invite.write_bytes(encode(invited))
            second = await join_swarm(
                old_invite,
                tmp_path / "second",
                "127.0.0.0/8",
                current,
            )
            assert second.policy == updated
            assert second.node.node_id != first.node.node_id

    asyncio.run(run())


def test_join_tries_next_seed_when_first_is_behind_invite(tmp_path):
    """A stale root-signed seed cannot prevent use of a current seed."""

    async def run() -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        admin = tmp_path / "admin"
        initial_invite = tmp_path / "initial.invite"
        create_admin("research", admin, now)
        issue_invite(admin, {"research": ["read"]}, [], initial_invite, now)
        first = await join_swarm(
            initial_invite,
            tmp_path / "first",
            "127.0.0.0/8",
            now,
            initialize_first=True,
            bootstrap_path=admin / "bootstrap.json",
        )
        stale = PolicyState(first.node.root, first.policy, now)
        later = now + timedelta(days=1)
        updated = refresh_policy(admin, later)
        current = PolicyState(first.node.root, first.policy, now)
        current.update(updated, later)
        tls = write_node(tmp_path / "tls", first.node, updated)
        async with ProbeServer(first.node, stale, tls) as old_port:
            async with ProbeServer(first.node, current, tls) as new_port:
                invite = tmp_path / "new.invite"
                issue_invite(
                    admin,
                    {"research": ["read"]},
                    [f"127.0.0.1:{old_port}", f"127.0.0.1:{new_port}"],
                    invite,
                    later,
                )
                joined = await join_swarm(
                    invite, tmp_path / "second", "127.0.0.0/8", later
                )
                assert joined.policy == updated

    asyncio.run(run())


def test_wrong_bootstrap_root_and_broad_mesh_are_refused(tmp_path):
    """Initial formation cannot silently adopt another root or broad network."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    admin, foreign = tmp_path / "admin", tmp_path / "foreign"
    invite = tmp_path / "first.invite"
    create_admin("research", admin, now)
    create_admin("unrelated", foreign, now)
    issue_invite(admin, {"research": ["read"]}, [], invite, now)
    with pytest.raises(ProvisionError):
        asyncio.run(
            join_swarm(
                invite,
                tmp_path / "node",
                "10.42.0.0/16",
                now,
                initialize_first=True,
                bootstrap_path=foreign / "bootstrap.json",
            )
        )
    with pytest.raises(ProvisionError, match="invalid_mesh"):
        asyncio.run(
            join_swarm(
                invite,
                tmp_path / "node",
                "0.0.0.0/0",
                now,
                initialize_first=True,
                bootstrap_path=admin / "bootstrap.json",
            )
        )


def test_private_state_rejects_open_permissions_and_symlinks(tmp_path):
    """A substituted or readable private file is not loaded."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    admin, invite, state = (
        tmp_path / "admin",
        tmp_path / "first.invite",
        tmp_path / "node",
    )
    create_admin("research", admin, now)
    issue_invite(admin, {"research": ["read"]}, [], invite, now)
    asyncio.run(
        join_swarm(
            invite,
            state,
            "10.42.0.0/16",
            now,
            initialize_first=True,
            bootstrap_path=admin / "bootstrap.json",
        )
    )
    key = state / "node.key"
    key.chmod(0o644)
    with pytest.raises(ProvisionError):
        load_node_state(state, now)
    key.chmod(0o600)
    link = tmp_path / "linked.key"
    link.symlink_to(key)
    key.unlink()
    key.symlink_to(link)
    with pytest.raises(ProvisionError):
        load_node_state(state, now)


def test_policy_replacement_failure_keeps_old_floor(tmp_path, monkeypatch):
    """A failed atomic rename leaves the old signed generation readable."""
    import os

    now = datetime.now(timezone.utc).replace(microsecond=0)
    admin, invite, state = (
        tmp_path / "admin",
        tmp_path / "first.invite",
        tmp_path / "node",
    )
    create_admin("research", admin, now)
    issue_invite(admin, {"research": ["read"]}, [], invite, now)
    asyncio.run(
        join_swarm(
            invite,
            state,
            "10.42.0.0/16",
            now,
            initialize_first=True,
            bootstrap_path=admin / "bootstrap.json",
        )
    )
    old = load_node_state(state, now).policy
    refresh_policy(admin, now + timedelta(days=1))

    def fail_rename(source, destination):
        raise OSError("injected failure")

    monkeypatch.setattr(os, "replace", fail_rename)
    with pytest.raises(ProvisionError):
        install_policy(state, admin / "policy.json", now + timedelta(days=1))
    assert load_node_state(state, now).policy == old


def test_public_cli_round_trip_uses_safe_output(tmp_path, monkeypatch, capsys):
    """The documented commands create, issue, join and reload a node."""
    from gimle.hugin.cli import cli

    admin, invite, state = (
        tmp_path / "admin",
        tmp_path / "first.invite",
        tmp_path / "node",
    )

    def call(*arguments):
        monkeypatch.setattr(sys, "argv", ["hugin", "swarm", *arguments])
        assert cli.main() == 0
        output = capsys.readouterr()
        assert output.err == ""
        assert "PRIVATE KEY" not in output.out
        assert str(tmp_path) not in output.out
        return json.loads(output.out)

    created = call("create", "--name", "research", "--output", str(admin))
    assert created["status"] == "created"
    issued = call(
        "invite",
        "--admin",
        str(admin),
        "--scope",
        "research:read,post",
        "--output",
        str(invite),
    )
    assert issued["status"] == "issued"
    joined = call(
        "join",
        "--invite-file",
        str(invite),
        "--state-dir",
        str(state),
        "--mesh-cidr",
        "10.42.0.0/16",
        "--initialize-first",
        "--bootstrap-bundle",
        str(admin / "bootstrap.json"),
    )
    assert joined["status"] == "provisioned"
    status = call("status", "--state-dir", str(state))
    assert status["node_id"] == joined["node_id"]
    assert status["local_authorization"] == "active"
    assert status["swarm_id"] == created["swarm_id"]
    refreshed = call("policy-refresh", "--admin", str(admin))
    assert refreshed["generation"] == 2
    installed = call(
        "policy-install",
        "--state-dir",
        str(state),
        "--policy-file",
        str(admin / "policy.json"),
    )
    assert installed["status"] == "installed"


def test_renewal_preserves_identity_after_grant_rotation(tmp_path):
    """Revoking an old invite does not prevent same-key replacement."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    admin, original, replacement, state = (
        tmp_path / "admin",
        tmp_path / "old.invite",
        tmp_path / "new.invite",
        tmp_path / "node",
    )
    create_admin("research", admin, now)
    old_grant = issue_invite(admin, {"research": ["read"]}, [], original, now)
    first = asyncio.run(
        join_swarm(
            original,
            state,
            "10.42.0.0/16",
            now,
            initialize_first=True,
            bootstrap_path=admin / "bootstrap.json",
        )
    )
    key_before = (state / "node.key").read_bytes()
    later = now + timedelta(days=1)
    refresh_policy(admin, later, revoked_grants=[old_grant])
    issue_invite(admin, {"research": ["read", "post"]}, [], replacement, later)
    renewed = renew_node(state, replacement, later)
    assert renewed.node.node_id == first.node.node_id
    assert (state / "node.key").read_bytes() == key_before
    assert (
        verify_credential(
            renewed.node.credential(),
            renewed.node.der,
            renewed.node.root,
            renewed.policy,
            later,
            "research",
            "post",
        )
        == first.node.node_id
    )
    assert load_node_state(state, later).node.node_id == first.node.node_id


def test_admin_refresh_recovers_after_second_file_write_fails(
    tmp_path, monkeypatch
):
    """A crashed refresh cannot mint an invite from a stale policy."""
    import os

    now = datetime.now(timezone.utc).replace(microsecond=0)
    admin = tmp_path / "admin"
    create_admin("research", admin, now)
    replace = os.replace
    calls = 0

    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected crash boundary")
        replace(source, destination)

    with monkeypatch.context() as patcher:
        patcher.setattr(os, "replace", fail_second)
        with pytest.raises(ProvisionError):
            refresh_policy(admin, now + timedelta(days=1))
    bundled = json.loads((admin / "bootstrap.json").read_text())["policy"]
    assert bundled["payload"]["generation"] == 2
    assert (
        json.loads((admin / "policy.json").read_text())["payload"]["generation"]
        == 1
    )
    invite = tmp_path / "new.invite"
    issue_invite(
        admin, {"research": ["read"]}, [], invite, now + timedelta(days=1)
    )
    assert json.loads((admin / "policy.json").read_text()) == bundled
    assert json.loads(invite.read_text())["policy"] == bundled


def test_swapped_node_key_is_rejected_on_reload(tmp_path):
    """A valid state certificate cannot be paired with a different private key."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    admin, invite, state = (
        tmp_path / "admin",
        tmp_path / "join.invite",
        tmp_path / "node",
    )
    create_admin("research", admin, now)
    issue_invite(admin, {"research": ["read"]}, [], invite, now)
    asyncio.run(
        join_swarm(
            invite,
            state,
            "10.42.0.0/16",
            now,
            initialize_first=True,
            bootstrap_path=admin / "bootstrap.json",
        )
    )
    wrong = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    (state / "node.key").write_bytes(wrong)
    with pytest.raises(ProvisionError):
        load_node_state(state, now)


def test_renew_uses_newer_local_policy_than_invite(tmp_path):
    """An older valid invitation does not lower a refreshed node's floor."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    admin, invite, state = (
        tmp_path / "admin",
        tmp_path / "join.invite",
        tmp_path / "node",
    )
    create_admin("research", admin, now)
    issue_invite(admin, {"research": ["read"]}, [], invite, now)
    asyncio.run(
        join_swarm(
            invite,
            state,
            "10.42.0.0/16",
            now,
            initialize_first=True,
            bootstrap_path=admin / "bootstrap.json",
        )
    )
    later = now + timedelta(days=1)
    newer = refresh_policy(admin, later)
    install_policy(state, admin / "policy.json", later)
    assert renew_node(state, invite, later).policy == newer


def test_status_reports_expired_authorization(tmp_path, monkeypatch, capsys):
    """Identity can still be inspected when the local policy has expired."""
    from gimle.hugin.cli import cli

    issued = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(
        days=8
    )
    admin, invite, state = (
        tmp_path / "admin",
        tmp_path / "join.invite",
        tmp_path / "node",
    )
    create_admin("research", admin, issued)
    issue_invite(admin, {"research": ["read"]}, [], invite, issued)
    asyncio.run(
        join_swarm(
            invite,
            state,
            "10.42.0.0/16",
            issued,
            initialize_first=True,
            bootstrap_path=admin / "bootstrap.json",
        )
    )
    monkeypatch.setattr(
        sys, "argv", ["hugin", "swarm", "status", "--state-dir", str(state)]
    )
    assert cli.main() == 0
    assert (
        json.loads(capsys.readouterr().out)["local_authorization"] == "inactive"
    )


def test_out_of_mesh_seed_is_rejected_before_persistence(tmp_path):
    """Even a first node never stores a seed outside its configured mesh."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    admin, invite, state = (
        tmp_path / "admin",
        tmp_path / "join.invite",
        tmp_path / "node",
    )
    create_admin("research", admin, now)
    issue_invite(admin, {"research": ["read"]}, ["10.99.0.1:8000"], invite, now)
    with pytest.raises(ProvisionError, match="invalid_seed"):
        asyncio.run(
            join_swarm(
                invite,
                state,
                "10.42.0.0/16",
                now,
                initialize_first=True,
                bootstrap_path=admin / "bootstrap.json",
            )
        )
    assert not state.exists()


def test_concurrent_refresh_preserves_both_revocations(tmp_path):
    """Authority transactions serialize generation and revocation updates."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    admin = tmp_path / "admin"
    create_admin("research", admin, now)
    one, two = "a" * 64, "b" * 64
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(refresh_policy, admin, now, revoked_nodes=[one]),
            executor.submit(refresh_policy, admin, now, revoked_nodes=[two]),
        ]
        for future in futures:
            future.result()
    policy = json.loads((admin / "policy.json").read_text())
    assert policy["payload"]["generation"] == 3
    assert policy["payload"]["revoked_nodes"] == [one, two]


def test_concurrent_join_returns_one_persistent_identity(tmp_path, monkeypatch):
    """Two cold boot processes converge on the first published node state."""
    from gimle.hugin.swarm import provisioning

    now = datetime.now(timezone.utc).replace(microsecond=0)
    admin, invite, state = (
        tmp_path / "admin",
        tmp_path / "join.invite",
        tmp_path / "node",
    )
    create_admin("research", admin, now)
    issue_invite(admin, {"research": ["read"]}, [], invite, now)
    original = provisioning.create_directory
    barrier = Barrier(2)

    def overlap(path, files):
        barrier.wait(timeout=10)
        return original(path, files)

    monkeypatch.setattr(provisioning, "create_directory", overlap)

    def join():
        return asyncio.run(
            join_swarm(
                invite,
                state,
                "10.42.0.0/16",
                now,
                initialize_first=True,
                bootstrap_path=admin / "bootstrap.json",
            )
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = [
            future.result().node.node_id
            for future in [executor.submit(join), executor.submit(join)]
        ]
    assert ids[0] == ids[1] == load_node_state(state, now).node.node_id


def test_interrupted_initial_directory_does_not_block_retry(
    tmp_path, monkeypatch
):
    """An unpublished staging directory never appears as node state."""
    from gimle.hugin.swarm import _provision_io

    now = datetime.now(timezone.utc).replace(microsecond=0)
    admin, invite, state = (
        tmp_path / "admin",
        tmp_path / "join.invite",
        tmp_path / "node",
    )
    create_admin("research", admin, now)
    issue_invite(admin, {"research": ["read"]}, [], invite, now)
    original = _provision_io._write_once
    calls = 0

    def fail_after_first(path, data):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected write failure")
        original(path, data)

    with monkeypatch.context() as patcher:
        patcher.setattr(_provision_io, "_write_once", fail_after_first)
        with pytest.raises(ProvisionError):
            asyncio.run(
                join_swarm(
                    invite,
                    state,
                    "10.42.0.0/16",
                    now,
                    initialize_first=True,
                    bootstrap_path=admin / "bootstrap.json",
                )
            )
    assert not state.exists()
    joined = asyncio.run(
        join_swarm(
            invite,
            state,
            "10.42.0.0/16",
            now,
            initialize_first=True,
            bootstrap_path=admin / "bootstrap.json",
        )
    )
    assert load_node_state(state, now).node.node_id == joined.node.node_id


def test_repeat_join_with_expired_policy_fails_inactive(tmp_path):
    """A retry cannot report successful admission from stale local state."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    admin, invite, state = (
        tmp_path / "admin",
        tmp_path / "join.invite",
        tmp_path / "node",
    )
    create_admin("research", admin, now)
    issue_invite(admin, {"research": ["read"]}, [], invite, now)
    asyncio.run(
        join_swarm(
            invite,
            state,
            "10.42.0.0/16",
            now,
            initialize_first=True,
            bootstrap_path=admin / "bootstrap.json",
        )
    )
    with pytest.raises(ProvisionError, match="authorization_inactive"):
        asyncio.run(
            join_swarm(
                invite,
                state,
                "10.42.0.0/16",
                now + timedelta(days=8),
                initialize_first=True,
                bootstrap_path=admin / "bootstrap.json",
            )
        )


def test_renew_without_new_seed_flags_preserves_contacts(tmp_path):
    """A replacement invite with no hints does not erase saved contacts."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    admin, invite, replacement, state = (
        tmp_path / "admin",
        tmp_path / "join.invite",
        tmp_path / "replacement.invite",
        tmp_path / "node",
    )
    create_admin("research", admin, now)
    issue_invite(
        admin, {"research": ["read"]}, ["10.42.0.10:7443"], invite, now
    )
    asyncio.run(
        join_swarm(
            invite,
            state,
            "10.42.0.0/16",
            now,
            initialize_first=True,
            bootstrap_path=admin / "bootstrap.json",
        )
    )
    issue_invite(admin, {"research": ["read"]}, [], replacement, now)
    assert renew_node(state, replacement, now).seeds == ("10.42.0.10:7443",)
