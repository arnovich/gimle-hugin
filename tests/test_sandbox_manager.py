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

    def test_from_dict_hints_at_misplaced_policy_keys(self):
        """A Policy key at the top level suggests nesting under policy:."""
        with pytest.raises(ValueError, match="options.bash.policy"):
            SandboxSpec.from_dict(
                {"backend": "local", "deny": ["rm"], "timeout_s": 30}
            )

    def test_from_dict_rejects_a_truly_unknown_key_without_the_hint(self):
        """A key that isn't a Policy field errors plainly, with no policy hint."""
        with pytest.raises(ValueError, match="unknown sandbox keys") as excinfo:
            SandboxSpec.from_dict({"backend": "local", "wibble": 1})
        assert "options.bash.policy" not in str(excinfo.value)


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

    def test_restart_failure_is_not_a_start_failure(self):
        """A re-start() failure on an already-created backend isn't miscounted.

        ``sandbox_start_failures`` is for *bringing a backend up*; a later
        idempotent re-start raising is a different class (the caller records it
        as ``infra_error``) and must not inflate the start-failure rate.
        """

        class _FailsOnRestart(FakeSandbox):
            def __init__(self) -> None:
                super().__init__()
                self._starts = 0

            def start(self) -> None:
                self._starts += 1
                if self._starts > 1:
                    raise RuntimeError("restart boom")
                super().start()

        manager = SandboxManager(LOCAL, "s", sandbox=_FailsOnRestart())
        manager.get()  # first start succeeds
        with pytest.raises(RuntimeError, match="restart boom"):
            manager.get()  # the idempotent re-start raises
        assert manager.audit.counters["sandbox_start_failures"] == 0


class TestAuditSummaryLogging:
    """log_summary emits counters at teardown, escalating on failing outcomes."""

    def test_logs_an_info_summary(self, caplog, tmp_path):
        """A used sandbox logs an INFO line naming the session and outcomes."""
        manager = SandboxManager(LOCAL, "sess-x", workspace_root=str(tmp_path))
        manager.audit.record(
            session_id="sess-x", agent_id="a", command="ls", outcome="run"
        )
        with caplog.at_level("INFO"):
            manager.log_summary()
        assert any(
            "bash sandbox audit" in r.getMessage()
            and "sess-x" in r.getMessage()
            for r in caplog.records
        )

    def test_warns_on_failing_outcomes(self, caplog, tmp_path):
        """A denied/timed-out/infra-error outcome escalates to a WARNING."""
        manager = SandboxManager(LOCAL, "s", workspace_root=str(tmp_path))
        manager.audit.record(
            session_id="s", agent_id="a", command="rm /", outcome="denied"
        )
        with caplog.at_level("WARNING"):
            manager.log_summary()
        assert any(
            r.levelname == "WARNING" and "failing outcomes" in r.getMessage()
            for r in caplog.records
        )

    def test_a_clean_session_does_not_warn(self, caplog, tmp_path):
        """Only successful outcomes: an INFO line but no WARNING."""
        manager = SandboxManager(LOCAL, "s", workspace_root=str(tmp_path))
        manager.audit.record(
            session_id="s", agent_id="a", command="ls", outcome="run"
        )
        with caplog.at_level("INFO"):
            manager.log_summary()
        assert not any(r.levelname == "WARNING" for r in caplog.records)

    def test_unused_sandbox_logs_nothing(self, caplog, tmp_path):
        """A sandbox with no recorded outcomes logs no audit line."""
        manager = SandboxManager(LOCAL, "s", workspace_root=str(tmp_path))
        with caplog.at_level("INFO"):
            manager.log_summary()
        assert not any(
            "bash sandbox audit" in r.getMessage() for r in caplog.records
        )


class TestConcurrentGet:
    """First-creation is serialized: concurrent callers share one backend."""

    def test_concurrent_get_creates_exactly_one_backend(self):
        """8 threads racing get() build the backend once and all get that one."""
        import threading
        import time as _time

        from gimle.hugin.sandbox import sandbox as sandbox_mod
        from gimle.hugin.sandbox.sandbox import register_backend

        built = []

        class _Slow:
            def __init__(self, spec, session_id, workspace_root):
                built.append(1)
                _time.sleep(0.05)  # widen the check-then-act race window

            def start(self):
                """No-op start."""

        register_backend("slowtest", lambda: _Slow)
        try:
            manager = SandboxManager(SandboxSpec(backend="slowtest"), "s")
            results: list = []
            threads = [
                threading.Thread(target=lambda: results.append(manager.get()))
                for _ in range(8)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            assert len(built) == 1  # created once despite 8 concurrent callers
            assert all(r is results[0] for r in results)  # all share the one
            assert manager.audit.counters["sandbox_starts"] == 1
        finally:
            sandbox_mod._BACKENDS.pop("slowtest", None)
