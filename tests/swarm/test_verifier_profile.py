"""Reject certificates outside the one supported private swarm hierarchy."""

from datetime import datetime, timezone

import pytest
from cryptography import x509
from cryptography.x509.oid import ExtensionOID, ObjectIdentifier

from gimle.hugin.swarm.admission import verify_credential
from gimle.hugin.swarm.credentials import (
    Node,
    verify_chain,
    verify_issuer,
    verify_root,
)
from gimle.hugin.swarm.wire import ProtocolError


def _resign(cert, signing_key, replacements, *, omit=(), additions=()):
    """Keep a valid signature while deliberately mutating the certificate."""
    builder = (
        x509.CertificateBuilder()
        .subject_name(cert.subject)
        .issuer_name(cert.issuer)
        .public_key(cert.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(cert.not_valid_before_utc)
        .not_valid_after(cert.not_valid_after_utc)
    )
    for extension in cert.extensions:
        if extension.oid in omit:
            continue
        value, critical = replacements.get(
            extension.oid, (extension.value, extension.critical)
        )
        builder = builder.add_extension(value, critical)
    for value, critical in additions:
        builder = builder.add_extension(value, critical)
    return builder.sign(signing_key, None)


@pytest.mark.parametrize(
    "case",
    [
        "missing_basic",
        "ca_leaf",
        "missing_eku",
        "wrong_san",
        "wrong_key_usage",
        "wrong_criticality",
        "unknown_critical",
        "wrong_authority_key",
    ],
)
def test_malformed_leaf_is_rejected_even_when_signed(swarm_material, case):
    """A holder of a live invite cannot mint a leaf outside the closed profile."""
    m = swarm_material
    original = m.alice.certificate
    replacements = {}
    omit = ()
    additions = ()
    if case == "missing_basic":
        omit = (ExtensionOID.BASIC_CONSTRAINTS,)
    elif case == "ca_leaf":
        replacements[ExtensionOID.BASIC_CONSTRAINTS] = (
            x509.BasicConstraints(ca=True, path_length=0),
            True,
        )
    elif case == "missing_eku":
        omit = (ExtensionOID.EXTENDED_KEY_USAGE,)
    elif case == "wrong_san":
        replacements[ExtensionOID.SUBJECT_ALTERNATIVE_NAME] = (
            x509.SubjectAlternativeName([x509.DNSName("other.swarm.invalid")]),
            False,
        )
    elif case == "wrong_key_usage":
        replacements[ExtensionOID.KEY_USAGE] = (
            x509.KeyUsage(
                False, False, False, False, False, True, False, False, False
            ),
            True,
        )
    elif case == "wrong_criticality":
        old = original.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        replacements[ExtensionOID.SUBJECT_ALTERNATIVE_NAME] = (old.value, True)
    elif case == "unknown_critical":
        additions = (
            (
                x509.UnrecognizedExtension(ObjectIdentifier("1.2.3.4.5"), b"x"),
                True,
            ),
        )
    else:
        replacements[ExtensionOID.AUTHORITY_KEY_IDENTIFIER] = (
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                m.root.key.public_key()
            ),
            False,
        )
    altered = _resign(
        original,
        m.invite.key,
        replacements,
        omit=omit,
        additions=additions,
    )
    node = Node(
        m.alice.key, altered, m.alice.issuer, m.alice.root, m.alice.grant
    )
    with pytest.raises(ProtocolError):
        verify_credential(
            node.credential(),
            node.der,
            m.root.certificate,
            m.policy,
            m.now,
            "research",
            "read",
        )


def test_root_and_issuer_profiles_reject_valid_signatures(swarm_material):
    """Correct keys and signatures do not make a malformed CA acceptable."""
    m = swarm_material
    wrong_root = _resign(
        m.root.certificate,
        m.root.key,
        {
            ExtensionOID.BASIC_CONSTRAINTS: (
                x509.BasicConstraints(ca=True, path_length=0),
                True,
            )
        },
    )
    with pytest.raises(ProtocolError):
        verify_root(wrong_root, m.now)
    wrong_issuer = _resign(
        m.invite.certificate,
        m.root.key,
        {
            ExtensionOID.BASIC_CONSTRAINTS: (
                x509.BasicConstraints(ca=True, path_length=1),
                True,
            )
        },
    )
    with pytest.raises(ProtocolError):
        verify_issuer(wrong_issuer, m.root.certificate, m.now)
    with pytest.raises(ProtocolError):
        verify_chain(
            m.alice.certificate, wrong_issuer, m.root.certificate, m.now
        )


def test_expired_chain_rejected(swarm_material):
    """The fixed verifier uses the caller's current validation time."""
    m = swarm_material
    later = datetime.fromtimestamp(
        m.alice.certificate.not_valid_after_utc.timestamp(), timezone.utc
    )
    with pytest.raises(ProtocolError):
        verify_chain(
            m.alice.certificate, m.alice.issuer, m.root.certificate, later
        )
