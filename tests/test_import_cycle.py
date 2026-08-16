"""Every public subpackage must import cold, on its own.

Regression test for the cycle that broke production on 2026-08-16:

    interaction/__init__ -> agent_call -> task_definition -> ask_oracle
        -> tools/__init__ -> launch_agent -> interaction.agent_call

`import gimle.hugin` and `import gimle.hugin.interaction` both raised
ImportError on a partially initialized `agent_call`, while `import
gimle.hugin.tools` first happened to be safe. The whole suite stayed green
because pytest's collection order reaches `tools` before `interaction` — so a
test that merely imports these modules in-process proves nothing.

Each import therefore runs in a FRESH interpreter, one per entry point. That is
the only way to see the order-dependence: once any module is in `sys.modules`,
the cycle is already resolved and cannot fail again in that process.
"""

import subprocess
import sys

import pytest

#: Entry points a downstream consumer may legitimately import first. Anything
#: reachable from outside the package belongs here; a new subpackage that is not
#: listed is untested, not exempt.
ENTRY_POINTS = [
    "gimle.hugin",
    "gimle.hugin.agent",
    "gimle.hugin.artifacts",
    "gimle.hugin.dreaming",
    "gimle.hugin.interaction",
    "gimle.hugin.tools",
]


@pytest.mark.parametrize("module", ENTRY_POINTS)
def test_imports_cold_in_a_fresh_interpreter(module: str) -> None:
    """The entry point must import as the very first import of a process."""
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"`import {module}` fails as the first import of a process.\n"
        f"This is an import cycle: it will pass in-process once something else "
        f"has already imported the package in a working order.\n\n"
        f"{result.stderr}"
    )
