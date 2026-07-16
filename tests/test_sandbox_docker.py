"""Tests for the DockerSandbox backend.

Two layers. The first asserts the **hardening contract** — every flag that makes
the container a boundary — purely from ``_container_kwargs``, so it runs with no
daemon and no ``docker`` SDK installed: these are the ones that must never
silently regress. The second layer is the real thing: daemon-gated
(``slow``-marked, skipped without a reachable daemon) tests that start a
container and prove the acceptance gate — ``python3 -c 'os.system("id")'`` is
*contained by the runtime*, not denied by the policy.
"""

import os

import pytest

from gimle.hugin.sandbox import DockerSandbox, SandboxSpec, create_sandbox
from gimle.hugin.sandbox.docker import (
    CONTAINER_WORKSPACE,
    LABEL_CREATED,
    LABEL_OWNER_PID,
    LABEL_TTL,
    _sanitize_name,
    container_name,
)
from gimle.hugin.sandbox.policy import Policy
from gimle.hugin.sandbox.sandbox import PolicyDenied


def _docker_available() -> bool:
    """Return whether a docker SDK and a reachable daemon are both present."""
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


requires_docker = pytest.mark.skipif(
    not _docker_available(), reason="requires a reachable docker daemon"
)


def _sandbox(tmp_path, **spec_kwargs) -> DockerSandbox:
    """Build a DockerSandbox rooted under tmp_path (no daemon touched)."""
    spec = SandboxSpec(backend="docker", **spec_kwargs)
    sandbox = create_sandbox(spec, "sess-1", str(tmp_path))
    assert isinstance(sandbox, DockerSandbox)
    return sandbox


