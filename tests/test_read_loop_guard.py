"""Re-reading the same unchanged file forever is a loop the model cannot see.

`read_generated_file` keeps only its most recent results in context. At a
window of 3, a task reasoning about five files evicted the oldest read on
every new one -- so the model noticed a file it needed was no longer visible,
read it again, and evicted another. Rational from inside, and unbounded: one
improve run spent 18 reads across 5 files and never reached a proposal.

The window is now wide enough for a whole small agent, and a repeat counter
backstops it, because a wider window on its own only moves the threshold.
"""

from types import SimpleNamespace

import pytest
import yaml

from gimle.hugin.apps import get_apps_path
from gimle.hugin.apps.agent_builder.tools.read_generated_file import (
    MAX_REPEAT_READS,
    read_generated_file,
)

BUILDER = get_apps_path() / "agent_builder"


@pytest.fixture
def stack():
    environment = SimpleNamespace(
        env_vars={"generated_files": {"tools/fetch.py": "x = 1\n"}}
    )
    return SimpleNamespace(agent=SimpleNamespace(environment=environment))


class TestTheRepeatGuard:
    """A backstop that does not fire on ordinary use."""

    def test_reading_a_file_a_few_times_is_fine(self, stack):
        """Re-reading before editing is normal and must stay cheap."""
        for _ in range(MAX_REPEAT_READS):
            response = read_generated_file(stack, "tools/fetch.py")

        assert not response.is_error

    def test_reading_it_too_often_is_refused(self, stack):
        """Serving the same bytes forever is the failure being stopped."""
        for _ in range(MAX_REPEAT_READS + 1):
            response = read_generated_file(stack, "tools/fetch.py")

        assert response.is_error
        assert "already been read" in response.content["error"]

    def test_the_refusal_says_what_to_do_instead(self, stack):
        """Something outside the context window has to break the loop."""
        for _ in range(MAX_REPEAT_READS + 1):
            response = read_generated_file(stack, "tools/fetch.py")

        assert "Act on what you have" in response.content["error"]

    def test_other_files_are_unaffected(self, stack):
        """The guard is per file, not a global read budget."""
        stack.agent.environment.env_vars["generated_files"][
            "tools/other.py"
        ] = "y = 2\n"
        for _ in range(MAX_REPEAT_READS + 1):
            read_generated_file(stack, "tools/fetch.py")

        assert not read_generated_file(stack, "tools/other.py").is_error


class TestTheContextWindow:
    """The cap that caused the loop in the first place."""

    def test_it_holds_a_whole_small_agent(self):
        """A generated agent is 4-8 files; a window under that evicts a
        file the task still needs and forces the re-read."""
        options = yaml.safe_load(
            (BUILDER / "tools" / "read_generated_file.yaml").read_text()
        )["options"]

        assert options["context_window"] >= 8
