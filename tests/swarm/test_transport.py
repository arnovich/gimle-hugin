"""Real TLS tests: the policy exception must never open the protected route."""

import asyncio
from datetime import timedelta

import httpx
import pytest

from gimle.hugin.swarm.admission import PolicyState
from gimle.hugin.swarm.material import client_context, write_node
from gimle.hugin.swarm.transport import (
    ProbeServer,
    exchange,
    probe_record,
)
from gimle.hugin.swarm.wire import ProtocolError, decode


def test_real_tls_probe_and_public_policy_are_separate(
    swarm_material, probe_files
):
    """A certificate-free connection can fetch policy but cannot send work."""
    m = swarm_material

    async def scenario():
        server_files = write_node(probe_files / "server", m.bob, m.policy)
        client_files = write_node(probe_files / "client", m.alice, m.policy)
        state = PolicyState(m.root.certificate, m.policy, m.now)
        async with ProbeServer(m.bob, state, server_files) as port:
            result = await exchange(
                port,
                m.bob.node_id,
                client_context(client_files),
                "POST",
                "/v0/probe",
                probe_record(m.alice),
            )
            assert result.status == 200
            assert decode(result.body)["accepted"] is True
            public = client_context(client_files, authenticate=False)
            policy = await exchange(
                port, m.bob.node_id, public, "GET", "/v0/policy"
            )
            assert policy.status == 200
            assert decode(policy.body) == m.policy
            denied = await exchange(
                port,
                m.bob.node_id,
                public,
                "POST",
                "/v0/probe",
                probe_record(m.alice),
            )
            assert denied.status == 403
            assert denied.body == b'{"error":"rejected"}'

    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["node", "grant", "expired"])
def test_live_connection_rechecks_revocation(
    swarm_material, probe_files, change
):
    """The same established TLS connection must reauthorize every operation."""
    from gimle.hugin.swarm.credentials import node_hostname

    m = swarm_material
    clock = [m.now]

    async def scenario():
        files = write_node(probe_files / "server", m.bob, m.policy)
        client_files = write_node(probe_files / "client", m.alice, m.policy)
        state = PolicyState(m.root.certificate, m.policy, m.now)
        async with ProbeServer(
            m.bob, state, files, clock=lambda: clock[0]
        ) as port:
            async with httpx.AsyncClient(
                verify=client_context(client_files), trust_env=False
            ) as client:
                args = dict(
                    content=probe_record(m.alice),
                    extensions={"sni_hostname": node_hostname(m.bob.node_id)},
                )
                first = await client.post(
                    f"https://127.0.0.1:{port}/v0/probe", **args
                )
                assert first.status_code == 200
                stream = first.extensions["network_stream"]
                if change == "expired":
                    clock[0] += timedelta(days=8)
                else:
                    kwargs = (
                        {"revoked_nodes": [m.alice.node_id]}
                        if change == "node"
                        else {
                            "revoked_grants": [
                                m.alice.credential()["grant"]["payload"][
                                    "grant_id"
                                ]
                            ]
                        }
                    )
                    state.update(
                        m.root.policy(m.now, generation=2, **kwargs), m.now
                    )
                second = await client.post(
                    f"https://127.0.0.1:{port}/v0/probe", **args
                )
                assert second.extensions["network_stream"] is stream
                assert second.status_code == 403

    asyncio.run(scenario())


def test_tls_identity_check_is_not_disabled(swarm_material, probe_files):
    """An expected node ID mismatch fails the TLS hostname check."""
    m = swarm_material

    async def scenario():
        files = write_node(probe_files / "server", m.bob, m.policy)
        client = write_node(probe_files / "client", m.alice, m.policy)
        async with ProbeServer(
            m.bob, PolicyState(m.root.certificate, m.policy, m.now), files
        ) as port:
            with pytest.raises(httpx.ConnectError):
                await exchange(
                    port,
                    m.alice.node_id,
                    client_context(client),
                    "GET",
                    "/v0/policy",
                )

    asyncio.run(scenario())


def test_stale_policy_can_refresh_without_opening_probe(
    swarm_material, probe_files
):
    """Day-eight clients recover via public policy while data stays denied."""
    m = swarm_material
    old_time = m.now - timedelta(days=8)
    stale_policy = m.root.policy(old_time)
    stale = PolicyState(m.root.certificate, stale_policy, old_time)
    fresh = m.root.policy(m.now, generation=2)

    async def scenario():
        files = write_node(probe_files / "server", m.bob, fresh)
        client = write_node(probe_files / "client", m.alice, stale_policy)
        async with ProbeServer(
            m.bob, PolicyState(m.root.certificate, fresh, m.now), files
        ) as port:
            result = await exchange(
                port,
                m.bob.node_id,
                client_context(client, authenticate=False),
                "GET",
                "/v0/policy",
            )
            stale.update(decode(result.body), m.now)
            assert stale.record == fresh
            with pytest.raises(ProtocolError):
                stale.update(stale_policy, old_time)

    asyncio.run(scenario())


