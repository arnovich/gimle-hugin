"""Generate ephemeral experiment certificates and isolate path validation."""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.x509.oid import (
    ExtendedKeyUsageOID,
    ExtensionOID,
    NameOID,
    SignatureAlgorithmOID,
)

from gimle.hugin.swarm.wire import ProtocolError, decode, encode, sign


def certificate_key(cert: x509.Certificate) -> Ed25519PublicKey:
    """Require Ed25519 before using an untrusted certificate's key."""
    key = cert.public_key()
    if not isinstance(key, Ed25519PublicKey):
        raise ProtocolError()
    return key


def public_id(key: Ed25519PublicKey) -> str:
    """Hash DER SubjectPublicKeyInfo, consistently for roots and node IDs."""
    raw = key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(raw).hexdigest()


def node_hostname(node_id: str) -> str:
    """Encode the full identity in legal DNS labels without DNS resolution."""
    if not re.fullmatch(r"[0-9a-f]{64}", node_id):
        raise ProtocolError()
    return node_id[:32] + "." + node_id[32:] + ".swarm.invalid"


def certificate_pem(cert: x509.Certificate) -> str:
    """Export public certificate evidence, never a private key."""
    return cert.public_bytes(serialization.Encoding.PEM).decode("ascii")


_BASE_EXTENSIONS = {
    ExtensionOID.BASIC_CONSTRAINTS,
    ExtensionOID.KEY_USAGE,
    ExtensionOID.SUBJECT_KEY_IDENTIFIER,
    ExtensionOID.AUTHORITY_KEY_IDENTIFIER,
}


def _profile(
    cert: x509.Certificate,
    parent: x509.Certificate,
    now: datetime,
    depth: int | None,
) -> None:
    """Check every field of the one supported private-certificate profile."""
    key = certificate_key(cert)
    parent_key = certificate_key(parent)
    identity = public_id(key)
    if (
        cert.signature_algorithm_oid != SignatureAlgorithmOID.ED25519
        or cert.subject
        != x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, identity)])
        or not cert.not_valid_before_utc <= now < cert.not_valid_after_utc
        or cert.not_valid_after_utc > parent.not_valid_after_utc
    ):
        raise ProtocolError()
    cert.verify_directly_issued_by(parent)
    allowed = set(_BASE_EXTENSIONS)
    if depth is None:
        allowed.update(
            {
                ExtensionOID.SUBJECT_ALTERNATIVE_NAME,
                ExtensionOID.EXTENDED_KEY_USAGE,
            }
        )
    if {extension.oid for extension in cert.extensions} != allowed:
        raise ProtocolError()
    expected_critical = {
        ExtensionOID.BASIC_CONSTRAINTS,
        ExtensionOID.KEY_USAGE,
    }
    for extension in cert.extensions:
        if extension.critical != (extension.oid in expected_critical):
            raise ProtocolError()
    if cert.extensions.get_extension_for_class(
        x509.BasicConstraints
    ).value != x509.BasicConstraints(ca=depth is not None, path_length=depth):
        raise ProtocolError()
    ca = depth is not None
    expected_usage = x509.KeyUsage(
        True, False, False, False, False, ca, ca, False, False
    )
    if (
        cert.extensions.get_extension_for_class(x509.KeyUsage).value
        != expected_usage
    ):
        raise ProtocolError()
    if cert.extensions.get_extension_for_class(
        x509.SubjectKeyIdentifier
    ).value != x509.SubjectKeyIdentifier.from_public_key(key):
        raise ProtocolError()
    if cert.extensions.get_extension_for_class(
        x509.AuthorityKeyIdentifier
    ).value != x509.AuthorityKeyIdentifier.from_issuer_public_key(parent_key):
        raise ProtocolError()
    if depth is None:
        san = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
        if san != x509.SubjectAlternativeName(
            [x509.DNSName(node_hostname(identity))]
        ):
            raise ProtocolError()
        eku = cert.extensions.get_extension_for_class(
            x509.ExtendedKeyUsage
        ).value
        if eku != x509.ExtendedKeyUsage(
            [ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.SERVER_AUTH]
        ):
            raise ProtocolError()


