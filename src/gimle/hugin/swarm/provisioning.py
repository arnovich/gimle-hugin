"""Provision private swarm authorities, invitations, and durable node identity."""

import asyncio
import ipaddress
import re
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from gimle.hugin.swarm._provision_io import (
    ProvisionError,
    create_directory,
    create_file,
    locked_directory,
    read_directory,
    read_file,
    replace_file,
)
from gimle.hugin.swarm.admission import (
    _permissions,
    verify_credential,
    verify_grant,
    verify_policy,
)
from gimle.hugin.swarm.credentials import (
    Authority,
    Invitation,
    Node,
    certificate_key,
    certificate_pem,
    public_id,
    verify_chain,
    verify_issuer,
    verify_root,
    verify_tls_leaf,
)
from gimle.hugin.swarm.wire import ProtocolError, decode, encode, fields


@dataclass(frozen=True)
class NodeState:
    """Loaded local identity and signed policy; never include an invite key."""

    node: Node = field(repr=False)
    policy: dict[str, Any] = field(repr=False)
    seeds: tuple[str, ...] = ()
    mesh_cidr: str = ""


def _key_bytes(key: Ed25519PrivateKey) -> bytes:
    """Serialize a local key only for an owner-only destination."""
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _load_key(raw: bytes) -> Ed25519PrivateKey:
    """Accept only Ed25519 private keys in provisioning material."""
    try:
        key = serialization.load_pem_private_key(raw, None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ProvisionError()
        return key
    except (ValueError, TypeError):
        raise ProvisionError() from None


def _certificate(value: Any) -> x509.Certificate:
    """Load a bounded, single public PEM certificate."""
    try:
        if type(value) is not str or len(value) > 8192:
            raise ProvisionError()
        cert = x509.load_pem_x509_certificate(value.encode("ascii"))
        if certificate_pem(cert) != value:
            raise ProvisionError()
        return cert
    except (
        ValueError,
        TypeError,
        UnicodeError,
        x509.DuplicateExtension,
        x509.UnsupportedGeneralNameType,
        x509.InvalidVersion,
    ):
        raise ProvisionError() from None


def _parse_seed(
    value: str,
) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, int]:
    """Permit numeric private-mesh hints only, avoiding DNS rebinding."""
    try:
        if value.startswith("["):
            host, separator, port_text = value[1:].partition("]:")
            if not separator:
                raise ValueError()
        else:
            host, separator, port_text = value.rpartition(":")
            if not separator or ":" in host:
                raise ValueError()
        address = ipaddress.ip_address(host)
        port = int(port_text)
        if (
            not 1 <= port <= 65535
            or address.is_multicast
            or address.is_unspecified
        ):
            raise ValueError()
        return address, port
    except ValueError:
        raise ProvisionError("invalid_seed") from None