def test_invalid_payload_never_reflected(swarm_material, probe_files):
    """Reject oversized/ambiguous payloads without putting them in errors."""
    m = swarm_material

    async def scenario():
        files = write_node(probe_files / "server", m.bob, m.policy)
        client = write_node(probe_files / "client", m.alice, m.policy)
        async with ProbeServer(
            m.bob, PolicyState(m.root.certificate, m.policy, m.now), files
        ) as port:
            for body in (b'{"v":0,"v":1}', b"x" * 65537):
                result = await exchange(
                    port,
                    m.bob.node_id,
                    client_context(client),
                    "POST",
                    "/v0/probe",
                    body,
                )
                assert result.status in (400, 413)
                assert b"x" * 20 not in result.body

    asyncio.run(scenario())


@pytest.mark.parametrize("invalid", ["foreign", "expired"])
def test_server_rejects_invalid_client_chain(
    swarm_material, probe_files, invalid
):
    """Trusting the server cannot make an invalid client certificate valid."""
    from gimle.hugin.swarm.credentials import Authority, certificate_pem

    m = swarm_material
    if invalid == "foreign":
        other = Authority.create(m.now)
        node = other.invite({"research": ["read"]}, m.now).join(m.now)
    else:
        then = m.now - timedelta(days=31)
        node = m.root.invite({"research": ["read"]}, then).join(then)

    async def scenario():
        files = write_node(probe_files / "server", m.bob, m.policy)
        client = write_node(probe_files / "client", node, m.policy)
        context = client_context(client)
        context.load_verify_locations(
            cadata=certificate_pem(m.root.certificate)
        )
        async with ProbeServer(
            m.bob, PolicyState(m.root.certificate, m.policy, m.now), files
        ) as port:
            with pytest.raises(httpx.TransportError):
                await exchange(
                    port,
                    m.bob.node_id,
                    context,
                    "POST",
                    "/v0/probe",
                    probe_record(node),
                )

    asyncio.run(scenario())


def test_expired_server_policy_denies_probe_but_can_be_replaced(
    swarm_material, probe_files
):
    """A live TLS session still needs current policy for every operation."""
    m = swarm_material
    then = m.now - timedelta(days=8)
    old = m.root.policy(then)
    state = PolicyState(m.root.certificate, old, then)

    async def scenario():
        files = write_node(probe_files / "server", m.bob, old)
        client = write_node(probe_files / "client", m.alice, m.policy)
        async with ProbeServer(m.bob, state, files) as port:
            denied = await exchange(
                port,
                m.bob.node_id,
                client_context(client),
                "POST",
                "/v0/probe",
                probe_record(m.alice),
            )
            assert denied.status == 403
            state.update(m.root.policy(m.now, generation=2), m.now)
            accepted = await exchange(
                port,
                m.bob.node_id,
                client_context(client),
                "POST",
                "/v0/probe",
                probe_record(m.alice),
            )
            assert accepted.status == 200

    asyncio.run(scenario())


def test_malformed_http_headers_are_not_logged_or_reflected(
    swarm_material, probe_files, caplog
):
    """Protocol errors before middleware must not expose request material."""
    from gimle.hugin.swarm.credentials import node_hostname

    m = swarm_material
    canary = b"harmless-publication-canary"

    async def scenario():
        files = write_node(probe_files / "server", m.bob, m.policy)
        client = write_node(probe_files / "client", m.alice, m.policy)
        async with ProbeServer(
            m.bob, PolicyState(m.root.certificate, m.policy, m.now), files
        ) as port:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1",
                port,
                ssl=client_context(client),
                server_hostname=node_hostname(m.bob.node_id),
            )
            try:
                writer.write(
                    b"GET /v0/policy HTTP/1.1\r\nHost: localhost\r\nX-Canary: "
                    + canary
                    + b"\x00\r\n\r\n"
                )
                await writer.drain()
                response = await asyncio.wait_for(reader.read(65536), timeout=5)
                assert b"400" in response
                assert canary not in response
            finally:
                writer.close()
                await writer.wait_closed()

    asyncio.run(scenario())
    assert canary.decode() not in caplog.text
