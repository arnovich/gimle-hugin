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

from .sandbox_backends import docker_available as _docker_available

requires_docker = pytest.mark.skipif(
    not _docker_available(),
    reason="requires a reachable docker daemon with the test image pulled",
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
        """Only an explicit unrestricted network:true relaxes to a bridge."""
        kwargs = _sandbox(
            tmp_path, network=True, allow_unrestricted_egress=True
        )._container_kwargs()
        assert kwargs["network_mode"] == "bridge"

    def test_filtered_egress_joins_internal_network_via_proxy(self, tmp_path):
        """network:true + an allowlist joins the internal net and sets HTTP_PROXY.

        The sandbox's ``network_mode`` is the per-session *internal* network (no
        direct route out), and its env points HTTP(S)_PROXY at the sidecar — so
        its only exit is the allowlist proxy.
        """
        sandbox = _sandbox(
            tmp_path, network=True, egress_allowlist=("pypi.org",)
        )
        kwargs = sandbox._container_kwargs()
        assert kwargs["network_mode"] == sandbox._egress_net_name
        assert kwargs["network_mode"].startswith("hugin-egress-")
        env = kwargs["environment"]
        expected = f"http://{sandbox._proxy_name}:8080"
        assert env["HTTP_PROXY"] == expected
        assert env["HTTPS_PROXY"] == expected
        assert env["https_proxy"] == expected

    def test_unfiltered_network_sets_no_proxy(self, tmp_path):
        """An unrestricted bridge sets no proxy env (nothing to route through)."""
        env = _sandbox(
            tmp_path, network=True, allow_unrestricted_egress=True
        )._container_kwargs()["environment"]
        assert "HTTP_PROXY" not in env

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
        """Labels carry owner PID + created + ttl + host/boot so it can judge it."""
        from gimle.hugin.sandbox.docker import LABEL_BOOT, LABEL_HOST

        labels = _sandbox(tmp_path)._container_kwargs()["labels"]
        assert labels[LABEL_OWNER_PID] == str(os.getpid())
        assert LABEL_CREATED in labels and LABEL_TTL in labels
        # Host + boot scope the owner-PID test to this host+boot (task 030).
        assert labels[LABEL_HOST] and labels[LABEL_BOOT]

    def test_dev_shm_is_hardened_too(self, tmp_path):
        """/dev/shm is a noexec,nosuid tmpfs (docker mounts it rw+exec by default)."""
        tmpfs = _sandbox(tmp_path)._container_kwargs()["tmpfs"]
        assert "noexec" in tmpfs["/dev/shm"]
        assert "nosuid" in tmpfs["/dev/shm"]

    def test_swap_is_pinned_to_the_memory_limit(self, tmp_path):
        """memswap_limit == mem_limit so the memory cap can't be doubled via swap."""
        kwargs = _sandbox(tmp_path, memory="1g")._container_kwargs()
        assert kwargs["memswap_limit"] == kwargs["mem_limit"] == "1g"


class TestProxyHardeningContract:
    """The proxy sidecar IS the egress boundary — pin its kwargs daemon-free.

    Mirrors ``TestHardeningContract`` for the sandbox: ``_proxy_kwargs`` is pure,
    so a regression that drops a hardening flag on the *proxy* is caught here,
    not only by the slow end-to-end suite.
    """

    def _kwargs(self, tmp_path):
        """Return the proxy run-kwargs for a filtered-egress sandbox."""
        return _sandbox(
            tmp_path, network=True, egress_allowlist=("pypi.org",)
        )._proxy_kwargs()

    def test_runs_the_proxy_script_on_the_internal_network(self, tmp_path):
        """It runs the bind-mounted proxy script, joined to the internal net."""
        kwargs = self._kwargs(tmp_path)
        assert kwargs["command"] == ["python3", "/opt/egress_proxy.py"]
        assert kwargs["network"].startswith("hugin-egress-")

    def test_hardened_like_the_sandbox(self, tmp_path):
        """All caps dropped, no-new-privs, read-only rootfs, non-root, capped."""
        kwargs = self._kwargs(tmp_path)
        assert kwargs["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in kwargs["security_opt"]
        assert kwargs["read_only"] is True
        assert kwargs["user"] == f"{os.getuid()}:{os.getgid()}"
        assert kwargs["mem_limit"] == kwargs["memswap_limit"] == "128m"
        assert kwargs["nano_cpus"] > 0

    def test_allowlist_and_port_reach_the_proxy_env(self, tmp_path):
        """The allowlist is passed comma-joined; the port matches HTTP_PROXY."""
        env = _sandbox(
            tmp_path,
            network=True,
            egress_allowlist=("pypi.org", "github.com"),
        )._proxy_kwargs()["environment"]
        assert env["EGRESS_ALLOWLIST"] == "pypi.org,github.com"
        assert env["EGRESS_PORT"] == "8080"

    def test_only_the_readonly_script_is_mounted(self, tmp_path):
        """The proxy's sole mount is the proxy script, read-only."""
        volumes = self._kwargs(tmp_path)["volumes"]
        ((host, mapping),) = volumes.items()
        assert host.endswith("egress_proxy.py")
        assert mapping == {"bind": "/opt/egress_proxy.py", "mode": "ro"}


class TestEgressGating:
    """network:true is fail-closed: unfiltered egress needs explicit opt-in.

    Pure spec checks — no daemon — so they run everywhere and can never silently
    regress (an accidentally-unfiltered container on a cloud host is the whole
    metadata-exfil risk).
    """

    def test_network_true_is_refused_by_default(self, tmp_path):
        """network:true without the ack raises, naming the metadata risk."""
        sandbox = _sandbox(tmp_path, network=True)
        with pytest.raises(RuntimeError, match="169.254.169.254"):
            sandbox._assert_egress_acknowledged()

    def test_explicit_ack_allows_it(self, tmp_path):
        """allow_unrestricted_egress:true lets network:true through (with a warn)."""
        sandbox = _sandbox(
            tmp_path, network=True, allow_unrestricted_egress=True
        )
        sandbox._assert_egress_acknowledged()  # must not raise

    def test_filtered_egress_is_not_gated(self, tmp_path):
        """A non-empty egress_allowlist is the filtered path — never refused."""
        sandbox = _sandbox(
            tmp_path, network=True, egress_allowlist=("pypi.org",)
        )
        assert sandbox._egress_filtered()
        sandbox._assert_egress_acknowledged()  # must not raise

    def test_empty_allowlist_is_still_gated(self, tmp_path):
        """An empty allowlist is not a policy — network:true is still refused."""
        sandbox = _sandbox(tmp_path, network=True, egress_allowlist=())
        assert not sandbox._egress_filtered()
        with pytest.raises(RuntimeError, match="egress_allowlist"):
            sandbox._assert_egress_acknowledged()

    def test_no_network_is_never_gated(self, tmp_path):
        """The safe default (no network) is unaffected by the gate."""
        _sandbox(tmp_path)._assert_egress_acknowledged()  # must not raise


class TestTeardownSafety:
    """The proxy/network teardown runs from stop() (a resume path): never raise.

    A raising ``stop()`` escapes ``ToolResult.step`` and permanently wedges the
    agent's stack, so a flaky/dead daemon must not turn teardown into an
    exception — and a non-egress sandbox must not touch the daemon at all.
    """

    class _AngryClient:
        """A docker client whose every use raises — proves we don't touch it."""

        @property
        def containers(self):
            """Raise on any container access."""
            raise RuntimeError("daemon down")

        @property
        def networks(self):
            """Raise on any network access."""
            raise RuntimeError("daemon down")

    def test_non_egress_teardown_never_touches_the_daemon(self, tmp_path):
        """A plain (non-egress) sandbox's proxy/network teardown is a no-op."""
        sandbox = _sandbox(tmp_path)  # network=False -> not egress-filtered
        sandbox._client = self._AngryClient()
        sandbox._remove_proxy_and_network()  # must not raise

    def test_filtered_teardown_swallows_a_dead_daemon(self, tmp_path):
        """A dead daemon can't make a filtered sandbox's teardown raise."""
        sandbox = _sandbox(
            tmp_path, network=True, egress_allowlist=("pypi.org",)
        )
        sandbox._client = self._AngryClient()
        sandbox._remove_proxy_and_network()  # must not raise


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

    def test_distinct_allowlists_get_distinct_containers(self):
        """Differing only by egress_allowlist must not collide onto one proxy.

        The allowlist names the proxy + internal network too; two agents that
        differ only here must get separate infra, or the second silently inherits
        the first's egress policy.
        """
        session = "sess-egress"
        a = container_name(
            session,
            SandboxSpec(
                backend="docker", network=True, egress_allowlist=("pypi.org",)
            ),
        )
        b = container_name(
            session,
            SandboxSpec(
                backend="docker",
                network=True,
                egress_allowlist=("evil.example",),
            ),
        )
        assert a != b

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
        sandbox.put_file("a", None, "notes.txt", b"hello")
        assert sandbox.get_file("a", None, "notes.txt") == b"hello"

    def test_container_path_under_the_agent_workspace_is_accepted(
        self, tmp_path
    ):
        """A /workspace-absolute path in the agent's own tree maps host-side."""
        sandbox = _sandbox(tmp_path)
        container = f"{sandbox.workspace_for('a', None)}/a.txt"
        sandbox.put_file("a", None, container, b"x")
        assert sandbox.get_file("a", None, "a.txt") == b"x"

    def test_symlink_escape_is_refused(self, tmp_path):
        """A symlink pointing outside the workspace cannot be read through."""
        sandbox = _sandbox(tmp_path)
        agent_host = sandbox._host_path(sandbox.workspace_for("a", None))
        os.makedirs(agent_host, exist_ok=True)
        secret = tmp_path / "outside.txt"
        secret.write_text("secret")
        os.symlink(str(secret), os.path.join(agent_host, "link"))
        with pytest.raises(PolicyDenied):
            sandbox.get_file("a", None, "link")


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

    def test_network_true_is_refused_at_start_with_no_container(self, tmp_path):
        """A network:true start() fails closed and creates no container."""
        import docker

        spec = SandboxSpec(backend="docker", image=DAEMON_IMAGE, network=True)
        sandbox = create_sandbox(spec, "egress-sess", str(tmp_path))
        with pytest.raises(RuntimeError, match="169.254.169.254"):
            sandbox.start()
        client = docker.from_env()
        with pytest.raises(docker.errors.NotFound):
            client.containers.get(sandbox._name)

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


@pytest.fixture
def filtered_sandbox(tmp_path):
    """Yield a real docker sandbox with FILTERED egress (allowlist proxy)."""
    spec = SandboxSpec(
        backend="docker",
        image=DAEMON_IMAGE,
        network=True,
        egress_allowlist=("example.com",),
        memory="512m",
    )
    sandbox = create_sandbox(spec, "egress-e2e-sess", str(tmp_path))
    sandbox.start()
    try:
        yield sandbox
    finally:
        sandbox.stop()


@pytest.mark.slow
@requires_docker
class TestFilteredEgress:
    """The real egress filter end-to-end: proxy sidecar + internal network.

    Proves the design's headline properties against a live daemon: the metadata
    endpoint is unreachable, there is no direct egress, a non-allowlisted host is
    refused, an allowlisted host works, and the proxy + network do not leak. The
    allow path needs outbound internet (``example.com``) — ``slow`` +
    daemon-gated, run intentionally.
    """

    def _run(self, sandbox, script, timeout_s=25):
        """Run a one-liner ``python3 -c`` snippet in the sandbox."""
        cwd = sandbox.workspace_for("a", None)
        return sandbox.exec(
            f'python3 -c "{script}"',
            policy=Policy(),
            cwd=cwd,
            timeout_s=timeout_s,
        )

    def test_no_direct_egress(self, filtered_sandbox):
        """A raw socket bypasses the proxy: the internal net has no route out."""
        result = self._run(
            filtered_sandbox,
            "import socket; socket.setdefaulttimeout(4); "
            "socket.create_connection(('1.1.1.1', 443))",
        )
        assert result.exit_code != 0  # unreachable — no direct egress

    def test_metadata_endpoint_is_blocked(self, filtered_sandbox):
        """The proxy refuses the link-local metadata endpoint (the headline gate)."""
        result = self._run(
            filtered_sandbox,
            "import urllib.request as u; "
            "u.urlopen('http://169.254.169.254/latest/meta-data/', timeout=6)",
        )
        assert result.exit_code != 0
        assert "ami-id" not in result.stdout  # no metadata content leaked

    def test_non_allowlisted_host_is_denied(self, filtered_sandbox):
        """A host not on the allowlist is refused by the proxy (403)."""
        result = self._run(
            filtered_sandbox,
            "import urllib.request as u; u.urlopen('https://pypi.org/', timeout=8)",
        )
        assert result.exit_code != 0

    def test_allowlisted_host_is_reachable(self, filtered_sandbox):
        """An allowlisted host is reachable through the proxy (needs internet)."""
        result = self._run(
            filtered_sandbox,
            "import urllib.request as u; "
            "print(u.urlopen('https://example.com/', timeout=15).status)",
        )
        assert result.exit_code == 0
        assert "200" in result.stdout

    def test_stop_removes_proxy_and_network(self, tmp_path):
        """stop() tears down the proxy sidecar and the internal network."""
        import docker

        spec = SandboxSpec(
            backend="docker",
            image=DAEMON_IMAGE,
            network=True,
            egress_allowlist=("example.com",),
            memory="512m",
        )
        sandbox = create_sandbox(spec, "egress-teardown-sess", str(tmp_path))
        sandbox.start()
        proxy_name = sandbox._proxy_name
        net_name = sandbox._egress_net_name
        client = docker.from_env()
        assert client.containers.get(proxy_name).status == "running"
        client.networks.get(net_name)  # exists while running
        sandbox.stop()
        with pytest.raises(docker.errors.NotFound):
            client.containers.get(proxy_name)
        with pytest.raises(docker.errors.NotFound):
            client.networks.get(net_name)
