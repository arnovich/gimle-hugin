"""Bounded, loopback-only probes; no board operations or production listener."""

import asyncio
import re
import secrets
import ssl
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import TracebackType

import httpx
from aiohttp import web
from cryptography import x509

from gimle.hugin.swarm._http_errors import RedactedServer
from gimle.hugin.swarm.admission import PolicyState, verify_credential
from gimle.hugin.swarm.credentials import (
    Node,
    certificate_key,
    node_hostname,
    public_id,
)
from gimle.hugin.swarm.material import TLSFiles, server_context
from gimle.hugin.swarm.wire import (
    MAX_RECORD_BYTES,
    ProtocolError,
    decode,
    encode,
    fields,
    sign,
    verify,
)


def probe_record(
    node: Node, *, group: str = "research", action: str = "read"
) -> bytes:
    """Sign a side-effect-free diagnostic request, never an execution command."""
    payload = {
        "v": 0,
        "kind": "probe",
        "swarm_id": public_id(certificate_key(node.root)),
        "node_id": node.node_id,
        "group": group,
        "action": action,
        "nonce": secrets.token_hex(16),
    }
    return encode(
        {"credential": node.credential(), "message": sign(payload, node.key)}
    )


def _response(status: int, code: str = "rejected") -> web.Response:
    return web.Response(
        status=status,
        body=encode({"error": code}),
        content_type="application/json",
    )


class ProbeServer:
    """Serve an experiment identity on loopback, with no configurable bind IP."""

    def __init__(
        self,
        node: Node,
        policy: PolicyState,
        files: TLSFiles,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Allow deterministic policy-time tests without replacing real TLS."""
        self._node, self._policy, self._files = node, policy, files
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._active = 0
        self._runner: web.ServerRunner | None = None

    async def _handle(self, request: web.BaseRequest) -> web.StreamResponse:
        if self._active >= 8:
            return _response(503, "busy")
        self._active += 1
        try:
            async with asyncio.timeout(10):
                if request.method == "GET" and request.path == "/v0/policy":
                    return web.Response(
                        body=encode(self._policy.record),
                        content_type="application/json",
                    )
                if request.method == "POST" and request.path == "/v0/probe":
                    return await self._probe(request)
                return _response(404)
        except TimeoutError:
            return _response(408, "timeout")
        finally:
            self._active -= 1

    async def _probe(self, request: web.BaseRequest) -> web.Response:
        transport = request.transport
        tls = transport.get_extra_info("ssl_object") if transport else None
        peer_der = tls.getpeercert(binary_form=True) if tls else None
        if not peer_der:
            return _response(403)
        if request.headers.get("Content-Encoding", "identity") != "identity":
            return _response(400)
        if (
            request.content_length is not None
            and request.content_length > MAX_RECORD_BYTES
        ):
            return _response(413)
        data = bytearray()
        async for chunk in request.content.iter_chunked(8192):
            data.extend(chunk)
            if len(data) > MAX_RECORD_BYTES:
                return _response(413)
        try:
            record = decode(bytes(data))
            fields(record, {"credential", "message"})
        except ProtocolError:
            return _response(400)
        try:
            payload = verify(
                record["message"],
                certificate_key(x509.load_der_x509_certificate(peer_der)),
            )
            fields(
                payload,
                {
                    "v",
                    "kind",
                    "swarm_id",
                    "node_id",
                    "group",
                    "action",
                    "nonce",
                },
            )
            if (
                type(payload["v"]) is not int
                or payload["v"] != 0
                or payload["kind"] != "probe"
                or payload["swarm_id"]
                != public_id(certificate_key(self._node.root))
            ):
                raise ProtocolError()
            if type(payload["nonce"]) is not str or not re.fullmatch(
                r"[0-9a-f]{32}", payload["nonce"]
            ):
                raise ProtocolError()
            group, action = payload["group"], payload["action"]
            if type(group) is not str or type(action) is not str:
                raise ProtocolError()
            now = self._clock()
            node_id = verify_credential(
                record["credential"],
                peer_der,
                self._node.root,
                self._policy.record,
                now,
                group,
                action,
            )
            if payload["node_id"] != node_id:
                raise ProtocolError()
            verify_credential(
                self._node.credential(),
                self._node.der,
                self._node.root,
                self._policy.record,
                now,
                group,
                "read",
            )
        except (ProtocolError, ValueError, TypeError):
            return _response(403)
        return web.Response(
            body=encode(
                {
                    "accepted": True,
                    "nonce": payload["nonce"],
                    "credential": self._node.credential(),
                }
            ),
            content_type="application/json",
        )

    async def __aenter__(self) -> int:
        """Return the ephemeral port after starting an isolated HTTPS listener."""
        self._runner = web.ServerRunner(
            RedactedServer(self._handle), shutdown_timeout=1
        )
        await self._runner.setup()
        try:
            site = web.TCPSite(
                self._runner,
                "127.0.0.1",
                0,
                ssl_context=server_context(self._files),
            )
            await site.start()
            return int(self._runner.addresses[0][1])
        except BaseException:
            await self._runner.cleanup()
            raise

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Finish outstanding handlers and close all sockets."""
        if self._runner is not None:
            await self._runner.cleanup()


@dataclass(frozen=True)
class ProbeResponse:
    """Keep certificates and response bytes out of automatic error reprs."""

    status: int
    body: bytes = field(repr=False)
    peer_der: bytes = field(repr=False)


async def exchange(
    port: int,
    expected_node: str,
    context: ssl.SSLContext,
    method: str,
    path: str,
    body: bytes = b"",
) -> ProbeResponse:
    """Inspect the real TLS peer while streaming a bounded loopback response."""
    hostname = node_hostname(expected_node)
    if path not in {"/v0/policy", "/v0/probe"}:
        raise ProtocolError()
    async with asyncio.timeout(10):
        async with httpx.AsyncClient(
            verify=context,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(10, connect=3),
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
        ) as client:
            async with client.stream(
                method,
                f"https://127.0.0.1:{port}{path}",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                },
                extensions={"sni_hostname": hostname},
            ) as response:
                stream = response.extensions.get("network_stream")
                tls = stream.get_extra_info("ssl_object") if stream else None
                peer_der = tls.getpeercert(binary_form=True) if tls else None
                if (
                    not peer_der
                    or public_id(
                        certificate_key(
                            x509.load_der_x509_certificate(peer_der)
                        )
                    )
                    != expected_node
                ):
                    raise ProtocolError()
                if (
                    response.headers.get("Content-Encoding", "identity")
                    != "identity"
                ):
                    raise ProtocolError()
                data = bytearray()
                async for chunk in response.aiter_raw():
                    data.extend(chunk)
                    if len(data) > MAX_RECORD_BYTES:
                        raise ProtocolError()
                return ProbeResponse(
                    response.status_code, bytes(data), peer_der
                )