class TestHardeningContract:
    """The container-creation flags ARE the boundary; pin every one."""

    def test_no_network_by_default(self, tmp_path):
        """The default is a container that cannot reach anything (network=none)."""
        kwargs = _sandbox(tmp_path)._container_kwargs()
        assert kwargs["network_mode"] == "none"

    def test_network_opt_in_uses_bridge(self, tmp_path):
        """Only an explicit network:true relaxes to a bridge network."""
        kwargs = _sandbox(tmp_path, network=True)._container_kwargs()
        assert kwargs["network_mode"] == "bridge"

    def test_all_capabilities_dropped(self, tmp_path):
        """Every Linux capability is dropped."""
        assert _sandbox(tmp_path)._container_kwargs()["cap_drop"] == ["ALL"]

    def test_no_new_privileges(self, tmp_path):
        """no-new-privileges blocks setuid escalation inside the container."""
        opts = _sandbox(tmp_path)._container_kwargs()["security_opt"]
        assert "no-new-privileges:true" in opts

    def test_readonly_root_and_hardened_tmpfs(self, tmp_path):
        """Rootfs is read-only; /tmp is a noexec,nosuid,size-capped tmpfs."""
        kwargs = _sandbox(tmp_path)._container_kwargs()
        assert kwargs["read_only"] is True
        assert kwargs["tmpfs"]["/tmp"] == "rw,noexec,nosuid,size=256m"

    def test_resource_caps_from_spec(self, tmp_path):
        """cpu/memory/pids from the spec become the container's hard limits."""
        kwargs = _sandbox(
            tmp_path, cpu=1.5, memory="1g", pids=256
        )._container_kwargs()
        assert kwargs["mem_limit"] == "1g"
        assert kwargs["nano_cpus"] == 1_500_000_000
        assert kwargs["pids_limit"] == 256

    def test_ulimits_present(self, tmp_path):
        """nproc/nofile ulimits are set (as plain tuples, SDK-free)."""
        names = {
            name
            for (name, _s, _h) in _sandbox(tmp_path)._container_kwargs()[
                "ulimits"
            ]
        }
        assert names == {"nofile", "nproc"}

    def test_init_reaps_children(self, tmp_path):
        """--init gives PID 1 that reaps double-forked children."""
        assert _sandbox(tmp_path)._container_kwargs()["init"] is True

    def test_runs_as_non_root(self, tmp_path):
        """The container process runs as the host user, never container-root."""
        user = _sandbox(tmp_path)._container_kwargs()["user"]
        assert user != "0:0"
        assert user == f"{os.getuid()}:{os.getgid()}"

    def test_env_has_no_inherited_secrets(self, tmp_path, monkeypatch):
        """A secret in the host env does not leak into the container env."""
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "super-secret")
        env = _sandbox(tmp_path)._container_kwargs()["environment"]
        assert "AWS_SECRET_ACCESS_KEY" not in env
        assert env["HOME"] == CONTAINER_WORKSPACE

    def test_never_mounts_the_docker_socket(self, tmp_path):
        """The docker socket is never bind-mounted (would be a full escape)."""
        volumes = _sandbox(tmp_path)._container_kwargs()["volumes"]
        assert not any("docker.sock" in key for key in volumes)

    def test_workspace_bind_is_the_only_mount(self, tmp_path):
        """The one mount is the session workspace, read-write."""
        volumes = _sandbox(tmp_path)._container_kwargs()["volumes"]
        assert len(volumes) == 1
        ((host, mapping),) = volumes.items()
        assert host == os.path.join(str(tmp_path), "sess-1")
        assert mapping == {"bind": CONTAINER_WORKSPACE, "mode": "rw"}

    def test_labels_identify_the_owner_for_the_reaper(self, tmp_path):
        """Labels carry owner PID + created + ttl so the reaper can judge it."""
        labels = _sandbox(tmp_path)._container_kwargs()["labels"]
        assert labels[LABEL_OWNER_PID] == str(os.getpid())
        assert LABEL_CREATED in labels and LABEL_TTL in labels

    def test_dev_shm_is_hardened_too(self, tmp_path):
        """/dev/shm is a noexec,nosuid tmpfs (docker mounts it rw+exec by default)."""
        tmpfs = _sandbox(tmp_path)._container_kwargs()["tmpfs"]
        assert "noexec" in tmpfs["/dev/shm"]
        assert "nosuid" in tmpfs["/dev/shm"]

    def test_swap_is_pinned_to_the_memory_limit(self, tmp_path):
        """memswap_limit == mem_limit so the memory cap can't be doubled via swap."""
        kwargs = _sandbox(tmp_path, memory="1g")._container_kwargs()
        assert kwargs["memswap_limit"] == kwargs["mem_limit"] == "1g"


class TestExitClassification:
    """124/137/hung map to the right (timed_out, oom_killed) signals."""

    def test_124_is_timeout(self):
        """`timeout`'s 124 is an unambiguous wall-clock timeout."""
        assert DockerSandbox._classify_exit(124, False, 15.0, 15) == (
            True,
            False,
        )

    def test_137_near_deadline_is_timeout_not_oom(self):
        """A TERM-ignoring hang killed after grace (137 at the deadline) = timeout."""
        assert DockerSandbox._classify_exit(137, False, 15.2, 15) == (
            True,
            False,
        )

    def test_137_well_before_deadline_is_oom(self):
        """A SIGKILL long before the deadline is most likely a memory-cap OOM."""
        assert DockerSandbox._classify_exit(137, False, 2.0, 15) == (
            False,
            True,
        )

    def test_hung_is_always_timeout(self):
        """A host-side abandonment is reported as a timeout regardless of code."""
        assert DockerSandbox._classify_exit(-1, True, 30.0, 15) == (True, False)

    def test_clean_exit_is_neither(self):
        """A normal exit (0, or non-zero from the command) is not a failure kind."""
        assert DockerSandbox._classify_exit(0, False, 1.0, 15) == (False, False)
        assert DockerSandbox._classify_exit(1, False, 1.0, 15) == (False, False)


