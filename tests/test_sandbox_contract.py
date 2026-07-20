"""One behaviour contract, run against every backend it can reach.

The bash sandbox ships three backends (``local`` / ``docker`` / ``ssh``) whose
whole promise is that they are *interchangeable* — "the runtime you choose is the
boundary; the config doesn't otherwise change." Each backend has its own unit
tests, but only a single suite parametrized over all three proves that promise:
identical agent-visible behaviour regardless of which runtime is underneath.

Gating: ``local`` always runs (no runtime to miss). ``docker`` and ``ssh`` are
``slow``-marked and skip when their runtime is absent (a reachable daemon /
``HUGIN_SSH_TEST_HOST``), so the default suite stays green everywhere while the
real backends are exercised wherever a runtime exists.

The containment half of the story lives in :class:`TestContainmentContract`,
parametrized over the *isolating* backends only — because ``local`` deliberately
does not contain (it says so), that is the one behaviour that legitimately
differs and so is not part of the interchangeable contract.
"""

from types import SimpleNamespace

import pytest

from gimle.hugin.sandbox import create_sandbox
from gimle.hugin.sandbox.policy import Policy
from gimle.hugin.sandbox.sandbox import PolicyDenied

from .sandbox_backends import ALL_BACKENDS, ISOLATING_BACKENDS, spec_for

# Every test starts a real sandbox and runs real commands (local always;
# docker/ssh when present), so the whole module is integration, not unit. The
# docker/ssh params additionally carry `slow` (see sandbox_backends), so
# `-m "not slow"` narrows to the always-available local backend.
pytestmark = pytest.mark.integration


def _started_backend(name: str, tmp_path):
    """Start a backend rooted under ``tmp_path``; yield it and always tear down.

    Written as a generator so the two fixtures below share start/stop. Teardown
    is reliable: when pytest closes the fixture generator, ``GeneratorExit``
    propagates through ``yield from`` into the ``yield`` here and the ``finally``
    runs ``stop()``. ``start()`` is intentionally before the ``try`` — if it
    raises there is nothing to stop.
    """
    spec = spec_for(name)
    sandbox = create_sandbox(spec, f"contract-{name}-sess", str(tmp_path))
    sandbox.start()
    try:
        yield SimpleNamespace(box=sandbox, name=name)
    finally:
        sandbox.stop()


def _has_python3(box, cwd) -> bool:
    """Return whether ``python3`` is on PATH inside this backend.

    A minimal ssh box may ship only bash + coreutils (its documented baseline),
    so tests that genuinely need an interpreter probe first and skip rather than
    fail with a misleading "truncation broke" message.
    """
    probe = box.exec(
        "command -v python3 || true", policy=Policy(), cwd=cwd, timeout_s=15
    )
    return "python3" in probe.stdout


@pytest.fixture(params=ALL_BACKENDS)
def backend(request, tmp_path):
    """Yield a started sandbox for each reachable runtime (local always)."""
    yield from _started_backend(request.param, tmp_path)


@pytest.fixture(params=ISOLATING_BACKENDS)
def isolating_backend(request, tmp_path):
    """Yield a started sandbox for the isolating backends only (docker/ssh)."""
    yield from _started_backend(request.param, tmp_path)


