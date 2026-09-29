"""Validate untrusted records once, then decide with immutable policy data."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from gimle.hugin.swarm.credentials import (
    certificate_key,
    public_id,
    verify_chain,
)
from gimle.hugin.swarm.wire import (
    ProtocolError,
    decode,
    encode,
    fields,
    integer,
    verify,
)


@dataclass(frozen=True)
class Snapshot:
    """Validated authorization state; no mutable untrusted dictionaries."""

    generation: int
    expires_at: int
    revoked_nodes: frozenset[str]
    revoked_grants: frozenset[str]


def _identities(values: Any) -> frozenset[str]:
    if type(values) is not list or len(values) > 512:
        raise ProtocolError()
    if any(
        type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in values
    ):
        raise ProtocolError()
    return frozenset(values)


def _header(payload: dict[str, Any], kind: str, root: x509.Certificate) -> None:
    if (
        type(payload["v"]) is not int
        or payload["v"] != 0
        or payload["kind"] != kind
        or payload["swarm_id"] != public_id(certificate_key(root))
    ):
        raise ProtocolError()


def _lifetime(
    payload: dict[str, Any],
    now: datetime,
    seconds: int,
    *,
    allow_expired: bool = False,
) -> int:
    issued, expires = integer(payload["issued_at"]), integer(
        payload["expires_at"]
    )
    if (
        not issued < expires <= issued + seconds
        or issued > now.timestamp() + 60
        or (not allow_expired and now.timestamp() >= expires)
    ):
        raise ProtocolError()
    return expires


def verify_policy(
    record: Any,
    root: x509.Certificate,
    now: datetime,
    *,
    allow_expired: bool = False,
) -> Snapshot:
    """Validate a signed current policy without requiring client admission."""
    payload = verify(record, certificate_key(root))
    fields(
        payload,
        {
            "v",
            "kind",
            "swarm_id",
            "generation",
            "issued_at",
            "expires_at",
            "revoked_nodes",
            "revoked_grants",
        },
    )
    _header(payload, "policy", root)
    return Snapshot(
        integer(payload["generation"], 1),
        _lifetime(payload, now, 7 * 86400, allow_expired=allow_expired),
        _identities(payload["revoked_nodes"]),
        _identities(payload["revoked_grants"]),
    )


def _permissions(value: Any) -> frozenset[tuple[str, str]]:
    if type(value) is not dict or not 1 <= len(value) <= 32:
        raise ProtocolError()
    result: set[tuple[str, str]] = set()
    for group, actions in value.items():
        if (
            type(group) is not str
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", group)
            or type(actions) is not list
            or not 1 <= len(actions) <= 4
        ):
            raise ProtocolError()
        if any(
            type(a) is not str or a not in {"read", "post", "ask", "reply"}
            for a in actions
        ) or len(set(actions)) != len(actions):
            raise ProtocolError()
        result.update((group, action) for action in actions)
    return frozenset(result)


def verify_grant(
    record: Any,
    issuer: x509.Certificate,
    root: x509.Certificate,
    now: datetime,
    *,
    allow_expired: bool = False,
) -> dict[str, Any]:
    """Validate one root-signed grant bound to its invitation issuer."""
    grant = verify(record, certificate_key(root))
    fields(
        grant,
        {
            "v",
            "kind",
            "swarm_id",
            "grant_id",
            "issuer_id",
            "groups",
            "issued_at",
            "expires_at",
        },
    )
    _header(grant, "grant", root)
    issuer_id = public_id(certificate_key(issuer))
    if grant["grant_id"] != issuer_id or grant["issuer_id"] != issuer_id:
        raise ProtocolError()
    expires = _lifetime(grant, now, 30 * 86400, allow_expired=allow_expired)
    if expires > issuer.not_valid_after_utc.timestamp():
        raise ProtocolError()
    _permissions(grant["groups"])
    return grant


def verify_credential(
    credential: Any,
    tls_der: bytes,
    root: x509.Certificate,
    policy: Any,
    now: datetime,
    group: str,
    action: str,
) -> str:
    """Authorize only a TLS-bound node with a matching issuer grant."""
    try:
        fields(credential, {"leaf", "issuer", "grant"})
        certificates = []
        for name in ("leaf", "issuer"):
            value = credential[name]
            if type(value) is not str or len(value) > 8192:
                raise ProtocolError()
            certificates.append(
                x509.load_pem_x509_certificate(value.encode("ascii"))
            )
        leaf, issuer = certificates
        if leaf.public_bytes(serialization.Encoding.DER) != tls_der:
            raise ProtocolError()
        verify_chain(leaf, issuer, root, now)
        node_id = public_id(certificate_key(leaf))
        issuer_id = public_id(certificate_key(issuer))
        grant = verify_grant(credential["grant"], issuer, root, now)
        if leaf.not_valid_after_utc.timestamp() > grant["expires_at"]:
            raise ProtocolError()
        snapshot = verify_policy(policy, root, now)
        if (
            node_id in snapshot.revoked_nodes
            or issuer_id in snapshot.revoked_grants
        ):
            raise ProtocolError()
        if (group, action) not in _permissions(grant["groups"]):
            raise ProtocolError()
        return node_id
    except (
        ValueError,
        TypeError,
        UnicodeError,
        x509.DuplicateExtension,
        x509.UnsupportedGeneralNameType,
        x509.InvalidVersion,
    ):
        raise ProtocolError() from None


class PolicyState:
    """In-memory policy floor for the isolated transport experiment."""

    def __init__(
        self, root: x509.Certificate, record: dict[str, Any], now: datetime
    ) -> None:
        """Pin the root and initial generation supplied by the test authority."""
        self._root = root
        self._snapshot = verify_policy(record, root, now)
        self._raw = encode(record)

    @property
    def record(self) -> dict[str, Any]:
        """Return a separate public snapshot, never mutable internal state."""
        return decode(self._raw)

    def update(self, record: dict[str, Any], now: datetime) -> None:
        """Accept only a current, monotonic, non-forked root-signed policy."""
        snapshot = verify_policy(record, self._root, now)
        raw = encode(record)
        if snapshot.generation < self._snapshot.generation or (
            snapshot.generation == self._snapshot.generation
            and raw != self._raw
        ):
            raise ProtocolError()
        self._snapshot, self._raw = snapshot, raw