class TestOwnerIsCurrent:
    """Reattach reuses only a container this live process owns."""

    class _FakeContainer:
        def __init__(self, labels):
            self.labels = labels

        status = "running"

    def test_own_pid_is_current(self, tmp_path):
        """A container labelled with our PID is reused."""
        sandbox = _sandbox(tmp_path)
        c = self._FakeContainer({LABEL_OWNER_PID: str(os.getpid())})
        assert sandbox._owner_is_current(c) is True

    def test_foreign_or_dead_pid_is_not_current(self, tmp_path):
        """A container labelled with a different PID (dead prior owner) is not."""
        sandbox = _sandbox(tmp_path)
        assert (
            sandbox._owner_is_current(
                self._FakeContainer({LABEL_OWNER_PID: "999999999"})
            )
            is False
        )

    def test_garbled_label_is_not_current(self, tmp_path):
        """A missing/garbled owner label is treated as not-ours (recreate)."""
        sandbox = _sandbox(tmp_path)
        assert sandbox._owner_is_current(self._FakeContainer({})) is False


class TestNameAndPaths:
    """Naming and the container<->host path mapping."""

    def test_container_name_is_docker_legal_and_prefixed(self):
        """A UUID-ish session id becomes a legal, prefixed container name."""
        spec = SandboxSpec(backend="docker")
        name = container_name("weird/id:x", spec)
        assert name.startswith("hugin-sbx-weird-id-x-")
        assert _sanitize_name("weird/id:x") == "weird-id-x"

    def test_distinct_specs_get_distinct_container_names(self):
        """Two specs in one session map to different containers (per-spec)."""
        session = "sess-9"
        a = container_name(session, SandboxSpec(backend="docker", memory="1g"))
        b = container_name(session, SandboxSpec(backend="docker", memory="2g"))
        assert a != b

    def test_same_spec_gives_a_stable_name(self):
        """The same (session, spec) always resolves to the same container name."""
        spec = SandboxSpec(backend="docker", image="x:1", network=True)
        assert container_name("s", spec) == container_name("s", spec)

    def test_sanitize_collision_is_disambiguated_by_the_hash(self):
        """`weird/id` and `weird-id` sanitize alike but don't share a container."""
        spec = SandboxSpec(backend="docker")
        # Same sanitized fragment, but the raw ids are hashed, so names differ.
        assert container_name("weird/id", spec) != container_name(
            "weird-id", spec
        )

    def test_workspace_for_creates_host_dir_and_returns_container_path(
        self, tmp_path
    ):
        """workspace_for returns a /workspace path and makes the host dir."""
        sandbox = _sandbox(tmp_path)
        path = sandbox.workspace_for("agent-a", "feature")
        assert path == f"{CONTAINER_WORKSPACE}/agents/agent-a/feature"
        assert os.path.isdir(
            os.path.join(
                str(tmp_path), "sess-1", "agents", "agent-a", "feature"
            )
        )

    def test_host_path_maps_workspace_into_the_bind_root(self, tmp_path):
        """A container /workspace path maps back to the host bind-mount root."""
        sandbox = _sandbox(tmp_path)
        host = sandbox._host_path(f"{CONTAINER_WORKSPACE}/agents/x/default")
        assert host == os.path.join(
            str(tmp_path), "sess-1", "agents", "x", "default"
        )


