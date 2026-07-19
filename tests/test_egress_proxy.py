"""The egress proxy's security policy: allowlist + private-IP/rebinding deny.

The proxy is the sandbox's only route out (task 033), so what it refuses is
unreachable. These tests pin the two mandatory controls — the host allowlist and
the deny of any host that resolves to a non-global address (link-local/metadata,
RFC1918, loopback) — as pure logic and end-to-end against a live proxy, including
the DNS-rebinding case (an allowlisted host that resolves to a private IP).
"""

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
