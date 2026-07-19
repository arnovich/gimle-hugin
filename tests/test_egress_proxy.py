"""The egress proxy's security policy: allowlist + private-IP/rebinding deny.

The proxy is the sandbox's only route out (task 033), so what it refuses is
unreachable. These tests pin the two mandatory controls — the host allowlist and
the deny of any host that resolves to a non-global address (link-local/metadata,
RFC1918, loopback) — as pure logic and end-to-end against a live proxy, including
the DNS-rebinding case (an allowlisted host that resolves to a private IP).
"""

import ipaddress
import socket
from typing import List, Tuple

from gimle.hugin.sandbox import egress_proxy


class TestAllowlist:
    """Host allowlist matching (empty = deny-all; subdomains included)."""

    def test_parse_allowlist(self):
        """Comma/space separated, lowercased, trailing dots stripped."""
        assert egress_proxy.parse_allowlist("pypi.org, github.com") == [
            "pypi.org",
            "github.com",
        ]
        assert egress_proxy.parse_allowlist("") == []
        assert egress_proxy.parse_allowlist(None) == []

    def test_exact_and_subdomain_match(self):
        """A host matches an exact entry or any of its subdomains."""
        allow = ["pythonhosted.org", "github.com"]
        assert egress_proxy.host_allowed("github.com", allow)
        assert egress_proxy.host_allowed("files.pythonhosted.org", allow)
        assert egress_proxy.host_allowed("GitHub.com.", allow)  # normalized

    def test_non_match_and_empty_are_denied(self):
        """A non-listed host, and everything under an empty list, is denied."""
        assert not egress_proxy.host_allowed("evil.example", ["github.com"])
        assert not egress_proxy.host_allowed("github.com", [])
        # Not a subdomain — a suffix that isn't a dotted boundary.
        assert not egress_proxy.host_allowed("notgithub.com", ["github.com"])


class TestPrivateIpDeny:
    """Only globally-routable resolved addresses survive — the core control."""

    def test_metadata_and_private_and_loopback_are_filtered(self):
        """Link-local (metadata), RFC1918, and loopback resolve to nothing."""
        assert egress_proxy.safe_global_addresses("169.254.169.254", 80) == []
        assert egress_proxy.safe_global_addresses("10.5.5.5", 80) == []
        assert egress_proxy.safe_global_addresses("192.168.1.1", 80) == []
        assert egress_proxy.safe_global_addresses("127.0.0.1", 80) == []

    def test_a_global_address_survives(self):
        """A globally-routable literal is returned to connect to."""
        addrs = egress_proxy.safe_global_addresses("1.1.1.1", 80)
        assert "1.1.1.1" in [ip for _f, ip in addrs]


class TestEmbeddedIpv4Deny:
    """Embedded-IPv4 forms are unwrapped so ``is_global`` can't be bypassed.

    The subtle SSRF: an allowlisted domain serving an AAAA of the metadata IP in
    IPv4-mapped or NAT64 form. ``is_global`` on the outer IPv6 passes (always for
    NAT64, and for IPv4-mapped on pre-CVE-2024-4032 stdlib), but the OS routes it
    to the embedded IPv4 — so the embedded address must be judged instead.
    """

    def test_ipv4_mapped_metadata_is_denied(self):
        """``::ffff:169.254.169.254`` resolves to the embedded metadata IP → deny."""
        assert (
            egress_proxy._safe_connect_target(
                ipaddress.ip_address("::ffff:169.254.169.254")
            )
            is None
        )

    def test_nat64_metadata_is_denied(self):
        """NAT64 ``64:ff9b::a9fe:a9fe`` embeds 169.254.169.254 → deny."""
        assert (
            egress_proxy._safe_connect_target(
                ipaddress.ip_address("64:ff9b::a9fe:a9fe")
            )
            is None
        )

    def test_ipv4_mapped_private_is_denied(self):
        """A mapped RFC1918 address (``::ffff:10.0.0.1``) is denied too."""
        assert (
            egress_proxy._safe_connect_target(
                ipaddress.ip_address("::ffff:10.0.0.1")
            )
            is None
        )

    def test_mapped_global_is_unwrapped_to_ipv4(self):
        """A mapped *global* address connects over clean IPv4 to the embedded IP."""
        target = egress_proxy._safe_connect_target(
            ipaddress.ip_address("::ffff:1.1.1.1")
        )
        assert target == (int(socket.AF_INET), "1.1.1.1")

    def test_embedded_ipv4_extraction(self):
        """Both mapped and NAT64 forms unwrap to the same embedded IPv4."""
        meta = ipaddress.ip_address("169.254.169.254")
        assert (
            egress_proxy._embedded_ipv4(
                ipaddress.ip_address("::ffff:169.254.169.254")
            )
            == meta
        )
        assert (
            egress_proxy._embedded_ipv4(
                ipaddress.ip_address("64:ff9b::a9fe:a9fe")
            )
            == meta
        )
        assert (
            egress_proxy._embedded_ipv4(ipaddress.ip_address("1.1.1.1")) is None
        )


class TestPortParsing:
    """Port parsing is defensive against exotic-unicode ``isdigit`` traps."""

    def test_unicode_superscript_is_rejected(self):
        """``"²"`` is ``isdigit()`` but not ``int()``-able → None, not a crash."""
        assert egress_proxy._parse_port("²") is None

    def test_valid_and_out_of_range(self):
        """A normal port parses; 0 and >65535 are rejected."""
        assert egress_proxy._parse_port("443") == 443
        assert egress_proxy._parse_port("0") is None
        assert egress_proxy._parse_port("70000") is None
        assert egress_proxy._parse_port("nope") is None