class TestFileConfinement:
    """put_file/get_file confine to the workspace; symlink escapes are refused."""

    def test_put_then_get_roundtrips(self, tmp_path):
        """A file written through put_file reads back through get_file."""
        sandbox = _sandbox(tmp_path)
        sandbox.put_file("notes.txt", b"hello")
        assert sandbox.get_file("notes.txt") == b"hello"

    def test_container_path_is_accepted(self, tmp_path):
        """A /workspace-absolute path is mapped to the host side, not rejected."""
        sandbox = _sandbox(tmp_path)
        sandbox.put_file(f"{CONTAINER_WORKSPACE}/a.txt", b"x")
        assert sandbox.get_file("a.txt") == b"x"

    def test_symlink_escape_is_refused(self, tmp_path):
        """A symlink pointing outside the workspace cannot be read through."""
        sandbox = _sandbox(tmp_path)
        host_root = sandbox._host_root
        os.makedirs(host_root, exist_ok=True)
        secret = tmp_path / "outside.txt"
        secret.write_text("secret")
        os.symlink(str(secret), os.path.join(host_root, "link"))
        with pytest.raises(PolicyDenied):
            sandbox.get_file("link")


class TestBackendRegistration:
    """The docker backend resolves through the registry, no SDK needed to load."""

    def test_create_sandbox_resolves_docker(self, tmp_path):
        """create_sandbox builds a DockerSandbox for backend: docker."""
        spec = SandboxSpec(backend="docker")
        assert isinstance(
            create_sandbox(spec, "s", str(tmp_path)), DockerSandbox
        )


# --------------------------------------------------------------------------
# Daemon-gated: the real boundary. Skipped without a reachable docker daemon.
# --------------------------------------------------------------------------

DAEMON_IMAGE = "python:3.12-slim"


@pytest.fixture
def running_sandbox(tmp_path):
    """Start a real DockerSandbox on a small public image; always tear it down."""
    spec = SandboxSpec(backend="docker", image=DAEMON_IMAGE, memory="512m")
    sandbox = create_sandbox(spec, "itest-sess", str(tmp_path))
    sandbox.start()
    try:
        yield sandbox
    finally:
        sandbox.stop()


@pytest.mark.slow
@requires_docker
class TestContainmentGate:
    """The acceptance gate: the runtime contains, the policy does not deny.

    The backend-*interchangeable* half of this (interpreter-not-denied, host fs
    unreachable) is asserted once for all backends in
    ``test_sandbox_contract.py``. What stays here is docker-*specific*: no
    network by default, not-container-root, the real hardening flags. Add new
    cross-backend containment assertions to the contract suite; add docker-only
    ones here.
    """

    def test_interpreter_runs_it_is_not_denied(self, running_sandbox):
        """python3 -c 'os.system("id")' RUNS (denylist lets interpreters through)."""
        cwd = running_sandbox.workspace_for("a", None)
        result = running_sandbox.exec(
            "python3 -c 'import os; os.system(\"id\")'",
            policy=Policy(),
            cwd=cwd,
            timeout_s=15,
        )
        assert result.exit_code == 0
        assert "uid=" in result.stdout  # it executed; it was not refused

    def test_host_filesystem_is_not_reachable(self, running_sandbox, tmp_path):
        """A host secret outside the workspace is invisible in the container."""
        secret = tmp_path / "host_secret.txt"
        secret.write_text("TOP-SECRET")
        cwd = running_sandbox.workspace_for("a", None)
        result = running_sandbox.exec(
            f"cat {secret}", policy=Policy(), cwd=cwd, timeout_s=15
        )
        assert result.exit_code != 0
        assert "TOP-SECRET" not in result.stdout

    def test_process_is_not_container_root(self, running_sandbox):
        """The uid inside the container is the host user, and specifically not 0."""
        cwd = running_sandbox.workspace_for("a", None)
        result = running_sandbox.exec(
            "id -u", policy=Policy(), cwd=cwd, timeout_s=15
        )
        uid = result.stdout.strip()
        assert uid == str(os.getuid())
        assert uid != "0"  # not container-root (the guard would refuse root)

    def test_no_network_by_default(self, running_sandbox):
        """With network:false the container cannot open an outbound socket."""
        cwd = running_sandbox.workspace_for("a", None)
        result = running_sandbox.exec(
            'python3 -c "import socket; '
            "socket.create_connection(('1.1.1.1', 53), 3)\"",
            policy=Policy(),
            cwd=cwd,
            timeout_s=15,
        )
        assert result.exit_code != 0  # no route out


