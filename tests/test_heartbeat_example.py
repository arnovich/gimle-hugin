"""Tests for heartbeat example tools."""

import os
import sys
import tempfile
from unittest.mock import MagicMock

import pytest

from gimle.hugin.agent.config import Config
from gimle.hugin.agent.session_state import SessionState
from gimle.hugin.interaction.waiting import Waiting

# Allow importing the example tools
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "examples",
        "heartbeat",
        "tools",
    ),
)
from check_folder import check_folder  # noqa: E402
from sleep_until_next_check import (  # noqa: E402
    sleep_until_next_check,
)


@pytest.fixture
def mock_session():
    """Create a mock session with real SessionState."""
    session = MagicMock()
    session.environment = MagicMock()
    session.environment.config_registry = MagicMock()
    session.environment.task_registry = MagicMock()
    session.environment.template_registry = MagicMock()
    session.environment.template_registry.registered.return_value = {}
    session.state = SessionState()
    return session


@pytest.fixture
def mock_agent(mock_session):
    """Create a mock agent with real SessionState."""
    from gimle.hugin.agent.agent import Agent

    config = Config(
        name="test_config",
        description="Test config",
        system_template="test_system",
        tools=[],
    )
    return Agent(config=config, session=mock_session)


@pytest.fixture
def watched_folder():
    """Create a temporary folder for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestCheckFolder:
    """Tests for the check_folder sensor tool."""

    def test_folder_not_found(self, mock_agent):
        """Test returns error when folder does not exist."""
        result = check_folder(
            mock_agent.stack, "/nonexistent/path"
        )
        assert result.is_error is True
        assert "not found" in result.content["error"]

    def test_os_error(self, mock_agent, watched_folder):
        """Test returns error on OS-level read failure."""
        os.chmod(watched_folder, 0o000)
        try:
            result = check_folder(
                mock_agent.stack, watched_folder
            )
            assert result.is_error is True
            assert "Cannot read folder" in result.content["error"]
        finally:
            os.chmod(watched_folder, 0o755)

    def test_first_check_finds_files(
        self, mock_agent, watched_folder
    ):
        """Test first check detects all files as new."""
        open(os.path.join(watched_folder, "a.txt"), "w").close()
        open(os.path.join(watched_folder, "b.txt"), "w").close()

        result = check_folder(mock_agent.stack, watched_folder)

        assert result.is_error is False
        assert sorted(result.content["new_files"]) == [
            "a.txt",
            "b.txt",
        ]
        # No response_interaction — goes to LLM for analysis
        assert result.response_interaction is None
        # seen_files updated in shared state
        seen = mock_agent.stack.get_shared_state("seen_files")
        assert "a.txt" in seen
        assert "b.txt" in seen

    def test_subsequent_check_only_reports_new(
        self, mock_agent, watched_folder
    ):
        """Test that already-seen files are not reported again."""
        open(os.path.join(watched_folder, "a.txt"), "w").close()
        check_folder(mock_agent.stack, watched_folder)

        open(os.path.join(watched_folder, "b.txt"), "w").close()
        result = check_folder(mock_agent.stack, watched_folder)

        assert result.content["new_files"] == ["b.txt"]

    def test_empty_check_returns_waiting(
        self, mock_agent, watched_folder
    ):
        """Test empty folder returns a silent heartbeat Waiting."""
        result = check_folder(mock_agent.stack, watched_folder)

        assert result.is_error is False
        waiting = result.response_interaction
        assert isinstance(waiting, Waiting)
        assert waiting.condition is not None
        assert waiting.condition.evaluator == "wait_for_ticks"
        assert waiting.condition.parameters == {"ticks": 3}
        assert waiting.next_tool == "check_folder"
        assert waiting.next_tool_args == {
            "folder_path": watched_folder,
            "interval": 3,
        }

    def test_custom_interval_propagates(
        self, mock_agent, watched_folder
    ):
        """Test that a custom interval is used in the Waiting."""
        result = check_folder(
            mock_agent.stack, watched_folder, interval=10
        )

        waiting = result.response_interaction
        assert isinstance(waiting, Waiting)
        assert waiting.condition.parameters == {"ticks": 10}
        assert waiting.next_tool_args["interval"] == 10

    def test_no_auto_termination(
        self, mock_agent, watched_folder
    ):
        """Test that repeated empty checks keep looping (no auto-stop)."""
        for _ in range(10):
            result = check_folder(
                mock_agent.stack, watched_folder
            )
            # Every empty check should return a Waiting, never terminate
            assert isinstance(result.response_interaction, Waiting)

    def test_heartbeat_resumes_after_new_files(
        self, mock_agent, watched_folder
    ):
        """Test the full cycle: empty → files → empty continues."""
        # Empty check — silent loop
        r1 = check_folder(mock_agent.stack, watched_folder)
        assert isinstance(r1.response_interaction, Waiting)

        # Add a file — goes to LLM
        open(os.path.join(watched_folder, "x.txt"), "w").close()
        r2 = check_folder(mock_agent.stack, watched_folder)
        assert r2.response_interaction is None
        assert r2.content["new_files"] == ["x.txt"]

        # Empty again — silent loop continues
        r3 = check_folder(mock_agent.stack, watched_folder)
        assert isinstance(r3.response_interaction, Waiting)


class TestSleepUntilNextCheck:
    """Tests for the sleep_until_next_check tool."""

    def test_returns_waiting_with_correct_condition(
        self, mock_agent
    ):
        """Test returns Waiting with wait_for_ticks condition."""
        result = sleep_until_next_check(
            mock_agent.stack, "/tmp/watched"
        )

        assert result.is_error is False
        waiting = result.response_interaction
        assert isinstance(waiting, Waiting)
        assert waiting.condition.evaluator == "wait_for_ticks"
        assert waiting.condition.parameters == {"ticks": 3}

    def test_passes_folder_and_interval_to_next_tool(
        self, mock_agent
    ):
        """Test folder_path and interval are forwarded."""
        result = sleep_until_next_check(
            mock_agent.stack, "/my/folder", interval=7
        )

        waiting = result.response_interaction
        assert isinstance(waiting, Waiting)
        assert waiting.next_tool == "check_folder"
        assert waiting.next_tool_args == {
            "folder_path": "/my/folder",
            "interval": 7,
        }

    def test_custom_interval_in_condition(self, mock_agent):
        """Test that custom interval flows into the condition."""
        result = sleep_until_next_check(
            mock_agent.stack, "/tmp", interval=5
        )

        waiting = result.response_interaction
        assert isinstance(waiting, Waiting)
        assert waiting.condition.parameters == {"ticks": 5}
