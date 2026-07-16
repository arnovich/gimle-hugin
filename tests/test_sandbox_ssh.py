"""Tests for the SSHSandbox backend.

Everything host-dependent goes through one subprocess seam (``_run``), so the
unit layer mocks that seam and asserts the security-relevant *command
construction* (hardened ssh options, the env-scrubbed remote wrapper, workspace
confinement) plus the exit mapping — no real host, no network. A final,
env-gated (``HUGIN_SSH_TEST_HOST``) layer runs the containment gate against a
real disposable box: the command executes on the remote machine, not locally.
"""

import os
import posixpath
from types import SimpleNamespace

import pytest

from gimle.hugin.sandbox import SandboxSpec, SSHSandbox, create_sandbox
from gimle.hugin.sandbox.policy import Policy
from gimle.hugin.sandbox.sandbox import PolicyDenied


def _sandbox(**spec_kwargs) -> SSHSandbox:
    """Build an SSHSandbox for a fake host (no connection made)."""
    spec_kwargs.setdefault("host", "user@box.example.com")
    spec = SandboxSpec(backend="ssh", **spec_kwargs)
    sandbox = create_sandbox(spec, "sess-1", "/tmp/hugin-sbx")
    assert isinstance(sandbox, SSHSandbox)
    return sandbox


def _started(sandbox: SSHSandbox) -> SSHSandbox:
    """Mark a sandbox as started with a known remote root (no real start)."""
    sandbox._remote_root = "/home/u/.hugin-sandbox/sess-1"
    sandbox._started = True
    return sandbox


class _FakeRun:
    """Records `_run` calls and returns queued (or default-OK) results."""

    def __init__(self, *results):
        """Queue ``(rc, out, err, capped, hung)`` tuples; default OK when empty."""
        self.results = list(results)
        self.calls = []

    def __call__(self, argv, *, input_bytes=b"", deadline_s):
        self.calls.append(
            SimpleNamespace(
                argv=argv, input_bytes=input_bytes, deadline_s=deadline_s
            )
        )
        if self.results:
            return self.results.pop(0)
        return (0, b"", b"", False, False)


class TestConfig:
    """Backend resolution and config validation."""

    def test_registry_resolves_ssh(self):
        """create_sandbox builds an SSHSandbox for backend: ssh."""
        assert isinstance(_sandbox(), SSHSandbox)

    def test_missing_host_is_a_clear_error(self):
        """backend: ssh with no host fails loud, not with a cryptic later error."""
        with pytest.raises(ValueError, match="requires options.bash.host"):
            create_sandbox(SandboxSpec(backend="ssh"), "s", "/tmp/x")


class TestCommandConstruction:
    """The security-relevant parts of what we hand to ssh."""

    def test_connection_hardening_options(self):
        """Agent-forwarding off, batch mode on, connect + keepalive set."""
        opts = _sandbox()._ssh_opts()
        assert "ForwardAgent=no" in opts
        assert "BatchMode=yes" in opts
        assert any(o.startswith("ConnectTimeout=") for o in opts)
        assert any(o.startswith("ServerAliveInterval=") for o in opts)

    def test_control_master_socket_is_owned(self):
        """A ControlPath under our control is set (cleaned in stop())."""
        sandbox = _sandbox()
        opts = sandbox._ssh_opts()
        assert f"ControlPath={sandbox._control_path}" in opts
        assert "ControlMaster=auto" in opts

    def test_key_is_wired_when_configured(self):
        """A configured ssh_key becomes -i <key>; absent -> no -i."""
        opts = _sandbox(ssh_key="/keys/id")._ssh_opts()
        assert opts[opts.index("-i") + 1] == "/keys/id"
        assert "-i" not in _sandbox()._ssh_opts()

    def test_remote_wrapper_scrubs_env_and_bounds_time(self):
        """The wrapper cds, scrubs env (env -i), and runs under a remote timeout."""
        wrapper = _sandbox()._remote_wrapper("/home/u/ws", 15)
        assert wrapper.startswith("cd /home/u/ws && ")
        assert "env -i HOME=/home/u/ws" in wrapper
        assert "timeout -k 5 15 bash -c" in wrapper
        # The untrusted command travels over stdin, not the argv.
        assert '"$(cat)"' in wrapper

    def test_ssh_argv_targets_the_host(self):
        """The argv is ssh <opts> <host> <remote-command>."""
        argv = _sandbox()._ssh_argv("echo hi")
        assert argv[0] == "ssh"
        assert argv[-2] == "user@box.example.com"
        assert argv[-1] == "echo hi"

    def test_start_script_sweeps_and_stamps(self):
        """Start script TTL-sweeps siblings, makes the root, writes the owner."""
        script = _sandbox()._remote_start_script()
        assert "-mmin +" in script  # mtime TTL sweep
        assert (
            "base64 -d" in script
        )  # owner marker written without quoting games
        assert ".hugin_owner.json" in script