def verify_root(root: x509.Certificate, now: datetime) -> None:
    """Validate the exact self-signed root profile before pinning it."""
    try:
        _profile(root, root, now, 1)
    except (
        ValueError,
        TypeError,
        InvalidSignature,
        UnsupportedAlgorithm,
        x509.ExtensionNotFound,
        x509.DuplicateExtension,
        x509.UnsupportedGeneralNameType,
        x509.InvalidVersion,
    ):
        raise ProtocolError() from None


def verify_issuer(
    issuer: x509.Certificate, root: x509.Certificate, now: datetime
) -> None:
    """Validate the sole invitation intermediate beneath the pinned root."""
    try:
        verify_root(root, now)
        _profile(issuer, root, now, 0)
    except (
        ValueError,
        TypeError,
        InvalidSignature,
        UnsupportedAlgorithm,
        x509.ExtensionNotFound,
        x509.DuplicateExtension,
        x509.UnsupportedGeneralNameType,
        x509.InvalidVersion,
    ):
        raise ProtocolError() from None


def verify_chain(
    leaf: x509.Certificate,
    issuer: x509.Certificate,
    root: x509.Certificate,
    now: datetime,
) -> None:
    """Check the exact three-certificate hierarchy verified again by TLS."""
    try:
        verify_issuer(issuer, root, now)
        _profile(leaf, issuer, now, None)
    except (
        ValueError,
        TypeError,
        InvalidSignature,
        UnsupportedAlgorithm,
        x509.ExtensionNotFound,
        x509.DuplicateExtension,
        x509.UnsupportedGeneralNameType,
        x509.InvalidVersion,
    ):
        raise ProtocolError() from None


def verify_tls_leaf(leaf: x509.Certificate, now: datetime) -> str:
    """Check seed identity after the TLS stack validated its pinned-root path."""
    try:
        node_id = public_id(certificate_key(leaf))
        allowed = _BASE_EXTENSIONS | {
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME,
            ExtensionOID.EXTENDED_KEY_USAGE,
        }
        if (
            leaf.signature_algorithm_oid != SignatureAlgorithmOID.ED25519
            or leaf.subject
            != x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, node_id)])
            or not leaf.not_valid_before_utc <= now < leaf.not_valid_after_utc
            or {extension.oid for extension in leaf.extensions} != allowed
        ):
            raise ProtocolError()
        for extension in leaf.extensions:
            if extension.critical != (
                extension.oid
                in {ExtensionOID.BASIC_CONSTRAINTS, ExtensionOID.KEY_USAGE}
            ):
                raise ProtocolError()
        if (
            leaf.extensions.get_extension_for_class(x509.BasicConstraints).value
            != x509.BasicConstraints(ca=False, path_length=None)
            or leaf.extensions.get_extension_for_class(x509.KeyUsage).value
            != x509.KeyUsage(
                True, False, False, False, False, False, False, False, False
            )
            or leaf.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            ).value
            != x509.SubjectAlternativeName(
                [x509.DNSName(node_hostname(node_id))]
            )
            or leaf.extensions.get_extension_for_class(
                x509.ExtendedKeyUsage
            ).value
            != x509.ExtendedKeyUsage(
                [
                    ExtendedKeyUsageOID.CLIENT_AUTH,
                    ExtendedKeyUsageOID.SERVER_AUTH,
                ]
            )
            or leaf.extensions.get_extension_for_class(
                x509.SubjectKeyIdentifier
            ).value
            != x509.SubjectKeyIdentifier.from_public_key(certificate_key(leaf))
        ):
            raise ProtocolError()
        return node_id
    except (
        ValueError,
        TypeError,
        UnsupportedAlgorithm,
        x509.ExtensionNotFound,
        x509.DuplicateExtension,
        x509.UnsupportedGeneralNameType,
        x509.InvalidVersion,
    ):
        raise ProtocolError() from None


def _issue(
    key: Ed25519PrivateKey,
    signer: Ed25519PrivateKey,
    issuer: x509.Certificate | None,
    now: datetime,
    end: datetime,
    depth: int | None,
) -> x509.Certificate:
    node_id = public_id(key.public_key())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, node_id)])
    ca = depth is not None
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(issuer.subject if issuer else name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(seconds=60))
        .not_valid_after(end)
        .add_extension(x509.BasicConstraints(ca=ca, path_length=depth), True)
        .add_extension(
            x509.KeyUsage(
                True, False, False, False, False, ca, ca, False, False
            ),
            True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                signer.public_key()
            ),
            False,
        )
    )
    if not ca:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(node_hostname(node_id))]),
            False,
        ).add_extension(
            x509.ExtendedKeyUsage(
                [
                    ExtendedKeyUsageOID.CLIENT_AUTH,
                    ExtendedKeyUsageOID.SERVER_AUTH,
                ]
            ),
            False,
        )
    return builder.sign(signer, None)


