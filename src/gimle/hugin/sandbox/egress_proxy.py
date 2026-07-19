"""A tiny forward proxy that filters a docker sandbox's egress by allowlist.

This is the security core of the docker egress filter (task 033). The sandbox
container has no direct route out (an ``internal`` docker network); its only exit
for HTTP(S) is this proxy, running in a dual-homed sidecar. So whatever this
proxy refuses is unreachable over HTTP(S) (but see the DNS caveat below).

Two controls, both mandatory:

- **Host allowlist** — a request is permitted only if its host equals, or is a
  subdomain of, an operator-configured entry. An empty allowlist denies
  everything.
- **Private-IP / DNS-rebinding deny** — the host is resolved *here*, and the
  connection is made to a resolved address only if it is **globally routable**
  (never link-local/metadata ``169.254.169.254``, RFC1918, loopback, CGNAT,
  multicast, reserved). Embedded-IPv4 forms (IPv4-mapped ``::ffff:a.b.c.d`` and
  NAT64 ``64:ff9b::/96``) are unwrapped and the *embedded* IPv4 judged, so an
  ``is_global`` check can't be fooled into reaching the metadata endpoint by an
  AAAA record. Crucially we connect to the *exact IP we checked*, not by
  re-resolving the hostname — so an allowlisted domain whose DNS points at the
  metadata endpoint cannot slip through (the allowlist alone is not enough).

Scope: HTTP (plain, port 80) and HTTPS (``CONNECT`` to 443). A tool that ignores
``HTTP_PROXY`` has no route and simply fails — fail-closed. Stdlib only, so the
sidecar image is ``python:slim`` + this one file.

**Residual channel (documented, not yet closed):** the sandbox still reaches
docker's embedded DNS resolver (it must, to resolve the proxy's container name),
and that resolver forwards external queries via the daemon — so a name like
``<base32-secret>.attacker.example`` can exfiltrate low-bandwidth data over DNS
without ever touching this proxy. It cannot reach the metadata endpoint that way
(DNS carries no reply payload from it), so this is exfil-only. Closing it
(static proxy host + a constrained resolver) is deferred to a follow-up; for now
this backend is HTTP/HTTPS egress control, not a full network jail.
"""

import ipaddress
import logging
import os
import select
import socket
import threading
from ipaddress import IPv4Address, IPv6Address, IPv6Network
from socketserver import StreamRequestHandler, ThreadingTCPServer
from typing import List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

_IPAddress = Union[IPv4Address, IPv6Address]

_CONNECT_PORTS = {443}  # CONNECT is for TLS only
_BUFSIZE = 65536
_MAX_HEADER_LINES = 100
_MAX_HEADER_BYTES = 65536


def _parse_port(port_s: str) -> Optional[int]:
    """Parse a port string to an int in 1..65535, or None if malformed.

    ``str.isdigit()`` is true for exotic unicode digits (e.g. ``"²"``) that
    ``int()`` then rejects, so parse defensively rather than trust ``isdigit``.
    """
    try:
        port = int(port_s)
    except (ValueError, TypeError):
        return None
    return port if 0 < port < 65536 else None


def parse_allowlist(raw: Optional[str]) -> List[str]:
    """Parse a comma/space-separated allowlist into normalized host entries."""
    if not raw:
        return []
    parts = raw.replace(",", " ").split()
    return [p.strip().lower().strip(".") for p in parts if p.strip()]


def host_allowed(host: str, allowlist: List[str]) -> bool:
    """Whether ``host`` equals or is a subdomain of an allowlist entry.

    An empty allowlist denies everything (deny-all default).
    """
    host = host.lower().rstrip(".")
    return any(
        host == entry or host.endswith("." + entry) for entry in allowlist
    )


# NAT64 embeds an IPv4 in the low 32 bits: the well-known prefix and the
# RFC 8215 local prefix. An is_global check on the *IPv6* form passes (True on
# every stdlib), so it must be unwrapped and the embedded IPv4 judged instead.
_NAT64_PREFIXES: Tuple[IPv6Network, ...] = (
    IPv6Network("64:ff9b::/96"),
    IPv6Network("64:ff9b:1::/48"),
)