class TestConfinement:
    """put_file/get_file resolve within the remote workspace only."""

    def test_relative_path_joins_the_root(self):
        """A relative path resolves under the remote root."""
        sandbox = _started(_sandbox())
        assert sandbox._confine("notes.txt") == (
            "/home/u/.hugin-sandbox/sess-1/notes.txt"
        )

    def test_dotdot_escape_is_refused(self):
        """A traversal outside the workspace is rejected."""
        sandbox = _started(_sandbox())
        with pytest.raises(PolicyDenied):
            sandbox._confine("../../etc/passwd")

    def test_absolute_outside_is_refused(self):
        """An absolute path outside the root is rejected."""
        sandbox = _started(_sandbox())
        with pytest.raises(PolicyDenied):
            sandbox._confine("/etc/passwd")


class TestExec:
    """Policy enforcement and exit mapping, with the subprocess seam mocked."""

    def test_denied_command_raises_without_running(self):
        """A policy-denied command never reaches the ssh seam."""
        sandbox = _started(_sandbox())
        fake = _FakeRun()
        sandbox._run = fake
        with pytest.raises(PolicyDenied):
            sandbox.exec(
                "dd if=/dev/zero of=/dev/sda",
                policy=Policy(),
                cwd="/home/u/.hugin-sandbox/sess-1",
                timeout_s=15,
            )
        assert fake.calls == []

    def test_not_started_raises(self):
        """Calling exec on an unstarted sandbox is a clear error."""
        sandbox = _sandbox()
        sandbox._run = _FakeRun()
        with pytest.raises(RuntimeError, match="not started"):
            sandbox.exec("echo hi", policy=Policy(), cwd="/x", timeout_s=15)

    def test_successful_command_maps_to_result(self):
        """A clean remote exit maps to a non-error ExecResult with output."""
        sandbox = _started(_sandbox())
        sandbox._run = _FakeRun((0, b"hello\n", b"", False, False))
        result = sandbox.exec(
            "echo hello",
            policy=Policy(),
            cwd="/home/u/.hugin-sandbox/sess-1",
            timeout_s=15,
        )
        assert result.exit_code == 0
        assert result.stdout == "hello\n"
        assert result.timed_out is False

    def test_transport_error_is_not_retried(self):
        """An ssh transport failure (255) raises a do-not-retry error."""
        sandbox = _started(_sandbox())
        sandbox._run = _FakeRun(
            (255, b"", b"ssh: connect: timed out", False, False)
        )
        with pytest.raises(RuntimeError, match="do not retry"):
            sandbox.exec(
                "echo hi",
                policy=Policy(),
                cwd="/home/u/.hugin-sandbox/sess-1",
                timeout_s=15,
            )

    def test_remote_timeout_is_reported(self):
        """Remote `timeout` exit 124 is surfaced as timed_out."""
        sandbox = _started(_sandbox())
        sandbox._run = _FakeRun((124, b"", b"", False, False))
        result = sandbox.exec(
            "sleep 99",
            policy=Policy(),
            cwd="/home/u/.hugin-sandbox/sess-1",
            timeout_s=5,
        )
        assert result.timed_out is True

    def test_truncated_output_spills_remotely(self):
        """Truncated output triggers a remote spill write (a second ssh call)."""
        sandbox = _started(_sandbox())
        big = b"x" * 50_000
        sandbox._run = _FakeRun(
            (0, big, b"", False, False),  # the command
            (0, b"", b"", False, False),  # the spill write
        )
        result = sandbox.exec(
            "cat big",
            policy=Policy(),
            cwd="/home/u/.hugin-sandbox/sess-1",
            timeout_s=15,
            max_output_bytes=1000,
        )
        assert result.truncated is True
        # The spill call wrote the full output to .hugin/last_output.txt.
        spill_call = sandbox._run.calls[-1]
        assert any("last_output.txt" in a for a in spill_call.argv)


