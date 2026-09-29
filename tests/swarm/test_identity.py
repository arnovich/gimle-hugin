"""Exercise cryptographic and permission boundaries using fresh keys."""

from datetime import timedelta

import pytest

from gimle.hugin.swarm.admission import verify_credential
from gimle.hugin.swarm.credentials import Authority
from gimle.hugin.swarm.wire import ProtocolError


def test_distinct_node_keys_and_verified_scope(swarm_material):
    """Shared admission authority never becomes shared node identity."""
    m = swarm_material
    assert m.alice.node_id != m.bob.node_id
    assert (
        verify_credential(
            m.alice.credential(),
            m.alice.der,
            m.root.certificate,
            m.policy,
            m.now,
            "research",
            "post",
        )
        == m.alice.node_id
    )


def test_grant_cannot_be_swapped_between_invitation_issuers(swarm_material):
    """A valid public broad grant cannot upgrade a narrow invitation."""
    m = swarm_material
    narrow = m.root.invite({"research": ["read"]}, m.now).join(m.now)
    forged = narrow.credential()
    forged["grant"] = m.alice.credential()["grant"]
    with pytest.raises(ProtocolError):
        verify_credential(
            forged,
            narrow.der,
            m.root.certificate,
            m.policy,
            m.now,
            "research",
            "post",
        )


def test_tls_leaf_binding_rejects_stolen_public_credential(swarm_material):
    """Valid public node evidence must belong to the TLS connection."""
    m = swarm_material
    with pytest.raises(ProtocolError):
        verify_credential(
            m.alice.credential(),
            m.bob.der,
            m.root.certificate,
            m.policy,
            m.now,
            "research",
            "read",
        )


@pytest.mark.parametrize(
    "case", ["foreign", "permission", "expired", "revoked"]
)
def test_admission_fails_closed(swarm_material, case):
    """Independent invalid authorization paths fail before accepting work."""
    m = swarm_material
    node, now, policy, action = m.alice, m.now, m.policy, "read"
    if case == "foreign":
        node = (
            Authority.create(now).invite({"research": ["read"]}, now).join(now)
        )
    elif case == "permission":
        action = "reply"
    elif case == "expired":
        now += timedelta(days=31)
    else:
        policy = m.root.policy(now, revoked_nodes=[node.node_id])
    with pytest.raises(ProtocolError):
        verify_credential(
            node.credential(),
            node.der,
            m.root.certificate,
            policy,
            now,
            "research",
            action,
        )


def test_credentials_have_no_secret_repr(swarm_material):
    """Accidental debug representations cannot include private key material."""
    m = swarm_material
    for value in (m.root, m.invite, m.alice):
        assert "PRIVATE" not in repr(value)
        assert "key=" not in repr(value)


def test_membership_cannot_outlive_invite(swarm_material):
    """Offline enrollment does not turn a short grant into permanent access."""
    m = swarm_material
    later = m.now + timedelta(days=29)
    node = m.invite.join(later)
    assert (
        node.certificate.not_valid_after_utc
        <= m.invite.certificate.not_valid_after_utc
    )
    with pytest.raises(ProtocolError):
        m.invite.join(m.now + timedelta(days=31))


def test_grant_revocation_and_policy_forks_are_rejected(swarm_material):
    """A leaked invitation revokes its cohort; policy generations cannot fork."""
    from gimle.hugin.swarm.admission import PolicyState

    m = swarm_material
    revoked = m.root.policy(
        m.now,
        generation=2,
        revoked_grants=[m.alice.credential()["grant"]["payload"]["grant_id"]],
    )
    for node in (m.alice, m.bob):
        with pytest.raises(ProtocolError):
            verify_credential(
                node.credential(),
                node.der,
                m.root.certificate,
                revoked,
                m.now,
                "research",
                "read",
            )
    state = PolicyState(m.root.certificate, m.policy, m.now)
    state.update(revoked, m.now)
    state.update(revoked, m.now)
    with pytest.raises(ProtocolError):
        state.update(m.policy, m.now)
    with pytest.raises(ProtocolError):
        state.update(m.root.policy(m.now, generation=2), m.now)
