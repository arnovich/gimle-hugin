"""Keep model-call budget flags reachable through the public CLI dispatcher."""

import sys

import pytest

from gimle.hugin.cli import cli, run_agent


@pytest.mark.parametrize("flag", ["--max-llm-calls", "--max-steps"])
def test_public_run_forwards_zero_budget_and_iteration_guard(
    flag: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public parser must preserve zero instead of silently using the default."""
    seen = []

    def capture() -> int:
        """Observe the actual arguments passed to the downstream run command."""
        seen.extend(sys.argv[1:])
        return 0

    monkeypatch.setattr(
        sys, "argv", ["hugin", "run", flag, "0", "--max-iterations", "7"]
    )
    monkeypatch.setattr(run_agent, "main", capture)
    assert cli.main() == 0
    assert seen == ["--max-llm-calls", "0", "--max-iterations", "7"]
