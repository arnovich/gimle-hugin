"""Private child-process entry point for generated loopback test material."""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

from gimle.hugin.swarm.admission import PolicyState
from gimle.hugin.swarm.material import TLSFiles, read_node
from gimle.hugin.swarm.transport import ProbeServer


async def serve(directory: Path) -> None:
    """Expose an ephemeral port to the parent pipe, never a public listener."""
    files = TLSFiles(directory)
    node, policy = read_node(files)
    state = PolicyState(node.root, policy, datetime.now(timezone.utc))
    async with ProbeServer(node, state, files) as port:
        print(port, flush=True)
        await asyncio.Event().wait()


def main() -> int:
    """Keep child diagnostics constant; the harness owns cleanup and reporting."""
    if len(sys.argv) != 2:
        return 2
    try:
        asyncio.run(serve(Path(sys.argv[1])))
    except (Exception, KeyboardInterrupt):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