class TestWorkspaceAndFiles:
    """Workspace creation and file transfer over the seam."""

    def test_workspace_for_creates_once_and_caches(self):
        """workspace_for mkdir -p's once per (agent, branch), then caches."""
        sandbox = _started(_sandbox())
        sandbox._run = _FakeRun()
        p1 = sandbox.workspace_for("agent-a", "feature")
        p2 = sandbox.workspace_for("agent-a", "feature")
        assert (
            p1 == p2 == ("/home/u/.hugin-sandbox/sess-1/agents/agent-a/feature")
        )
        assert len(sandbox._run.calls) == 1  # cached the second time

    def test_put_and_get_use_the_confined_remote_path(self):
        """put_file/get_file operate on a confined remote path over ssh."""
        sandbox = _started(_sandbox())
        sandbox._run = _FakeRun(
            (0, b"", b"", False, False),  # put
            (0, b"stored", b"", False, False),  # get
        )
        sandbox.put_file("out.txt", b"data")
        assert sandbox.get_file("out.txt") == b"stored"
        put_argv = " ".join(sandbox._run.calls[0].argv)
        assert "sess-1/out.txt" in put_argv

    def test_get_file_failure_raises(self):
        """A non-zero remote cat (missing file) raises."""
        sandbox = _started(_sandbox())
        sandbox._run = _FakeRun((1, b"", b"No such file", False, False))
        with pytest.raises(RuntimeError, match="get_file failed"):
            sandbox.get_file("missing.txt")


class TestRunSeam:
    """The real subprocess seam every other test mocks — exercised for real.

    Uses harmless local commands (no ssh, no network) so it runs anywhere, and
    validates the stdin feed, output capture, byte cap, and deadline/kill logic
    that all the mocked tests depend on being correct.
    """

    def test_feeds_stdin_and_captures_stdout(self):
        """input_bytes reaches the process; its stdout comes back."""
        rc, out, err, capped, hung = _sandbox()._run(
            ["cat"], input_bytes=b"hello-seam", deadline_s=5
        )
        assert rc == 0
        assert out == b"hello-seam"
        assert capped is False and hung is False

    def test_propagates_the_exit_code(self):
        """A non-zero process exit is returned, not swallowed."""
        rc, _out, _err, _capped, _hung = _sandbox()._run(
            ["sh", "-c", "exit 3"], deadline_s=5
        )
        assert rc == 3

    def test_deadline_kills_and_reports_hung(self):
        """A process past the deadline is killed and flagged hung."""
        rc, _out, _err, _capped, hung = _sandbox()._run(
            ["sh", "-c", "sleep 5"], deadline_s=0.3
        )
        assert hung is True
        assert rc != 0

    def test_output_cap_stops_a_flood(self):
        """More than the byte ceiling of output trips capped and is bounded."""
        rc, out, _err, capped, _hung = _sandbox()._run(
            ["cat"], input_bytes=b"x" * 3_000_000, deadline_s=10
        )
        assert capped is True
        assert len(out) <= 2_000_000  # buffered output is hard-capped
        assert rc is not None