def _mesh(cidr: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    """Reject an internet-wide mesh CIDR before any seed connection."""
    try:
        network = ipaddress.ip_network(cidr, strict=True)
        floor = 8 if network.version == 4 else 32
        if network.is_global or network.prefixlen < floor:
            raise ValueError()
        return network
    except ValueError:
        raise ProvisionError("invalid_mesh") from None


def _seeds(values: Any) -> tuple[str, ...]:
    """Bound and normalize bootstrap contacts before reading or writing."""
    if type(values) is not list or len(values) > 16:
        raise ProvisionError("invalid_seed")
    result: list[str] = []
    for value in values:
        if type(value) is not str or len(value) > 64:
            raise ProvisionError("invalid_seed")
        address, port = _parse_seed(value)
        formatted = (
            f"[{address}]:{port}"
            if address.version == 6
            else f"{address}:{port}"
        )
        if formatted != value or value in result:
            raise ProvisionError("invalid_seed")
        result.append(value)
    return tuple(result)


def _mesh_seeds(
    contacts: tuple[str, ...],
    mesh: ipaddress.IPv4Network | ipaddress.IPv6Network,
) -> None:
    """Require every durable seed hint to belong to the selected mesh."""
    if any(_parse_seed(contact)[0] not in mesh for contact in contacts):
        raise ProvisionError("invalid_seed")


def _load_admin(path: Path, now: datetime) -> tuple[Authority, dict[str, Any]]:
    """Load a completed offline authority without exposing its root key."""
    read_directory(path)
    key = _load_key(read_file(path / "root.key", limit=8192))
    root = _certificate(
        read_file(path / "root.pem", limit=8192).decode("ascii")
    )
    verify_root(root, now)
    if public_id(key.public_key()) != public_id(certificate_key(root)):
        raise ProvisionError()
    policy = decode(read_file(path / "policy.json"))
    current = verify_policy(policy, root, now, allow_expired=True)
    bootstrap = decode(read_file(path / "bootstrap.json"))
    fields(bootstrap, {"v", "kind", "name", "root", "policy"})
    if (
        type(bootstrap["v"]) is not int
        or bootstrap["v"] != 0
        or bootstrap["kind"] != "bootstrap"
        or _certificate(bootstrap["root"]) != root
    ):
        raise ProvisionError()
    bundled = bootstrap["policy"]
    newer = verify_policy(bundled, root, now, allow_expired=True)
    if newer.generation < current.generation or (
        newer.generation == current.generation
        and encode(bundled) != encode(policy)
    ):
        raise ProvisionError("policy_rollback")
    if newer.generation > current.generation:
        replace_file(path / "policy.json", encode(bundled))
        policy = bundled
    return Authority(key, root), policy


def create_admin(name: str, output: Path, now: datetime) -> str:
    """Create one offline root, signed policy and public bootstrap bundle."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", name):
        raise ProvisionError("invalid_name")
    authority = Authority.create(now)
    policy = authority.policy(now)
    root_pem = certificate_pem(authority.certificate)
    bootstrap = {
        "v": 0,
        "kind": "bootstrap",
        "name": name,
        "root": root_pem,
        "policy": policy,
    }
    create_directory(
        output,
        {
            "root.key": _key_bytes(authority.key),
            "root.pem": root_pem.encode("ascii"),
            "policy.json": encode(policy),
            "bootstrap.json": encode(bootstrap),
        },
    )
    return authority.swarm_id


def issue_invite(
    admin: Path,
    scopes: dict[str, list[str]],
    seeds: list[str],
    output: Path,
    now: datetime,
) -> str:
    """Write one reusable, scoped bearer invitation as a private file."""
    with locked_directory(admin, exclusive=True):
        return _issue_invite_unlocked(admin, scopes, seeds, output, now)


def _issue_invite_unlocked(
    admin: Path,
    scopes: dict[str, list[str]],
    seeds: list[str],
    output: Path,
    now: datetime,
) -> str:
    """Issue while holding the authority's transaction lock."""
    _permissions(scopes)
    contacts = _seeds(seeds)
    authority, policy = _load_admin(admin, now)
    if (
        verify_policy(policy, authority.certificate, now).expires_at
        <= now.timestamp()
    ):
        raise ProvisionError()
    invitation = authority.invite(scopes, now)
    grant = decode(invitation.grant)
    record = {
        "v": 0,
        "kind": "invite",
        "root": certificate_pem(invitation.root),
        "issuer": certificate_pem(invitation.certificate),
        "issuer_key": _key_bytes(invitation.key).decode("ascii"),
        "grant": grant,
        "policy": policy,
        "seeds": list(contacts),
    }
    create_file(output, encode(record))
    return public_id(invitation.key.public_key())


def _load_invite(
    path: Path, now: datetime, *, allow_expired: bool = False
) -> tuple[Invitation, dict[str, Any], tuple[str, ...], dict[str, Any]]:
    """Validate a bearer invitation before minting or persisting node state."""
    record = decode(read_file(path))
    fields(
        record,
        {
            "v",
            "kind",
            "root",
            "issuer",
            "issuer_key",
            "grant",
            "policy",
            "seeds",
        },
    )
    if (
        type(record["v"]) is not int
        or record["v"] != 0
        or record["kind"] != "invite"
    ):
        raise ProvisionError("invalid_invite")
    root = _certificate(record["root"])
    issuer = _certificate(record["issuer"])
    issuer_time = (
        min(now, issuer.not_valid_after_utc - timedelta(seconds=1))
        if allow_expired
        else now
    )
    verify_issuer(issuer, root, issuer_time)
    key_text = record["issuer_key"]
    if type(key_text) is not str or len(key_text) > 8192:
        raise ProvisionError("invalid_invite")
    key = _load_key(key_text.encode("ascii"))
    issuer_id = public_id(certificate_key(issuer))
    if public_id(key.public_key()) != issuer_id:
        raise ProvisionError("invalid_invite")
    grant = verify_grant(
        record["grant"], issuer, root, now, allow_expired=allow_expired
    )
    policy = record["policy"]
    verify_policy(policy, root, now, allow_expired=True)
    contacts = _seeds(record["seeds"])
    return (
        Invitation(key, issuer, root, encode(record["grant"])),
        policy,
        contacts,
        grant,
    )


def _newer_policy(
    current: dict[str, Any],
    candidate: dict[str, Any],
    root: x509.Certificate,
    now: datetime,
) -> dict[str, Any]:
    """Accept only a current signed generation at or above a durable floor."""
    old = verify_policy(current, root, now, allow_expired=True)
    new = verify_policy(candidate, root, now)
    if new.generation < old.generation or (
        new.generation == old.generation
        and encode(candidate) != encode(current)
    ):
        raise ProvisionError("policy_rollback")
    return candidate


def _bootstrap_policy(
    path: Path, invite: Invitation, floor: dict[str, Any], now: datetime
) -> dict[str, Any]:
    """Require an explicit matching public bundle for first-node formation."""
    record = decode(read_file(path))
    fields(record, {"v", "kind", "name", "root", "policy"})
    if (
        type(record["v"]) is not int
        or record["v"] != 0
        or record["kind"] != "bootstrap"
        or _certificate(record["root"]) != invite.root
    ):
        raise ProvisionError("invalid_bootstrap")
    return _newer_policy(floor, record["policy"], invite.root, now)


def _server_identity(der: bytes, now: datetime) -> None:
    """Check the leaf identity after root-pinned TLS path verification."""
    verify_tls_leaf(x509.load_der_x509_certificate(der), now)


async def _fetch_policy(
    contacts: tuple[str, ...],
    mesh: ipaddress.IPv4Network | ipaddress.IPv6Network,
    root: x509.Certificate,
    floor: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Fetch a bounded public snapshot from any root-authenticated seed."""
    context = ssl.create_default_context(cadata=certificate_pem(root))
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_flags |= ssl.VERIFY_X509_STRICT
    context.check_hostname = False
    for contact in contacts:
        address, port = _parse_seed(contact)
        if address not in mesh:
            continue
        try:
            async with asyncio.timeout(15):
                policy = await _fetch_seed_policy(address, port, context, now)
                _newer_policy(floor, policy, root, now)
                return policy
        except (
            TimeoutError,
            httpx.HTTPError,
            OSError,
            ValueError,
            ProtocolError,
            ProvisionError,
        ):
            continue
    raise ProvisionError("seed_unavailable")


async def _fetch_seed_policy(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    port: int,
    context: ssl.SSLContext,
    now: datetime,
) -> dict[str, Any]:
    """Read one bounded snapshot over a pinned TLS connection."""
    host = f"[{address}]" if address.version == 6 else str(address)
    async with httpx.AsyncClient(
        verify=context,
        trust_env=False,
        follow_redirects=False,
        timeout=httpx.Timeout(10, connect=3),
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
    ) as client:
        async with client.stream(
            "GET",
            f"https://{host}:{port}/v0/policy",
            headers={"Accept-Encoding": "identity"},
        ) as response:
            stream = response.extensions.get("network_stream")
            tls = stream.get_extra_info("ssl_object") if stream else None
            der = tls.getpeercert(binary_form=True) if tls else None
            if not der:
                raise ProvisionError("invalid_seed")
            _server_identity(der, now)
            if (
                response.status_code != 200
                or response.headers.get("Content-Encoding", "identity")
                != "identity"
            ):
                raise ProvisionError("invalid_seed")
            data = bytearray()
            async for chunk in response.aiter_raw():
                data.extend(chunk)
                if len(data) > 65536:
                    raise ProvisionError("invalid_seed")
            return decode(bytes(data))


def _matching_existing_join(
    invite_path: Path, state_dir: Path, mesh_cidr: str, now: datetime
) -> NodeState:
    """Validate a retry without reissuing the persistent node identity."""
    existing = load_node_state(state_dir, now)
    invitation, floor, _, _ = _load_invite(invite_path, now, allow_expired=True)
    stored = verify_policy(
        existing.policy, existing.node.root, now, allow_expired=True
    )
    invited = verify_policy(floor, existing.node.root, now, allow_expired=True)
    if (
        existing.mesh_cidr != mesh_cidr
        or invitation.root != existing.node.root
        or invitation.certificate != existing.node.issuer
        or invitation.grant != existing.node.grant
        or stored.generation < invited.generation
        or (
            stored.generation == invited.generation
            and encode(existing.policy) != encode(floor)
        )
    ):
        raise ProvisionError("already_initialized")
    group, action = sorted(
        _permissions(decode(existing.node.grant)["payload"]["groups"])
    )[0]
    try:
        verify_credential(
            existing.node.credential(),
            existing.node.der,
            existing.node.root,
            existing.policy,
            now,
            group,
            action,
        )
    except ProtocolError:
        raise ProvisionError("authorization_inactive") from None
    return existing


async def join_swarm(
    invite_path: Path,
    state_dir: Path,
    mesh_cidr: str,
    now: datetime,
    *,
    initialize_first: bool = False,
    bootstrap_path: Path | None = None,
) -> NodeState:
    """Mint and persist a new identity after explicit formation or seed contact."""
    mesh = _mesh(mesh_cidr)
    if state_dir.exists() or state_dir.is_symlink():
        return _matching_existing_join(invite_path, state_dir, str(mesh), now)
    invitation, floor, contacts, grant = _load_invite(invite_path, now)
    _mesh_seeds(contacts, mesh)
    if initialize_first:
        if bootstrap_path is None:
            raise ProvisionError("bootstrap_required")
        policy = _bootstrap_policy(bootstrap_path, invitation, floor, now)
    else:
        if bootstrap_path is not None or not contacts:
            raise ProvisionError("seed_required")
        fetched = await _fetch_policy(
            contacts, mesh, invitation.root, floor, now
        )
        policy = _newer_policy(floor, fetched, invitation.root, now)
    node = invitation.join(now)
    permissions = _permissions(grant["groups"])
    group, action = sorted(permissions)[0]
    verify_credential(
        node.credential(), node.der, node.root, policy, now, group, action
    )
    state = _state_record(node, policy, contacts, str(mesh))
    try:
        create_directory(
            state_dir,
            {"node.key": _key_bytes(node.key), "state.json": encode(state)},
        )
    except ProvisionError as error:
        if str(error) != "already_initialized":
            raise
        return _matching_existing_join(invite_path, state_dir, str(mesh), now)
    return NodeState(node, policy, contacts, str(mesh))


def _state_record(
    node: Node,
    policy: dict[str, Any],
    contacts: tuple[str, ...],
    mesh_cidr: str,
) -> dict[str, Any]:
    """Build public node evidence without copying invitation signing material."""
    return {
        "v": 0,
        "kind": "node-state",
        "root": certificate_pem(node.root),
        "credential": node.credential(),
        "policy": policy,
        "seeds": list(contacts),
        "mesh_cidr": mesh_cidr,
    }


def load_node_state(state_dir: Path, now: datetime) -> NodeState:
    """Restore a completed identity under a shared transaction lock."""
    with locked_directory(state_dir, exclusive=False):
        return _load_node_state_unlocked(state_dir, now)


def _load_node_state_unlocked(state_dir: Path, now: datetime) -> NodeState:
    """Restore one completed identity without creating a replacement key."""
    read_directory(state_dir)
    key = _load_key(read_file(state_dir / "node.key", limit=8192))
    state = decode(read_file(state_dir / "state.json"))
    fields(
        state,
        {"v", "kind", "root", "credential", "policy", "seeds", "mesh_cidr"},
    )
    if (
        type(state["v"]) is not int
        or state["v"] != 0
        or state["kind"] != "node-state"
    ):
        raise ProvisionError()
    root = _certificate(state["root"])
    evidence = state["credential"]
    fields(evidence, {"leaf", "issuer", "grant"})
    leaf = _certificate(evidence["leaf"])
    issuer = _certificate(evidence["issuer"])
    issued = max(
        leaf.not_valid_before_utc,
        issuer.not_valid_before_utc,
        root.not_valid_before_utc,
    ) + timedelta(seconds=1)
    verify_chain(leaf, issuer, root, issued)
    node = Node(key, leaf, issuer, root, encode(evidence["grant"]))
    if public_id(key.public_key()) != public_id(certificate_key(leaf)):
        raise ProvisionError()
    grant = verify_grant(
        evidence["grant"], issuer, root, now, allow_expired=True
    )
    if leaf.not_valid_after_utc.timestamp() > grant["expires_at"]:
        raise ProvisionError()
    policy = state["policy"]
    verify_policy(policy, root, now, allow_expired=True)
    contacts = _seeds(state["seeds"])
    if type(state["mesh_cidr"]) is not str:
        raise ProvisionError()
    mesh = _mesh(state["mesh_cidr"])
    _mesh_seeds(contacts, mesh)
    return NodeState(node, policy, contacts, str(mesh))


def refresh_policy(
    admin: Path,
    now: datetime,
    *,
    revoked_nodes: list[str] | None = None,
    revoked_grants: list[str] | None = None,
) -> dict[str, Any]:
    """Sign the next generation, preserving all previous revocations."""
    with locked_directory(admin, exclusive=True):
        return _refresh_policy_unlocked(
            admin, now, revoked_nodes, revoked_grants
        )


def _refresh_policy_unlocked(
    admin: Path,
    now: datetime,
    revoked_nodes: list[str] | None,
    revoked_grants: list[str] | None,
) -> dict[str, Any]:
    """Refresh while holding the authority's transaction lock."""
    authority, current = _load_admin(admin, now)
    snapshot = verify_policy(
        current, authority.certificate, now, allow_expired=True
    )
    old = current["payload"]
    if now.timestamp() + 60 < old["issued_at"]:
        raise ProvisionError("clock_rollback")
    nodes = sorted(set(snapshot.revoked_nodes) | set(revoked_nodes or []))
    grants = sorted(set(snapshot.revoked_grants) | set(revoked_grants or []))
    candidate = authority.policy(
        now,
        generation=snapshot.generation + 1,
        revoked_nodes=nodes,
        revoked_grants=grants,
    )
    verify_policy(candidate, authority.certificate, now)
    bootstrap = decode(read_file(admin / "bootstrap.json"))
    fields(bootstrap, {"v", "kind", "name", "root", "policy"})
    bootstrap["policy"] = candidate
    replace_file(admin / "bootstrap.json", encode(bootstrap))
    replace_file(admin / "policy.json", encode(candidate))
    return candidate


def install_policy(state_dir: Path, policy_file: Path, now: datetime) -> None:
    """Atomically raise one node's durable policy generation."""
    with locked_directory(state_dir, exclusive=True):
        loaded = _load_node_state_unlocked(state_dir, now)
        candidate = decode(read_file(policy_file))
        _newer_policy(loaded.policy, candidate, loaded.node.root, now)
        state = decode(read_file(state_dir / "state.json"))
        state["policy"] = candidate
        replace_file(state_dir / "state.json", encode(state))


def renew_node(state_dir: Path, invite_path: Path, now: datetime) -> NodeState:
    """Issue a fresh leaf and grant while preserving the node's private key."""
    with locked_directory(state_dir, exclusive=True):
        return _renew_node_unlocked(state_dir, invite_path, now)


def _renew_node_unlocked(
    state_dir: Path, invite_path: Path, now: datetime
) -> NodeState:
    """Renew while holding the identity's transaction lock."""
    loaded = _load_node_state_unlocked(state_dir, now)
    invitation, floor, contacts, grant = _load_invite(invite_path, now)
    if not contacts:
        contacts = loaded.seeds
    _mesh_seeds(contacts, _mesh(loaded.mesh_cidr))
    if invitation.root != loaded.node.root:
        raise ProvisionError("wrong_swarm")
    local_snapshot = verify_policy(
        loaded.policy, loaded.node.root, now, allow_expired=True
    )
    invite_snapshot = verify_policy(
        floor, loaded.node.root, now, allow_expired=True
    )
    if invite_snapshot.generation > local_snapshot.generation:
        policy = _newer_policy(loaded.policy, floor, loaded.node.root, now)
    else:
        if invite_snapshot.generation == local_snapshot.generation and encode(
            floor
        ) != encode(loaded.policy):
            raise ProvisionError("policy_rollback")
        verify_policy(loaded.policy, loaded.node.root, now)
        policy = loaded.policy
    node = invitation.join(now, key=loaded.node.key)
    group, action = sorted(_permissions(grant["groups"]))[0]
    verify_credential(
        node.credential(), node.der, node.root, policy, now, group, action
    )
    record = _state_record(node, policy, contacts, loaded.mesh_cidr)
    replace_file(state_dir / "state.json", encode(record))
    return NodeState(node, policy, contacts, loaded.mesh_cidr)