class TestBackendContract:
    """Agent-visible behaviour that must be identical on every backend."""

    def test_command_runs_and_returns_stdout(self, backend):
        """A plain command runs and its stdout comes back."""
        cwd = backend.box.workspace_for("a", None)
        result = backend.box.exec(
            "echo hello-contract", policy=Policy(), cwd=cwd, timeout_s=15
        )
        assert result.exit_code == 0
        assert result.stdout.strip() == "hello-contract"

    def test_nonzero_exit_is_data_not_an_error(self, backend):
        """A non-zero exit is reported as data (no raise), preserving the code."""
        cwd = backend.box.workspace_for("a", None)
        result = backend.box.exec(
            "exit 7", policy=Policy(), cwd=cwd, timeout_s=15
        )
        assert result.exit_code == 7
        assert result.timed_out is False

    def test_wallclock_overrun_is_timed_out_not_raised(self, backend):
        """A command past its timeout is flagged timed_out, not raised."""
        cwd = backend.box.workspace_for("a", None)
        result = backend.box.exec(
            "sleep 5", policy=Policy(), cwd=cwd, timeout_s=1
        )
        assert result.timed_out is True

    def test_output_truncation_spills_the_full_output(self, backend):
        """Oversized output truncates the returned view AND spills the full text.

        Uses only coreutils (no interpreter) so it runs on a minimal remote box.
        Two things must both hold: the view the model receives is actually
        shortened (not merely flagged), and the whole output is recoverable from
        the spill file.
        """
        cwd = backend.box.workspace_for("a", None)
        result = backend.box.exec(
            "head -c 500 /dev/zero | tr '\\0' 'x'",
            policy=Policy(),
            cwd=cwd,
            timeout_s=15,
            max_output_bytes=200,
        )
        assert result.truncated is True
        # The returned view is genuinely shortened, not just flagged — a backend
        # that set the flag but returned all 500 bytes would flood the context.
        assert "x" * 300 not in result.stdout
        # The result names exactly where the full output was spilled, and that
        # path is usable as-is (absolute, so it reads from any cwd).
        assert result.spill_path is not None
        spilled = backend.box.exec(
            f"cat {result.spill_path}",
            policy=Policy(),
            cwd=cwd,
            timeout_s=15,
        )
        # ...and the spill holds the full output the view dropped.
        assert "x" * 300 in spilled.stdout

    def test_workspaces_are_isolated_per_agent(self, backend):
        """Two (agent, branch) pairs get distinct, non-leaking workspaces."""
        cwd_a = backend.box.workspace_for("agent-a", "main")
        cwd_b = backend.box.workspace_for("agent-b", "main")
        assert cwd_a != cwd_b
        backend.box.exec(
            "echo secret-a > marker.txt",
            policy=Policy(),
            cwd=cwd_a,
            timeout_s=15,
        )
        seen = backend.box.exec(
            "cat marker.txt", policy=Policy(), cwd=cwd_b, timeout_s=15
        )
        assert seen.exit_code != 0
        assert "secret-a" not in seen.stdout
        # ...but the file persists in its own workspace.
        own = backend.box.exec(
            "cat marker.txt", policy=Policy(), cwd=cwd_a, timeout_s=15
        )
        assert own.stdout.strip() == "secret-a"

    def test_policy_denies_a_command_without_running_it(self, backend):
        """A denylisted command raises PolicyDenied and never reaches the runtime."""
        cwd = backend.box.workspace_for("a", None)
        with pytest.raises(PolicyDenied):
            backend.box.exec(
                "dd if=/dev/zero of=/dev/sda",
                policy=Policy(),
                cwd=cwd,
                timeout_s=15,
            )

    def test_interpreter_is_not_denied_by_policy(self, backend):
        """An interpreter that a naive allowlist would fear runs on every backend.

        The thesis: the policy is a seatbelt against accidents, not the boundary.
        ``os.system`` inside python is not refused — the runtime, not the policy,
        is what actually contains it (asserted in TestContainmentContract). Skips
        on a backend without python3 (a minimal remote box), where the thesis
        can't be shown with this particular interpreter.
        """
        cwd = backend.box.workspace_for("a", None)
        if not _has_python3(backend.box, cwd):
            pytest.skip(f"no python3 on the {backend.name} backend")
        result = backend.box.exec(
            "python3 -c 'import os; os.system(\"id\")'",
            policy=Policy(),
            cwd=cwd,
            timeout_s=15,
        )
        assert result.exit_code == 0, f"interpreter refused on {backend.name}"
        assert "uid=" in result.stdout

    def test_put_get_roundtrip_and_confinement(self, backend):
        """put_file/get_file round-trip bytes; a traversal path is refused."""
        backend.box.workspace_for("a", None)  # ensure the root exists
        backend.box.put_file("note.txt", b"payload-bytes")
        assert backend.box.get_file("note.txt") == b"payload-bytes"
        with pytest.raises(PolicyDenied):
            backend.box.get_file("../../../etc/passwd")


class TestContainmentContract:
    """The isolating backends actually contain — the one thing local does not."""

    def test_host_filesystem_outside_the_workspace_is_unreachable(
        self, isolating_backend, tmp_path
    ):
        """A secret outside the workspace cannot be read from inside the sandbox.

        For docker it is simply not bind-mounted; for ssh the command runs on the
        remote box, which cannot see this machine's filesystem at all. Either way
        the boundary holds — and this is exactly what the ``local`` backend can't
        promise, so it is not in the shared contract.
        """
        secret = tmp_path / "host_secret.txt"
        secret.write_text("TOP-SECRET-CONTRACT")
        cwd = isolating_backend.box.workspace_for("a", None)
        result = isolating_backend.box.exec(
            f"cat {secret}", policy=Policy(), cwd=cwd, timeout_s=15
        )
        assert result.exit_code != 0
        assert "TOP-SECRET-CONTRACT" not in result.stdout
