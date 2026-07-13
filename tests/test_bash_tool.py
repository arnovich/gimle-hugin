"""Tests for the ``builtins.bash`` tool, driven against a FakeSandbox.

These pin the agent-facing behaviour: how a result maps to a ToolResponse
(only denial/timeout/infra are errors — a non-zero exit is not), that policy is
read from ``config.options['bash']`` and enforced before the sandbox runs, and
that the command reaches the backend with the right cwd and policy.
"""

from types import SimpleNamespace

from gimle.hugin.sandbox.fake import FakeSandbox
from gimle.hugin.sandbox.manager import SandboxManager
from gimle.hugin.sandbox.sandbox import ExecResult, SandboxSpec
from gimle.hugin.tools.builtins.bash import bash

LOCAL = SandboxSpec(backend="local")


def _stack(config_options=None, sandbox_manager=None):
    """Build a minimal stack exposing just what the bash tool reads."""
    environment = SimpleNamespace(env_vars={})
    session = SimpleNamespace(id="session-1", sandbox=sandbox_manager)
    config = SimpleNamespace(options=config_options or {})
    agent = SimpleNamespace(
        id="agent-a",
        config=config,
        session=session,
        environment=environment,
    )
    return SimpleNamespace(agent=agent)


def _stack_with_fake(fake, config_options=None):
    """Build a stack whose session owns a manager wrapping ``fake``."""
    manager = SandboxManager(LOCAL, "session-1", sandbox=fake)
    return _stack(config_options=config_options, sandbox_manager=manager)


class TestResultMapping:
    """How an ExecResult becomes a ToolResponse."""

    def test_successful_command_is_not_an_error(self):
        """Exit 0 maps to a non-error response carrying stdout."""
        fake = FakeSandbox(
            ExecResult(exit_code=0, stdout="hi", stderr="", duration_s=0.1)
        )
        response = bash("echo hi", stack=_stack_with_fake(fake))
        assert response.is_error is False
        assert response.content["exit_code"] == 0
        assert response.content["stdout"] == "hi"
        assert fake.last_call.command == "echo hi"

    def test_nonzero_exit_is_not_an_error(self):
        """A completed process that exits non-zero is data, not an error."""
        fake = FakeSandbox(
            ExecResult(exit_code=2, stdout="", stderr="nope", duration_s=0.0)
        )
        response = bash("grep x f", stack=_stack_with_fake(fake))
        assert response.is_error is False
        assert response.content["exit_code"] == 2

    def test_timeout_is_an_error(self):
        """A timed-out command is an error the model must react to."""
        fake = FakeSandbox(
            ExecResult(
                exit_code=-1,
                stdout="",
                stderr="",
                duration_s=1.0,
                timed_out=True,
            )
        )
        response = bash("sleep 99", stack=_stack_with_fake(fake))
        assert response.is_error is True
        assert response.content["timed_out"] is True

    def test_infra_failure_is_an_error(self):
        """A backend that raises maps to an infra_error response."""
        fake = FakeSandbox(raises=RuntimeError("daemon down"))
        response = bash("echo hi", stack=_stack_with_fake(fake))
        assert response.is_error is True
        assert "daemon down" in response.content["infra_error"]


