"""Integration tests for ``LocalSandbox`` — real subprocesses on the host.

The local backend has **no isolation boundary** (that's the honest design
position); these tests pin the behaviour it *does* promise: it enforces policy
fail-closed, runs in the agent's workspace with a scrubbed environment, kills
the whole process group on timeout, caps output, and confines file access to
the workspace.
"""

import os

import pytest

from gimle.hugin.sandbox.local import LocalSandbox
from gimle.hugin.sandbox.policy import Policy
from gimle.hugin.sandbox.sandbox import PolicyDenied, SandboxSpec

pytestmark = pytest.mark.integration

SPEC = SandboxSpec(backend="local")


@pytest.fixture
def sandbox(tmp_path):
    """Yield a started LocalSandbox under a temp dir, stopped on teardown."""
    box = LocalSandbox(SPEC, session_id="sess1", workspace_root=str(tmp_path))
    box.start()
    yield box
    box.stop()


def _cwd(sandbox, agent="agent-a", branch="main"):
    return sandbox.workspace_for(agent, branch)


class TestExec:
    """Running commands, exit codes, cwd, and env scrubbing."""

    def test_runs_command_and_captures_stdout(self, sandbox):
        """A successful command returns exit 0 and its stdout."""
        result = sandbox.exec(
            "echo hello", policy=Policy(), cwd=_cwd(sandbox), timeout_s=10
        )
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert not result.timed_out

    def test_nonzero_exit_is_reported_not_raised(self, sandbox):
        """A non-zero exit is data on the result, not an exception."""
        result = sandbox.exec(
            "exit 3", policy=Policy(), cwd=_cwd(sandbox), timeout_s=10
        )
        assert result.exit_code == 3
        assert not result.timed_out

    def test_denied_command_raises_policy_denied(self, sandbox):
        """Policy is enforced inside exec (fail closed), raising PolicyDenied."""
        with pytest.raises(PolicyDenied):
            sandbox.exec(
                "dd if=/dev/zero of=/dev/sda",
                policy=Policy(),
                cwd=_cwd(sandbox),
                timeout_s=10,
            )

    def test_runs_in_the_given_workspace(self, sandbox):
        """The command's cwd is the agent workspace."""
        cwd = _cwd(sandbox)
        result = sandbox.exec("pwd", policy=Policy(), cwd=cwd, timeout_s=10)
        assert os.path.realpath(result.stdout.strip()) == os.path.realpath(cwd)

    def test_environment_is_scrubbed(self, sandbox, monkeypatch):
        """Secrets in the parent env do not leak to the command."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "super-secret")
        result = sandbox.exec(
            "echo key=$ANTHROPIC_API_KEY",
            policy=Policy(),
            cwd=_cwd(sandbox),
            timeout_s=10,
        )
        assert "super-secret" not in result.stdout
        assert result.stdout.strip() == "key="

    def test_home_is_the_workspace(self, sandbox):
        """HOME points at the workspace, not the real user home."""
        cwd = _cwd(sandbox)
        result = sandbox.exec(
            "echo $HOME", policy=Policy(), cwd=cwd, timeout_s=10
        )
        assert os.path.realpath(result.stdout.strip()) == os.path.realpath(cwd)


class TestTimeout:
    """Timeout handling and process-group kill."""

    def test_timeout_flags_and_returns_promptly(self, sandbox):
        """A command exceeding the timeout is killed and flagged."""
        import time

        start = time.monotonic()
        result = sandbox.exec(
            "sleep 30", policy=Policy(), cwd=_cwd(sandbox), timeout_s=1
        )
        elapsed = time.monotonic() - start
        assert result.timed_out
        assert elapsed < 10  # killed near the 1s deadline, not after 30s

    def test_child_process_group_is_killed(self, sandbox):
        """A backgrounded child started by the command is killed too."""
        import time

        cwd = _cwd(sandbox)
        # Write a pid file for a child that would outlive a naive kill.
        marker = os.path.join(cwd, "child.pid")
        sandbox.exec(
            f"(sleep 30 & echo $! > {marker}); sleep 30",
            policy=Policy(),
            cwd=cwd,
            timeout_s=1,
        )
        time.sleep(0.5)
        with open(marker) as handle:
            child_pid = int(handle.read().strip())
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)  # gone -> group kill worked


class TestOutputTruncation:
    """Output capping behaviour."""

    def test_large_output_is_truncated_tail_biased(self, sandbox):
        """Output over the cap is truncated, keeping the tail."""
        policy = Policy(max_output_bytes=300)
        result = sandbox.exec(
            "for i in $(seq 1 1000); do echo line-$i; done",
            policy=policy,
            cwd=_cwd(sandbox),
            timeout_s=10,
            max_output_bytes=300,
        )
        assert result.truncated
        assert len(result.stdout.encode()) <= 600  # cap + marker slack
        assert "line-1000" in result.stdout  # tail preserved

    def test_small_output_is_not_truncated(self, sandbox):
        """Output under the cap is returned whole."""
        result = sandbox.exec(
            "echo small", policy=Policy(), cwd=_cwd(sandbox), timeout_s=10
        )
        assert not result.truncated


class TestWorkspaces:
    """Per-(agent, branch) workspace directories."""

    def test_workspace_is_per_agent_and_branch(self, sandbox):
        """Each (agent, branch) gets its own existing directory."""
        a_main = sandbox.workspace_for("agent-a", "main")
        a_feat = sandbox.workspace_for("agent-a", "feature")
        b_main = sandbox.workspace_for("agent-b", "main")
        assert a_main != a_feat != b_main
        assert a_main != b_main
        for path in (a_main, a_feat, b_main):
            assert os.path.isdir(path)


class TestFileAccess:
    """put_file/get_file and workspace confinement."""

    def test_put_and_get_file_round_trip(self, sandbox):
        """A file written into the workspace reads back byte-for-byte."""
        sandbox.put_file("notes/todo.txt", b"remember milk")
        assert sandbox.get_file("notes/todo.txt") == b"remember milk"

    def test_get_file_rejects_symlink_escape(self, sandbox, tmp_path):
        """A symlink pointing outside the workspace cannot be read."""
        secret = tmp_path / "outside_secret.txt"
        secret.write_text("classified")
        root = sandbox.workspace_for("agent-a", "main")
        link = os.path.join(root, "escape")
        os.symlink(str(secret), link)
        with pytest.raises(PolicyDenied):
            sandbox.get_file(
                os.path.join("agents", "agent-a", "main", "escape")
            )


def test_stop_is_idempotent(tmp_path):
    """stop() is safe to call twice and on an unstarted sandbox."""
    box = LocalSandbox(SPEC, session_id="s", workspace_root=str(tmp_path))
    box.stop()  # never started
    box.start()
    box.stop()
    box.stop()


def test_start_writes_owner_stamp(tmp_path):
    """start() stamps the workspace with the current PID for the reaper."""
    import json

    from gimle.hugin.sandbox.local import OWNER_FILE

    box = LocalSandbox(SPEC, session_id="s", workspace_root=str(tmp_path))
    box.start()
    stamp = tmp_path / "s" / OWNER_FILE
    assert stamp.exists()
    assert json.loads(stamp.read_text())["pid"] == os.getpid()
