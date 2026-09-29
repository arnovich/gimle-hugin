"""Temporary node files and TLS contexts for the loopback experiment only."""

import os
import ssl
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from gimle.hugin.swarm.credentials import Node, certificate_pem
from gimle.hugin.swarm.wire import ProtocolError, decode, encode


@dataclass(frozen=True)
class TLSFiles:
    """Keep temporary paths out of automatic diagnostic representations."""

    directory: Path = field(repr=False)


def _write(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def write_node(directory: Path, node: Node, policy: dict[str, Any]) -> TLSFiles:
    """Create owner-only files; callers own temporary-directory cleanup."""
    directory.mkdir(mode=0o700)
    _write(
        directory / "key.pem",
        node.key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    _write(
        directory / "chain.pem",
        (
            certificate_pem(node.certificate) + certificate_pem(node.issuer)
        ).encode("ascii"),
    )
    _write(directory / "root.pem", certificate_pem(node.root).encode("ascii"))
    _write(
        directory / "public.json",
        encode({"credential": node.credential(), "policy": policy}),
    )
    return TLSFiles(directory)


def read_node(files: TLSFiles) -> tuple[Node, dict[str, Any]]:
    """Read only a harness-generated child identity, never ambient credentials."""
    path = files.directory
    private = serialization.load_pem_private_key(
        (path / "key.pem").read_bytes(), None
    )
    if not isinstance(private, Ed25519PrivateKey):
        raise ProtocolError()
    public = decode((path / "public.json").read_bytes())
    evidence = public["credential"]
    node = Node(
        private,
        x509.load_pem_x509_certificate(evidence["leaf"].encode("ascii")),
        x509.load_pem_x509_certificate(evidence["issuer"].encode("ascii")),
        x509.load_pem_x509_certificate((path / "root.pem").read_bytes()),
        encode(evidence["grant"]),
    )
    return node, dict(public["policy"])


def client_context(
    files: TLSFiles, *, authenticate: bool = True
) -> ssl.SSLContext:
    """Pin the generated root and retain hostname checks and TLS 1.3."""
    context = ssl.create_default_context(
        cafile=str(files.directory / "root.pem")
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    if authenticate:
        context.load_cert_chain(
            str(files.directory / "chain.pem"), str(files.directory / "key.pem")
        )
    return context


def server_context(files: TLSFiles) -> ssl.SSLContext:
    """Validate supplied client certificates; protected routes require one."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_verify_locations(cafile=str(files.directory / "root.pem"))
    context.load_cert_chain(
        str(files.directory / "chain.pem"), str(files.directory / "key.pem")
    )
    context.verify_mode = ssl.CERT_OPTIONAL
    return context
