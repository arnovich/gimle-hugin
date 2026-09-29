"""Run the isolated admission experiment without any deployment credentials."""

import asyncio
import importlib.metadata
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import AsyncIterator

import httpx

from gimle.hugin.swarm.admission import verify_credential, verify_policy
from gimle.hugin.swarm.credentials import Authority, certificate_pem
from gimle.hugin.swarm.material import TLSFiles, client_context, write_node
from gimle.hugin.swarm.transport import exchange, probe_record
from gimle.hugin.swarm.wire import ProtocolError, decode

CHILD_START_TIMEOUT = 30.0


class ProbeFailure(RuntimeError):
    """Bounded stage code, never underlying exception text."""

    def __init__(self, stage: str) -> None:
        """Permit only fixed diagnostics suitable for public CI output."""
        allowed = {
            "child_start_failed",
            "tls_connect_failed",
            "authorization_failed",
            "local_io_failed",
            "probe_failed",
        }
        self.stage = stage if stage in allowed else "probe_failed"
        super().__init__(self.stage)


@asynccontextmanager
async def child_server(files: TLSFiles) -> AsyncIterator[int]:
    """Start a real separate process; always stop it before deleting key files."""
    env = {"PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    if "PATH" in os.environ:
        env["PATH"] = os.environ["PATH"]
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "gimle.hugin.swarm._probe_server",
        str(files.directory),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=env,
        limit=1024,
    )
    try:
        if process.stdout is None:
            raise ProtocolError()
        try:
            line = await asyncio.wait_for(
                process.stdout.readline(), timeout=CHILD_START_TIMEOUT
            )
        except TimeoutError:
            raise ProbeFailure("child_start_failed") from None
        if not line.strip().isdigit():
            raise ProbeFailure("child_start_failed")
        port = int(line)
        if not 1 <= port <= 65535:
            raise ProtocolError()
        yield port
    finally:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()


async def run_experiment() -> dict[str, object]:
    """Exercise real TLS in a child process, returning only safe result labels."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    root = Authority.create(now)
    invite = root.invite({"research": ["read", "post"]}, now)
    server, client = invite.join(now), invite.join(now)
    policy = root.policy(now)
    checks: list[str] = []
    with TemporaryDirectory(prefix="hugin-transport-") as directory:
        base = Path(directory)
        server_files = write_node(base / "server", server, policy)
        client_files = write_node(base / "client", client, policy)
        async with child_server(server_files) as port:
            request = probe_record(client)
            accepted = await exchange(
                port,
                server.node_id,
                client_context(client_files),
                "POST",
                "/v0/probe",
                request,
            )
            response = decode(accepted.body)
            if (
                accepted.status != 200
                or response.get("accepted") is not True
                or response.get("nonce")
                != decode(request)["message"]["payload"]["nonce"]
            ):
                raise ProtocolError()
            identity = verify_credential(
                response["credential"],
                accepted.peer_der,
                root.certificate,
                policy,
                now,
                "research",
                "read",
            )
            if identity != server.node_id:
                raise ProtocolError()
            checks.append("mutual_tls_and_grant_binding")
            unauthenticated = client_context(client_files, authenticate=False)
            refreshed = await exchange(
                port, server.node_id, unauthenticated, "GET", "/v0/policy"
            )
            verify_policy(decode(refreshed.body), root.certificate, now)
            rejected = await exchange(
                port,
                server.node_id,
                unauthenticated,
                "POST",
                "/v0/probe",
                request,
            )
            if refreshed.status != 200 or rejected.status != 403:
                raise ProtocolError()
            checks.append("policy_recovery_isolated")
            denied = await exchange(
                port,
                server.node_id,
                client_context(client_files),
                "POST",
                "/v0/probe",
                probe_record(client, action="reply"),
            )
            if denied.status != 403:
                raise ProtocolError()
            checks.append("permission_denied")
            foreign = Authority.create(now)
            stranger = foreign.invite({"research": ["read"]}, now).join(now)
            foreign_files = write_node(
                base / "foreign", stranger, foreign.policy(now)
            )
            foreign_context = client_context(foreign_files)
            foreign_context.load_verify_locations(
                cadata=certificate_pem(root.certificate)
            )
            try:
                await exchange(
                    port,
                    server.node_id,
                    foreign_context,
                    "GET",
                    "/v0/policy",
                )
            except httpx.TransportError:
                checks.append("foreign_swarm_denied")
            else:
                raise ProtocolError()
    return {
        "status": "passed",
        "checks": checks,
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in (
                "aiohttp",
                "httpx",
                "cryptography",
                "pyopenssl",
                "rfc8785",
            )
        },
    }


def main() -> int:
    """Print aggregate results only, never key data, addresses or raw errors."""
    if len(sys.argv) != 1:
        print("Usage: python -m gimle.hugin.swarm.experiment")
        return 2
    try:
        report = asyncio.run(run_experiment())
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        if isinstance(error, ProbeFailure):
            stage = error.stage
        elif isinstance(error, httpx.TransportError):
            stage = "tls_connect_failed"
        elif isinstance(error, ProtocolError):
            stage = "authorization_failed"
        elif isinstance(error, OSError):
            stage = "local_io_failed"
        else:
            stage = "probe_failed"
        print(json.dumps({"status": "failed", "reason": stage}))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