@pytest.mark.slow
@requires_docker
class TestContainerLifecycle:
    """Real hardening flags, resume-reattach, teardown, and reaping."""

    def test_hardening_flags_are_set_on_the_real_container(
        self, running_sandbox
    ):
        """Inspect the started container: the boundary flags are actually on."""
        attrs = running_sandbox._container.attrs
        host = attrs["HostConfig"]
        assert host["NetworkMode"] == "none"
        assert host["ReadonlyRootfs"] is True
        assert "ALL" in host["CapDrop"]
        assert any("no-new-privileges" in o for o in host["SecurityOpt"])
        assert host["PidsLimit"] == 512

    def test_stop_removes_the_container(self, tmp_path):
        """close()/stop() releases the container — no leak on a clean exit."""
        import docker

        spec = SandboxSpec(backend="docker", image=DAEMON_IMAGE)
        sandbox = create_sandbox(spec, "stop-sess", str(tmp_path))
        sandbox.start()
        name = sandbox._name
        sandbox.stop()
        client = docker.from_env()
        with pytest.raises(docker.errors.NotFound):
            client.containers.get(name)

    def test_resume_reattaches_the_same_workspace(self, tmp_path):
        """A file written in one session is present after a resume (same id)."""
        spec = SandboxSpec(backend="docker", image=DAEMON_IMAGE)
        first = create_sandbox(spec, "resume-sess", str(tmp_path))
        first.start()
        cwd = first.workspace_for("a", None)
        first.exec(
            "echo persisted > marker.txt",
            policy=Policy(),
            cwd=cwd,
            timeout_s=15,
        )
        try:
            second = create_sandbox(spec, "resume-sess", str(tmp_path))
            second.start()
            result = second.exec(
                "cat marker.txt", policy=Policy(), cwd=cwd, timeout_s=15
            )
            assert "persisted" in result.stdout
        finally:
            second.stop()

    def test_resume_by_a_new_owner_recreates_with_fresh_labels(
        self, tmp_path, monkeypatch
    ):
        """A container left by a dead owner is recreated so its labels refresh.

        Otherwise the immutable owner-PID label would name a dead process and
        the startup reaper would remove the live resumed session's container.
        Simulate a different owner by faking getpid() on the "resume".
        """
        spec = SandboxSpec(backend="docker", image=DAEMON_IMAGE)
        first = create_sandbox(spec, "reown-sess", str(tmp_path))
        first.start()
        first_id = first._container.id
        try:
            monkeypatch.setattr(os, "getpid", lambda: 424242)
            second = create_sandbox(spec, "reown-sess", str(tmp_path))
            second.start()
            assert second._container.id != first_id  # recreated
            assert (
                second._container.labels[LABEL_OWNER_PID] == "424242"
            )  # labels now name the live (resumed) owner
        finally:
            second.stop()

    def test_missing_image_fails_fast_with_a_build_hint(self, tmp_path):
        """A never-built default image raises a clear, actionable error."""
        spec = SandboxSpec(backend="docker", image="gimle/does-not-exist:nope")
        sandbox = create_sandbox(spec, "noimg-sess", str(tmp_path))
        with pytest.raises(RuntimeError, match="docker build"):
            sandbox.start()

    def test_backgrounded_process_does_not_hang_the_call(self, running_sandbox):
        """A command that backgrounds a pipe-holding child still returns."""
        cwd = running_sandbox.workspace_for("a", None)
        # `sleep 30 &` would hold the exec's stdout pipe open; the host-side
        # deadline (or foreground-exit detection) must let exec() return anyway.
        result = running_sandbox.exec(
            "echo started; sleep 30 &",
            policy=Policy(),
            cwd=cwd,
            timeout_s=5,
        )
        assert "started" in result.stdout