def _serve(allowlist: List[str]):
    """Start the proxy on an ephemeral localhost port; return (server, addr)."""
    server = egress_proxy.serve("127.0.0.1", 0, allowlist)
    return server, server.server_address


def _request(addr: Tuple[str, int], line: str) -> str:
    """Send one proxy request line and return the response status line."""
    sock = socket.create_connection(addr, timeout=5)
    try:
        sock.sendall(line.encode("latin-1") + b"\r\n\r\n")
        data = sock.recv(4096).decode("latin-1", "replace")
        return data.splitlines()[0] if data else ""
    finally:
        sock.close()


class TestProxyDenies:
    """End-to-end deny paths against a live proxy (the security assertions)."""

    def test_connect_to_non_allowlisted_is_403(self):
        """A CONNECT to a host not on the allowlist is refused."""
        server, addr = _serve(["github.com"])
        try:
            status = _request(addr, "CONNECT evil.example:443 HTTP/1.1")
            assert "403" in status
        finally:
            server.shutdown()

    def test_allowlisted_host_resolving_private_is_403(self):
        """DNS-rebinding: an allowlisted host resolving to a private IP is denied.

        ``localhost`` is on the allowlist but resolves to loopback, so the
        private-IP deny (not the allowlist) must still refuse it — proving the
        allowlist alone cannot be used to reach a private/metadata address.
        """
        server, addr = _serve(["localhost"])
        try:
            status = _request(addr, "CONNECT localhost:443 HTTP/1.1")
            assert "403" in status
        finally:
            server.shutdown()

    def test_connect_to_non_tls_port_is_403(self):
        """CONNECT is TLS-only; tunnelling an arbitrary port is refused."""
        server, addr = _serve(["github.com"])
        try:
            status = _request(addr, "CONNECT github.com:22 HTTP/1.1")
            assert "403" in status
        finally:
            server.shutdown()

    def test_plain_http_to_non_allowlisted_is_403(self):
        """A plain-HTTP absolute-URI request to a non-listed host is refused."""
        server, addr = _serve(["github.com"])
        try:
            status = _request(addr, "GET http://evil.example/ HTTP/1.1")
            assert "403" in status
        finally:
            server.shutdown()


class TestProxyTunnels:
    """The allow-path plumbing: CONNECT 200 + byte relay (stubbed connect)."""

    def test_connect_allowed_tunnels_bytes(self, monkeypatch):
        """An allowed CONNECT establishes a tunnel and relays bytes both ways."""
        # A local echo upstream, reachable regardless of the global-IP check.
        echo = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        echo.bind(("127.0.0.1", 0))
        echo.listen(1)

        def _echo_once():
            conn, _ = echo.accept()
            data = conn.recv(1024)
            conn.sendall(b"echo:" + data)
            conn.close()

        import threading

        threading.Thread(target=_echo_once, daemon=True).start()

        def _stub_connect(host, port, allowlist):
            if egress_proxy.host_allowed(host, allowlist):
                s = socket.create_connection(echo.getsockname(), timeout=5)
                return s
            return None

        monkeypatch.setattr(egress_proxy, "_connect_checked", _stub_connect)

        server, addr = _serve(["allowed.test"])
        try:
            sock = socket.create_connection(addr, timeout=5)
            sock.sendall(b"CONNECT allowed.test:443 HTTP/1.1\r\n\r\n")
            status = sock.recv(4096).decode("latin-1")
            assert "200" in status.splitlines()[0]
            sock.sendall(b"ping")
            assert b"echo:ping" in sock.recv(1024)
            sock.close()
        finally:
            server.shutdown()
            echo.close()

    def test_plain_http_forwards_origin_form_with_headers(self, monkeypatch):
        """A plain-HTTP GET reaches upstream in origin-form *with* its headers.

        Regression: reading the request line through a buffered reader stranded
        the remaining headers, so no ``Host`` reached upstream and the response
        relay hung. The unbuffered read + explicit header forward fixes it.
        """
        captured: dict = {}
        upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        upstream.bind(("127.0.0.1", 0))
        upstream.listen(1)

        def _serve_upstream():
            conn, _ = upstream.accept()
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                data += chunk
            captured["request"] = data
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nhi")
            conn.close()

        import threading

        threading.Thread(target=_serve_upstream, daemon=True).start()

        def _stub_connect(host, port, allowlist):
            if egress_proxy.host_allowed(host, allowlist):
                return socket.create_connection(upstream.getsockname(), 5)
            return None

        monkeypatch.setattr(egress_proxy, "_connect_checked", _stub_connect)
        server, addr = _serve(["allowed.test"])
        try:
            sock = socket.create_connection(addr, timeout=5)
            sock.sendall(
                b"GET http://allowed.test/p HTTP/1.1\r\n"
                b"Host: allowed.test\r\nX-Custom: v\r\n\r\n"
            )
            resp = sock.recv(4096)
            sock.close()
            assert b"200 OK" in resp and b"hi" in resp
            request = captured["request"]
            assert request.startswith(b"GET /p HTTP/1.1\r\n")  # origin-form
            assert b"Host: allowed.test\r\n" in request  # header forwarded
            assert b"X-Custom: v\r\n" in request
        finally:
            server.shutdown()
            upstream.close()
