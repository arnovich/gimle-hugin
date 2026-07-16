"""Tests for ``SandboxManager`` and the ``create_sandbox`` factory."""

import pytest

from gimle.hugin.sandbox.fake import FakeSandbox
from gimle.hugin.sandbox.local import LocalSandbox
from gimle.hugin.sandbox.manager import SandboxManager
from gimle.hugin.sandbox.sandbox import SandboxSpec, create_sandbox

LOCAL = SandboxSpec(backend="local")


class TestCreateSandbox:
    """The backend factory."""

    def test_local_backend_builds_local_sandbox(self, tmp_path):
        """backend='local' constructs a LocalSandbox."""
        box = create_sandbox(LOCAL, "s", workspace_root=str(tmp_path))
        assert isinstance(box, LocalSandbox)

    def test_docker_backend_builds_docker_sandbox(self):
        """backend='docker' constructs a DockerSandbox (no daemon touched)."""
        from gimle.hugin.sandbox.docker import DockerSandbox

        box = create_sandbox(SandboxSpec(backend="docker"), "s")
        assert isinstance(box, DockerSandbox)

    def test_ssh_backend_builds_ssh_sandbox(self):
        """backend='ssh' constructs an SSHSandbox (no connection made)."""
        from gimle.hugin.sandbox.ssh import SSHSandbox

        box = create_sandbox(SandboxSpec(backend="ssh", host="user@box"), "s")
        assert isinstance(box, SSHSandbox)

    def test_unknown_backend_is_a_clear_error(self):
        """An unregistered backend fails loud, listing what is known."""
        with pytest.raises(ValueError, match="unknown backend"):
            create_sandbox(SandboxSpec(backend="nope"), "s")


class TestBackendRegistry:
    """Backends are looked up through a registry, not a hardcoded factory."""

    def test_registered_backends_include_the_three_peers(self):
        """local, docker, and ssh are registered out of the box."""
        from gimle.hugin.sandbox.sandbox import registered_backends

        names = registered_backends()
        assert {"local", "docker", "ssh"} <= set(names)

    def test_a_registered_backend_is_constructed(self):
        """A newly registered backend is built by create_sandbox (no core edit)."""
        from gimle.hugin.sandbox import sandbox as sandbox_mod
        from gimle.hugin.sandbox.sandbox import register_backend

        built = {}

        class _Toy:
            def __init__(self, spec, session_id, workspace_root):
                built["ok"] = (spec.backend, session_id)

        register_backend("toytest", lambda: _Toy)
        try:
            create_sandbox(SandboxSpec(backend="toytest"), "s", "/tmp/x")
            assert built["ok"] == ("toytest", "s")
        finally:
            sandbox_mod._BACKENDS.pop("toytest", None)

    def test_from_dict_validates_against_the_registry(self):
        """SandboxSpec.from_dict rejects a backend the registry doesn't know."""
        with pytest.raises(ValueError, match="invalid backend"):
            SandboxSpec.from_dict({"backend": "nope"})


class TestSandboxRoot:
    """The sandbox root is derived from the session's storage base path."""

    def test_default_root_when_no_storage_base(self):
        """No storage path (in-memory) falls back to the default root."""
        from gimle.hugin.sandbox.sandbox import (
            DEFAULT_SANDBOX_ROOT,
            sandbox_root_for,
        )

        assert sandbox_root_for(None) == DEFAULT_SANDBOX_ROOT

    def test_root_is_beside_a_custom_storage_base(self):
        """A custom storage base puts sandboxes under <base>/sandboxes."""
        from gimle.hugin.sandbox.sandbox import sandbox_root_for

        assert sandbox_root_for("/tmp/run7") == "/tmp/run7/sandboxes"


class TestSandboxManager:
    """Lazy lifecycle around a single backend."""

    def test_get_starts_the_injected_sandbox(self):
        """get() returns and starts the injected backend."""
        fake = FakeSandbox()
        manager = SandboxManager(LOCAL, "s", sandbox=fake)
        assert manager.get() is fake
        assert fake.started

    def test_close_stops_the_sandbox(self):
        """close() stops the backend."""
        fake = FakeSandbox()
        manager = SandboxManager(LOCAL, "s", sandbox=fake)
        manager.get()
        manager.close()
        assert fake.stopped

    def test_close_is_safe_when_never_started(self):
        """close() on an unused manager does nothing and does not raise."""
        SandboxManager(LOCAL, "s").close()

    def test_lazily_creates_a_backend_when_none_injected(self, tmp_path):
        """Without an injected backend, get() builds one from the spec."""
        manager = SandboxManager(LOCAL, "s", workspace_root=str(tmp_path))
        assert isinstance(manager.get(), LocalSandbox)


class TestLifecycleCounters:
    """The manager tallies backend starts and start-failures."""

    def test_start_is_counted_once(self, tmp_path):
        """Creating a backend counts one start; a re-get() does not add more."""
        manager = SandboxManager(LOCAL, "s", workspace_root=str(tmp_path))
        manager.get()
        manager.get()
        assert manager.audit.counters["sandbox_starts"] == 1
        assert manager.audit.counters["sandbox_start_failures"] == 0

    def test_start_failure_is_counted_and_reraised(self):
        """A backend that fails to start counts a failure and propagates."""
        from gimle.hugin.sandbox import sandbox as sandbox_mod
        from gimle.hugin.sandbox.sandbox import register_backend

        class _Boom:
            def __init__(self, spec, session_id, workspace_root):
                pass

            def start(self):
                raise RuntimeError("cannot start")

        register_backend("boomtest", lambda: _Boom)
        try:
            manager = SandboxManager(SandboxSpec(backend="boomtest"), "s")
            with pytest.raises(RuntimeError, match="cannot start"):
                manager.get()
            assert manager.audit.counters["sandbox_start_failures"] == 1
            assert manager.audit.counters["sandbox_starts"] == 0
        finally:
            sandbox_mod._BACKENDS.pop("boomtest", None)