class TestLifecycle:
    """start()/stop() over the seam."""

    def test_start_captures_the_remote_root(self):
        """start() runs the setup script and records the printed root path."""
        sandbox = _sandbox()
        sandbox._run = _FakeRun(
            (0, b"/home/u/.hugin-sandbox/sess-1", b"", False, False)
        )
        sandbox.start()
        assert sandbox._started is True
        assert sandbox._remote_root == "/home/u/.hugin-sandbox/sess-1"

    def test_start_transport_error_raises(self):
        """An unreachable host raises a clear error from start()."""
        sandbox = _sandbox()
        sandbox._run = _FakeRun((255, b"", b"connection refused", False, False))
        with pytest.raises(RuntimeError, match="cannot reach ssh host"):
            sandbox.start()

    def test_start_is_idempotent(self):
        """A second start() on a live sandbox does nothing."""
        sandbox = _started(_sandbox())
        sandbox._run = _FakeRun()
        sandbox.start()
        assert sandbox._run.calls == []

    def test_stop_is_idempotent_and_safe_unstarted(self):
        """stop() on an unstarted sandbox is a no-op."""
        sandbox = _sandbox()
        sandbox._run = _FakeRun()
        sandbox.stop()  # never started — no error, no calls
        assert sandbox._run.calls == []


# --------------------------------------------------------------------------
# Real-host gate. Set HUGIN_SSH_TEST_HOST=user@box (a DISPOSABLE box you don't
# mind the agent touching) to run. Proves the command executes on the remote.
# --------------------------------------------------------------------------

REAL_HOST = os.environ.get("HUGIN_SSH_TEST_HOST")
requires_real_host = pytest.mark.skipif(
    not REAL_HOST, reason="set HUGIN_SSH_TEST_HOST=user@box to run"
)


@pytest.fixture
def real_sandbox(tmp_path):
    """Start a real SSHSandbox against HUGIN_SSH_TEST_HOST; always tear down."""
    spec = SandboxSpec(
        backend="ssh",
        host=REAL_HOST,
        ssh_key=os.environ.get("HUGIN_SSH_TEST_KEY"),
    )
    sandbox = create_sandbox(spec, "itest-sess", str(tmp_path))
    sandbox.start()
    try:
        yield sandbox
    finally:
        sandbox.stop()


@pytest.mark.slow
@requires_real_host
class TestRealHostContainment:
    """The command runs on the remote machine — that IS the boundary."""

    def test_command_runs_on_the_remote(self, real_sandbox):
        """python3 -c 'os.system("id")' runs (not denied) on the remote box."""
        cwd = real_sandbox.workspace_for("a", None)
        result = real_sandbox.exec(
            "python3 -c 'import os; os.system(\"id\")'",
            policy=Policy(),
            cwd=cwd,
            timeout_s=20,
        )
        assert result.exit_code == 0
        assert "uid=" in result.stdout

    def test_it_is_not_the_local_machine(self, real_sandbox):
        """The remote hostname differs from ours — the command is not local."""
        cwd = real_sandbox.workspace_for("a", None)
        result = real_sandbox.exec(
            "hostname", policy=Policy(), cwd=cwd, timeout_s=20
        )
        assert result.stdout.strip() != os.uname().nodename

    def test_files_roundtrip_on_the_remote(self, real_sandbox):
        """put_file then a remote cat sees the same bytes."""
        real_sandbox.workspace_for("a", None)
        real_sandbox.put_file("marker.txt", b"remote-hello")
        cwd = real_sandbox.workspace_for("a", None)
        result = real_sandbox.exec(
            "cat ../../marker.txt || cat "
            + posixpath.join(real_sandbox._remote_root, "marker.txt"),
            policy=Policy(),
            cwd=cwd,
            timeout_s=20,
        )
        assert "remote-hello" in result.stdout
