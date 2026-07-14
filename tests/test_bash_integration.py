"""End-to-end wiring test: the bash tool through the real framework path.

The unit tests drive ``bash`` with a hand-built stack. This one goes through
``Tool.execute_tool`` on a *real* Agent/Session/Environment against a real
``LocalSandbox`` running real subprocesses — so it catches the integration
seams the fakes can't: that ``execute_tool`` injects ``stack`` and ``branch``,
that ``config.options`` / ``session.id`` / ``agent.id`` / ``env_vars`` all
resolve on a real stack, and that a real command runs and comes back mapped.
"""

import pytest

import gimle.hugin.tools  # noqa: F401  (registers builtins.bash)
from gimle.hugin.sandbox import LocalSandbox, SandboxManager, SandboxSpec
from gimle.hugin.tools.tool import Tool

pytestmark = pytest.mark.integration

SPEC = SandboxSpec(backend="local")


def _seed_real_sandbox(agent, tmp_path):
    """Give the agent's session a real LocalSandbox rooted under tmp_path."""
    sandbox = LocalSandbox(
        SPEC, session_id=agent.session.id, workspace_root=str(tmp_path)
    )
    agent.session.sandbox = SandboxManager(
        SPEC, agent.session.id, sandbox=sandbox
    )


def test_bash_runs_a_real_command_through_execute_tool(mock_agent, tmp_path):
    """execute_tool injects the stack; the real backend runs the command."""
    _seed_real_sandbox(mock_agent, tmp_path)
    tool = Tool.get_tool("builtins.bash")

    result = Tool.execute_tool(
        tool, mock_agent.stack, None, command="echo hello-e2e"
    )

    assert result.is_error is False
    assert "hello-e2e" in result.content["stdout"]
    assert result.content["exit_code"] == 0


def test_execute_tool_threads_branch_into_the_workspace(mock_agent, tmp_path):
    """The injected branch reaches workspace_for — branches are isolated."""
    _seed_real_sandbox(mock_agent, tmp_path)
    tool = Tool.get_tool("builtins.bash")

    result = Tool.execute_tool(
        tool, mock_agent.stack, "feature-x", command="pwd"
    )

    assert result.is_error is False
    cwd = result.content["stdout"].strip()
    assert cwd.endswith("/feature-x")
    assert mock_agent.id in cwd


def test_denied_command_is_refused_through_the_real_path(mock_agent, tmp_path):
    """A policy denial comes back as a recoverable error, not a crash."""
    _seed_real_sandbox(mock_agent, tmp_path)
    tool = Tool.get_tool("builtins.bash")

    result = Tool.execute_tool(
        tool, mock_agent.stack, None, command="dd if=/dev/zero of=/dev/sda"
    )

    assert result.is_error is True
    assert "denied" in result.content
