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

    def test_escaped_child_does_not_hang_exec(self, sandbox):
        """A child that setsid()'s away and holds the pipe cannot hang exec.

        The old code drained with an un-timed communicate() after the kill, so
        an escaped grandchild holding stdout blocked until it exited (30s here),
        defeating the timeout. exec must return near the deadline regardless.
        """
        import time

        start = time.monotonic()
        # Trailing `; true` forces bash to fork python (rather than exec it in
        # place), so python is a group member that can setsid() into its own
        # session and escape the kill while holding the inherited stdout pipe.
        result = sandbox.exec(
            "python3 -c 'import os, time; os.setsid(); time.sleep(30)' ; true",
            policy=Policy(),
            cwd=_cwd(sandbox),
            timeout_s=1,
        )
        elapsed = time.monotonic() - start
        assert result.timed_out
        assert elapsed < 8  # bounded drain, not blocked on the 30s sleep


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
        assert result.spill_path is None  # nothing spilled, nothing to point at

    def test_each_truncation_spills_a_distinct_readable_file(self, sandbox):
        """Two truncated commands spill to different files, both recoverable.

        Regression: a single overwritten ``last_output.txt`` meant a deferred
        read of the earlier command got the later command's output.
        """
        import os

        cwd = _cwd(sandbox)

        def big(marker: str):
            return sandbox.exec(
                f"for i in $(seq 1 1000); do echo {marker}-$i; done",
                policy=Policy(max_output_bytes=300),
                cwd=cwd,
                timeout_s=10,
                max_output_bytes=300,
            )

        first = big("alpha")
        second = big("beta")
        assert first.spill_path and second.spill_path
        assert first.spill_path != second.spill_path  # unique per call
        assert os.path.isabs(first.spill_path)  # usable from any cwd
        with open(first.spill_path, encoding="utf-8") as handle:
            assert "alpha-1000" in handle.read()  # earlier output not clobbered
        with open(second.spill_path, encoding="utf-8") as handle:
            assert "beta-1000" in handle.read()

    def test_runaway_file_write_is_size_capped(self, sandbox, monkeypatch):
        """A single file a command writes is bounded by the fsize cap, not the disk.

        `yes > f` would fill the host disk; the fsize rlimit kills it (SIGXFSZ)
        with the file bounded near the cap — not a timeout, not a success.
        """
        import os

        from gimle.hugin.sandbox import sandbox as sandbox_mod

        monkeypatch.setattr(sandbox_mod, "MAX_FILE_BYTES", 1_048_576)  # 1 MiB
        cwd = _cwd(sandbox)
        result = sandbox.exec(
            "yes > big.txt", policy=Policy(), cwd=cwd, timeout_s=10
        )
        assert result.exit_code != 0  # killed by the file-size cap
        assert result.timed_out is False  # the cap stopped it, not the clock
        size = os.path.getsize(os.path.join(cwd, "big.txt"))
        assert size <= 1_048_576 + 65_536  # bounded near the cap, not unbounded

    def test_runaway_output_is_capped_without_hanging(self, sandbox):
        """Unbounded output is bounded in memory and the process is killed.

        ``yes`` produces output forever; without a byte ceiling the parent
        buffers it all and OOMs. The capture must stop it at the ceiling, well
        before the (10s) timeout, and keep the model-facing output tiny.
        """
        import time

        start = time.monotonic()
        result = sandbox.exec(
            "yes",
            policy=Policy(max_output_bytes=300),
            cwd=_cwd(sandbox),
            timeout_s=10,
            max_output_bytes=300,
        )
        elapsed = time.monotonic() - start
        assert result.truncated
        assert not result.timed_out  # killed for output, not for wall-clock
        assert elapsed < 8
        assert len(result.stdout.encode()) <= 600  # cap + marker slack
        assert "output exceeded" in result.stderr


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
        """A file written into the agent workspace reads back byte-for-byte."""
        sandbox.put_file("a", None, "notes/todo.txt", b"remember milk")
        assert sandbox.get_file("a", None, "notes/todo.txt") == b"remember milk"

    def test_get_file_rejects_symlink_escape(self, sandbox, tmp_path):
        """A symlink pointing outside the workspace cannot be read."""
        secret = tmp_path / "outside_secret.txt"
        secret.write_text("classified")
        root = sandbox.workspace_for("agent-a", "main")
        link = os.path.join(root, "escape")
        os.symlink(str(secret), link)
        with pytest.raises(PolicyDenied):
            sandbox.get_file("agent-a", "main", "escape")

    def test_file_ops_are_confined_to_the_agent(self, sandbox):
        """A path that climbs into a sibling agent's workspace is refused."""
        sandbox.put_file("owner", None, "secret.txt", b"mine")
        sandbox.workspace_for("intruder", None)
        with pytest.raises(PolicyDenied):
            sandbox.get_file("intruder", None, "../owner/secret.txt")


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
    record = json.loads(stamp.read_text())
    assert record["pid"] == os.getpid()
    assert "start_time" in record  # incarnation token for the reaper


def test_start_rewrites_stale_owner_stamp(tmp_path):
    """A resumed session re-stamps its live PID over a stale (dead) one.

    This is the data-loss fix: without rewriting, the stamp would keep the
    previous process's dead PID and the reaper would delete the running
    session's workspace.
    """
    import json

    from gimle.hugin.sandbox.local import OWNER_FILE

    session_root = tmp_path / "s"
    session_root.mkdir()
    stamp = session_root / OWNER_FILE
    stamp.write_text(json.dumps({"pid": 999_000_001, "created": 1.0}))

    box = LocalSandbox(SPEC, session_id="s", workspace_root=str(tmp_path))
    box.start()

    record = json.loads(stamp.read_text())
    assert record["pid"] == os.getpid()  # rewritten to the live owner
    assert record["created"] == 1.0  # original creation time preserved


def test_process_start_time_is_a_stable_token_for_self(tmp_path):
    """process_start_time returns a stable, non-empty token for a live PID."""
    from gimle.hugin.sandbox.local import process_start_time

    first = process_start_time(os.getpid())
    assert isinstance(first, str) and first
    assert process_start_time(os.getpid()) == first  # stable across calls


def test_local_backend_warns_it_is_not_isolated(tmp_path, caplog):
    """Selecting the local backend logs that it provides no isolation."""
    import gimle.hugin.sandbox.local as local_mod

    local_mod._isolation_warned = False  # arm the one-shot warning
    with caplog.at_level("WARNING", logger="gimle.hugin.sandbox.local"):
        LocalSandbox(SPEC, session_id="warn", workspace_root=str(tmp_path))
    assert any("NO isolation" in record.message for record in caplog.records)