class TestPolicyEnforcement:
    """Policy is read from config and enforced before the sandbox runs."""

    def test_denied_command_short_circuits_before_exec(self):
        """A denied command never reaches the sandbox."""
        fake = FakeSandbox()
        response = bash(
            "dd if=/dev/zero of=/dev/sda", stack=_stack_with_fake(fake)
        )
        assert response.is_error is True
        assert "denied" in response.content
        assert fake.calls == []  # exec never called

    def test_config_policy_is_applied(self):
        """An allowlist policy from config refuses an unlisted command."""
        fake = FakeSandbox()
        options = {"bash": {"policy": {"mode": "allowlist", "allow": ["ls"]}}}
        response = bash("curl http://x", stack=_stack_with_fake(fake, options))
        assert response.is_error is True
        assert "denied" in response.content
        assert fake.calls == []

    def test_escalate_maps_to_needs_approval(self):
        """on_violation=ask_human surfaces a needs_approval response."""
        fake = FakeSandbox()
        options = {"bash": {"policy": {"on_violation": "ask_human"}}}
        response = bash("shutdown now", stack=_stack_with_fake(fake, options))
        assert response.is_error is True
        assert "needs_approval" in response.content
        assert fake.calls == []

    def test_malformed_policy_config_is_reported(self):
        """A bad policy block is a clear config error, not a silent default."""
        fake = FakeSandbox()
        options = {"bash": {"policy": {"modee": "allowlist"}}}
        response = bash("echo hi", stack=_stack_with_fake(fake, options))
        assert response.is_error is True
        assert "invalid bash policy config" in response.content["error"]

    def test_policy_is_passed_through_to_exec(self):
        """The resolved policy (timeout etc.) reaches the sandbox exec."""
        fake = FakeSandbox()
        options = {"bash": {"policy": {"timeout_s": 42}}}
        bash("echo hi", stack=_stack_with_fake(fake, options))
        assert fake.last_call.policy.timeout_s == 42
        assert fake.last_call.timeout_s == 42


class TestWorkspaceRouting:
    """cwd handling and workspace confinement."""

    def test_runs_in_workspace_by_default(self):
        """With no cwd, the command runs in the agent workspace root."""
        fake = FakeSandbox()
        bash("pwd", stack=_stack_with_fake(fake))
        assert fake.last_call.cwd == "/workspace/agents/agent-a/default"

    def test_relative_cwd_is_joined(self):
        """A relative cwd runs in that subdirectory of the workspace."""
        fake = FakeSandbox()
        bash("pwd", cwd="src", stack=_stack_with_fake(fake))
        assert fake.last_call.cwd == "/workspace/agents/agent-a/default/src"

    def test_escaping_cwd_is_refused(self):
        """A cwd that climbs out of the workspace is refused."""
        fake = FakeSandbox()
        response = bash("pwd", cwd="../../etc", stack=_stack_with_fake(fake))
        assert response.is_error is True
        assert "escapes the workspace" in response.content["error"]
        assert fake.calls == []


class TestAudit:
    """Every command outcome is tallied in the session's audit counters."""

    def test_run_is_counted(self):
        """A completed command increments the ``run`` counter."""
        fake = FakeSandbox(
            ExecResult(exit_code=0, stdout="hi", stderr="", duration_s=0.1)
        )
        manager = SandboxManager(LOCAL, "session-1", sandbox=fake)
        stack = _stack(sandbox_manager=manager)
        bash("echo hi", stack=stack)
        assert manager.audit.counters["run"] == 1

    def test_denied_is_counted(self):
        """A policy denial increments the ``denied`` counter, not ``run``."""
        fake = FakeSandbox()
        manager = SandboxManager(LOCAL, "session-1", sandbox=fake)
        stack = _stack(sandbox_manager=manager)
        bash("dd if=/dev/zero of=/dev/sda", stack=stack)
        assert manager.audit.counters["denied"] == 1
        assert manager.audit.counters["run"] == 0

    def test_timeout_is_counted(self):
        """A timed-out command increments the ``timed_out`` counter."""
        fake = FakeSandbox(
            ExecResult(
                exit_code=-1,
                stdout="",
                stderr="",
                duration_s=1.0,
                timed_out=True,
            )
        )
        manager = SandboxManager(LOCAL, "session-1", sandbox=fake)
        stack = _stack(sandbox_manager=manager)
        bash("sleep 99", stack=stack)
        assert manager.audit.counters["timed_out"] == 1


class TestSandboxResolution:
    """Building the sandbox from config when none is pre-seeded."""

    def test_missing_backend_is_a_clear_error(self):
        """An allowed command with no backend named reports it cleanly."""
        response = bash("echo hi", stack=_stack(config_options={"bash": {}}))
        assert response.is_error is True
        assert "sandbox unavailable" in response.content["error"]

    def test_missing_stack_is_handled(self):
        """Called without a stack, the tool errors instead of crashing."""
        response = bash("echo hi", stack=None)
        assert response.is_error is True