@dataclass(frozen=True)
class Authority:
    """Fresh offline test authority; never serialized by the harness."""

    key: Ed25519PrivateKey = field(repr=False)
    certificate: x509.Certificate = field(repr=False)

    @classmethod
    def create(cls, now: datetime) -> "Authority":
        """Generate unrelated test roots for each test run."""
        key = Ed25519PrivateKey.generate()
        return cls(
            key, _issue(key, key, None, now, now + timedelta(days=365), 1)
        )

    @property
    def swarm_id(self) -> str:
        """Return the pinned root identity."""
        return public_id(self.key.public_key())

    def invite(
        self, groups: dict[str, list[str]], now: datetime
    ) -> "Invitation":
        """Create test invitation material, not a persisted enrollment API."""
        key = Ed25519PrivateKey.generate()
        expires = min(
            now + timedelta(days=30), self.certificate.not_valid_after_utc
        )
        cert = _issue(key, self.key, self.certificate, now, expires, 0)
        identity = public_id(key.public_key())
        grant = sign(
            {
                "v": 0,
                "kind": "grant",
                "swarm_id": self.swarm_id,
                "grant_id": identity,
                "issuer_id": identity,
                "groups": groups,
                "issued_at": int(now.timestamp()),
                "expires_at": int(expires.timestamp()),
            },
            self.key,
        )
        return Invitation(key, cert, self.certificate, encode(grant))

    def policy(
        self,
        now: datetime,
        *,
        generation: int = 1,
        revoked_nodes: list[str] | None = None,
        revoked_grants: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a signed public policy for positive and negative tests."""
        return sign(
            {
                "v": 0,
                "kind": "policy",
                "swarm_id": self.swarm_id,
                "generation": generation,
                "issued_at": int(now.timestamp()),
                "expires_at": int((now + timedelta(days=7)).timestamp()),
                "revoked_nodes": revoked_nodes or [],
                "revoked_grants": revoked_grants or [],
            },
            self.key,
        )


@dataclass(frozen=True)
class Invitation:
    """Ephemeral bearer signing authority with no logging/serialization API."""

    key: Ed25519PrivateKey = field(repr=False)
    certificate: x509.Certificate = field(repr=False)
    root: x509.Certificate = field(repr=False)
    grant: bytes = field(repr=False)

    def join(
        self, now: datetime, *, key: Ed25519PrivateKey | None = None
    ) -> "Node":
        """Issue a leaf for a new identity or renew an existing node key."""
        if (
            not self.certificate.not_valid_before_utc
            <= now
            < self.certificate.not_valid_after_utc
        ):
            raise ProtocolError()
        key = key or Ed25519PrivateKey.generate()
        return Node(
            key,
            _issue(
                key,
                self.key,
                self.certificate,
                now,
                self.certificate.not_valid_after_utc,
                None,
            ),
            self.certificate,
            self.root,
            self.grant,
        )


@dataclass(frozen=True)
class Node:
    """Independent node key and immutable public evidence for the experiment."""

    key: Ed25519PrivateKey = field(repr=False)
    certificate: x509.Certificate = field(repr=False)
    issuer: x509.Certificate = field(repr=False)
    root: x509.Certificate = field(repr=False)
    grant: bytes = field(repr=False)

    @property
    def node_id(self) -> str:
        """Return the public node identity."""
        return public_id(self.key.public_key())

    @property
    def der(self) -> bytes:
        """Return public certificate bytes for TLS channel binding."""
        return self.certificate.public_bytes(serialization.Encoding.DER)

    def credential(self) -> dict[str, Any]:
        """Return a fresh public evidence object without private material."""
        return {
            "leaf": certificate_pem(self.certificate),
            "issuer": certificate_pem(self.issuer),
            "grant": decode(self.grant),
        }