def _embedded_ipv4(ip: _IPAddress) -> Optional[IPv4Address]:
    """Return the IPv4 embedded in an IPv4-mapped / NAT64 IPv6 address, else None.

    These forms route to the embedded IPv4 at the OS level, so judging the outer
    IPv6 with ``is_global`` misses ``::ffff:169.254.169.254`` (only denied on
    CVE-2024-4032-patched stdlib) and ``64:ff9b::a9fe:a9fe`` (``is_global`` True
    on *all* stdlib) — both of which reach the metadata endpoint.
    """
    if not isinstance(ip, IPv6Address):
        return None
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    for prefix in _NAT64_PREFIXES:
        if ip in prefix:
            return IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def _safe_connect_target(ip: _IPAddress) -> Optional[Tuple[int, str]]:
    """Return the ``(family, ip)`` to connect to for a resolved IP, or None.

    Unwraps IPv4-mapped / NAT64 IPv6 to the embedded IPv4 (and connects over
    IPv4), then requires a globally-routable, non-multicast address — so
    link-local (incl. the metadata endpoint), RFC1918, loopback, CGNAT, and
    reserved ranges all resolve to nothing (deny), whatever form they arrive in.
    """
    embedded = _embedded_ipv4(ip)
    if embedded is not None:
        ip = embedded
    if not ip.is_global or ip.is_multicast:
        return None
    family = socket.AF_INET if ip.version == 4 else socket.AF_INET6
    return int(family), str(ip)


def safe_global_addresses(host: str, port: int) -> List[Tuple[int, str]]:
    """Resolve ``host`` and return only safe, globally-routable ``(family, ip)``.

    Filters out link-local (incl. the metadata endpoint), private (RFC1918),
    loopback, CGNAT, multicast, and reserved addresses — including the
    embedded-IPv4 forms (IPv4-mapped, NAT64) that an ``is_global`` check alone
    would miss — so a hostname that resolves to any of those yields no address
    to connect to (deny).
    """
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return []
    safe: List[Tuple[int, str]] = []
    for _family, _type, _proto, _canon, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        target = _safe_connect_target(ip)
        if target is not None and target not in safe:
            safe.append(target)
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
    """Handle one proxied request: CONNECT (https) or an absolute-URI GET/….

    ``rbufsize = 0`` makes ``rfile`` unbuffered so reading the request line +
    headers never reads ahead into the tunnel/body bytes — otherwise the raw
    relay below would miss buffered data (a stranded ``Host`` header, or a
    corrupted TLS ClientHello).
    """

    allowlist: List[str] = []
    rbufsize = 0
    # Bound the request-parse phase so a slow/greedy client can't hold a proxy
    # thread (and, at pids_limit, egress for a same-session peer) open forever.
    timeout = 20

    def handle(self) -> None:
        """Parse the first request line and dispatch, denying by default."""
        try:
            line = self.rfile.readline(65536).decode("latin-1").strip()
        except OSError:  # includes socket.timeout — a stalled client
            return
        parts = line.split()
        if len(parts) != 3:
            self._read_headers()
            self._deny(400, "bad request")
            return
        method, target, _version = parts
        if method.upper() == "CONNECT":
            self._handle_connect(target)
        else:
            self._handle_absolute(method, target)

    def _read_headers(self) -> List[bytes]:
        """Consume the request headers up to (and including) the blank line.

        Capped in count and bytes so a client that never sends the terminating
        blank line cannot make this grow without bound.
        """
        headers: List[bytes] = []
        total = 0
        while len(headers) < _MAX_HEADER_LINES and total < _MAX_HEADER_BYTES:
            try:
                piece = self.rfile.readline(65536)
            except OSError:  # timeout / reset mid-headers
                break
            if piece in (b"\r\n", b"\n", b""):
                break
            headers.append(piece)
            total += len(piece)
        return headers

    def _relay_after_parse(self, upstream: socket.socket) -> None:
        """Clear the parse-phase timeout, then splice the two sockets."""
        # select() in _relay governs idle now; a per-recv timeout would abort a
        # legitimately quiet-but-open tunnel.
        try:
            self.connection.settimeout(None)
        except OSError:
            pass
        _relay(self.connection, upstream)

    def _handle_connect(self, target: str) -> None:
        """Tunnel an HTTPS CONNECT to an allowlisted, global host on 443."""
        host, _, port_s = target.rpartition(":")
        self._read_headers()  # consume before the tunnel, or they corrupt TLS
        port = _parse_port(port_s)
        if port is None:
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
        self._relay_after_parse(upstream)

    def _handle_absolute(self, method: str, target: str) -> None:
        """Forward a plain-HTTP absolute-URI request to an allowlisted host."""
        headers = self._read_headers()
        if not target.lower().startswith("http://"):
            self._deny(400, "only absolute http:// targets are proxied")
            return
        rest = target[len("http://") :]
        authority, _, path = rest.partition("/")
        host, _, port_s = authority.partition(":")
        port = _parse_port(port_s) if port_s else 80
        if port != 80:
            self._deny(403, "port not permitted")
            return
        upstream = _connect_checked(host, port, self.allowlist)
        if upstream is None:
            self._deny(403, "egress denied")
            return
        try:
            # Re-issue as origin-form with the original headers, then splice the
            # response (and any request body) both ways.
            request = f"{method} /{path} HTTP/1.1\r\n".encode("latin-1")
            upstream.sendall(request + b"".join(headers) + b"\r\n")
            self._relay_after_parse(upstream)
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
