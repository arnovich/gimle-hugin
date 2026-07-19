"""A tiny forward proxy that filters a docker sandbox's egress by allowlist.

This is the security core of the docker egress filter (task 033). The sandbox
container has no direct route out (an ``internal`` docker network); its only exit
is this proxy, running in a dual-homed sidecar. So whatever this proxy refuses is
simply unreachable.

Two controls, both mandatory:

- **Host allowlist** — a request is permitted only if its host equals, or is a
  subdomain of, an operator-configured entry. An empty allowlist denies
  everything.
- **Private-IP / DNS-rebinding deny** — the host is resolved *here*, and the
  connection is made to a resolved address only if it is **globally routable**
  (never link-local/metadata ``169.254.169.254``, RFC1918, loopback, CGNAT,
  multicast, reserved). Crucially we connect to the *exact IP we checked*, not by
  re-resolving the hostname — so an allowlisted domain whose DNS points at the
  metadata endpoint cannot slip through (the allowlist alone is not enough).

Scope: HTTP (plain, port 80) and HTTPS (``CONNECT`` to 443). A tool that ignores
``HTTP_PROXY`` has no route and simply fails — fail-closed. Stdlib only, so the
sidecar image is ``python:slim`` + this one file.
"""

import ipaddress
import logging
import os
import select
import socket
import threading
from socketserver import StreamRequestHandler, ThreadingTCPServer
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_CONNECT_PORTS = {443}  # CONNECT is for TLS only
_BUFSIZE = 65536


def parse_allowlist(raw: Optional[str]) -> List[str]:
    """Parse a comma/space-separated allowlist into normalized host entries."""
    if not raw:
        return []
    parts = raw.replace(",", " ").split()
    return [p.strip().lower().rstrip(".") for p in parts if p.strip()]


def host_allowed(host: str, allowlist: List[str]) -> bool:
    """Whether ``host`` equals or is a subdomain of an allowlist entry.

    An empty allowlist denies everything (deny-all default).
    """
    host = host.lower().rstrip(".")
    return any(
        host == entry or host.endswith("." + entry) for entry in allowlist
    )


def safe_global_addresses(host: str, port: int) -> List[Tuple[int, str]]:
    """Resolve ``host`` and return only globally-routable ``(family, ip)`` addrs.

    Filters out link-local (incl. the metadata endpoint), private (RFC1918),
    loopback, CGNAT, multicast, and reserved addresses — so a hostname that
    resolves to any of those yields no address to connect to (deny).
    """
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return []
    safe: List[Tuple[int, str]] = []
    for family, _type, _proto, _canon, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if ip.is_global and not ip.is_multicast:
            safe.append((int(family), str(ip)))
    return safe


def _connect_checked(
    host: str, port: int, allowlist: List[str]
) -> Optional[socket.socket]:
    """Open a socket to a *checked* global address for ``host:port``, or None.

    Returns the connected socket, or None if the host is not allowlisted or
    resolves only to non-global addresses. Connects to the exact IP checked (no
    re-resolution — DNS-rebinding-safe).
    """
    if not host_allowed(host, allowlist):
        logger.info("deny (not allowlisted): %s", host)
        return None
    for family, ip in safe_global_addresses(host, port):
        try:
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.settimeout(15)
            sock.connect((ip, port))
            sock.settimeout(None)
            return sock
        except OSError:
            continue
    logger.info("deny (no global address): %s", host)
    return None


def _relay(a: socket.socket, b: socket.socket) -> None:
    """Pipe bytes both ways between two sockets until either closes."""
    socks = [a, b]
    try:
        while True:
            readable, _, errored = select.select(socks, [], socks, 60)
            if errored or not readable:
                break
            for src in readable:
                dst = b if src is a else a
                data = src.recv(_BUFSIZE)
                if not data:
                    return
                dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in socks:
            try:
                s.close()
            except OSError:
                pass


class _Handler(StreamRequestHandler):
    """Handle one proxied request: CONNECT (https) or an absolute-URI GET/…."""

    allowlist: List[str] = []

    def handle(self) -> None:
        """Parse the first request line and dispatch, denying by default."""
        try:
            line = self.rfile.readline(65536).decode("latin-1").strip()
        except OSError:
            return
        parts = line.split()
        if len(parts) != 3:
            self._deny(400, "bad request")
            return
        method, target, _version = parts
        if method.upper() == "CONNECT":
            self._handle_connect(target)
        else:
            self._handle_absolute(method, target)

    def _handle_connect(self, target: str) -> None:
        """Tunnel an HTTPS CONNECT to an allowlisted, global host on 443."""
        host, _, port_s = target.rpartition(":")
        try:
            port = int(port_s)
        except ValueError:
            self._deny(400, "bad CONNECT target")
            return
        if port not in _CONNECT_PORTS:
            self._deny(403, "port not permitted")
            return
        upstream = _connect_checked(host, port, self.allowlist)
        if upstream is None:
            self._deny(403, "egress denied")
            return
        self.wfile.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        self.wfile.flush()
        _relay(self.connection, upstream)

    def _handle_absolute(self, method: str, target: str) -> None:
        """Forward a plain-HTTP absolute-URI request to an allowlisted host."""
        if not target.lower().startswith("http://"):
            self._deny(400, "only absolute http:// targets are proxied")
            return
        rest = target[len("http://") :]
        authority, _, path = rest.partition("/")
        host, _, port_s = authority.partition(":")
        port = int(port_s) if port_s.isdigit() else 80
        if port != 80:
            self._deny(403, "port not permitted")
            return
        upstream = _connect_checked(host, port, self.allowlist)
        if upstream is None:
            self._deny(403, "egress denied")
            return
        try:
            # Re-issue as origin-form to the upstream, then splice.
            request = f"{method} /{path} HTTP/1.1\r\n".encode("latin-1")
            upstream.sendall(request)
            # Forward the remaining request headers/body verbatim.
            _relay(self.connection, upstream)
        except OSError:
            self._deny(502, "upstream error")

    def _deny(self, code: int, message: str) -> None:
        """Send a short error response (best-effort)."""
        try:
            body = message.encode("latin-1")
            self.wfile.write(
                f"HTTP/1.1 {code} {message}\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Connection: close\r\n\r\n".encode("latin-1") + body
            )
            self.wfile.flush()
        except OSError:
            pass


class _Server(ThreadingTCPServer):
    """A threaded proxy server; reuse the address so restarts are clean."""

    allow_reuse_address = True
    daemon_threads = True


def serve(host: str, port: int, allowlist: List[str]) -> _Server:
    """Start the proxy server on ``host:port`` with ``allowlist``."""
    handler = type("_BoundHandler", (_Handler,), {"allowlist": allowlist})
    server = _Server((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main() -> None:
    """Run the proxy from ``EGRESS_ALLOWLIST`` / ``EGRESS_PORT`` env (foreground)."""
    logging.basicConfig(level=logging.INFO)
    allowlist = parse_allowlist(os.environ.get("EGRESS_ALLOWLIST"))
    port = int(os.environ.get("EGRESS_PORT", "8080"))
    logger.info("egress proxy on :%d, allowlist=%s", port, allowlist)
    server = _Server(
        ("0.0.0.0", port),
        type("_BoundHandler", (_Handler,), {"allowlist": allowlist}),
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
