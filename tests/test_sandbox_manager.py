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

    def test_docker_backend_not_yet_implemented(self):
        """backend='docker' is a clear NotImplementedError until phase 2."""
        with pytest.raises(NotImplementedError, match="phase 2"):
            create_sandbox(SandboxSpec(backend="docker"), "s")

    def test_ssh_backend_not_yet_implemented(self):
        """backend='ssh' is a clear NotImplementedError until phase 2."""
        with pytest.raises(NotImplementedError, match="phase 2"):
            create_sandbox(SandboxSpec(backend="ssh"), "s")


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
