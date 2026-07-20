"""Tests for the ``builtins.bash`` tool, driven against a FakeSandbox.

These pin the agent-facing behaviour: how a result maps to a ToolResponse
(only denial/timeout/infra are errors — a non-zero exit is not), that policy is
read from ``config.options['bash']`` and enforced before the sandbox runs, and
that the command reaches the backend with the right cwd and policy.
"""

import os
from types import SimpleNamespace

from gimle.hugin.sandbox.fake import FakeSandbox
from gimle.hugin.sandbox.manager import SandboxManager
from gimle.hugin.sandbox.sandbox import ExecResult, SandboxSpec
from gimle.hugin.tools.builtins.bash import bash

LOCAL = SandboxSpec(backend="local")


def _stack(config_options=None, sandbox_manager=None, interactive=False):
    """Build a minimal stack exposing just what the bash tool reads.

    When a ``sandbox_manager`` is pre-seeded, the config is given
    ``backend: local`` so the tool resolves the same LOCAL spec the manager is
    keyed by in ``session.sandboxes``. ``interactive`` sets ``config.interactive``
    (whether an escalation can ask a human).
    """
    opts = dict(config_options or {})
    sandboxes = {}
    if sandbox_manager is not None:
        bash_opts = dict(opts.get("bash", {}))
        bash_opts.setdefault("backend", "local")
        opts["bash"] = bash_opts
        sandboxes[LOCAL] = sandbox_manager
    environment = SimpleNamespace(env_vars={})
    session = SimpleNamespace(id="session-1", sandboxes=sandboxes)
    config = SimpleNamespace(options=opts, interactive=interactive)
    agent = SimpleNamespace(
        id="agent-a",
        config=config,
        session=session,
        environment=environment,
    )
    return SimpleNamespace(agent=agent)


def _stack_with_fake(fake, config_options=None, interactive=False):
    """Build a stack whose session owns a manager wrapping ``fake``."""
    manager = SandboxManager(LOCAL, "session-1", sandbox=fake)
    return _stack(
        config_options=config_options,
        sandbox_manager=manager,
        interactive=interactive,
    )


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

    def test_backend_that_fails_to_start_is_a_clean_dont_retry_error(self):
        """A start() failure (any exception) comes back as an actionable result.

        Regression guard: docker's start() raises RuntimeError/DockerException/
        ImageNotFound, none of which are ValueError/NotImplementedError; a
        too-narrow handler would let them escape the tool entirely instead of
        reaching the model.
        """
        fake = FakeSandbox(
            raises_on_start=RuntimeError("Cannot connect to the Docker daemon")
        )
        response = bash("echo hi", stack=_stack_with_fake(fake))
        assert response.is_error is True
        assert "Docker daemon" in response.content["infra_error"]
        assert "operator" in response.content["note"]

    def test_oom_kill_is_an_error(self):
        """An OOM-killed command is an error, like a timeout — not a plain exit."""
        fake = FakeSandbox(
            ExecResult(
                exit_code=-9,
                stdout="partial",
                stderr="",
                duration_s=0.2,
                oom_killed=True,
            )
        )
        response = bash("./hog", stack=_stack_with_fake(fake))
        assert response.is_error is True
        assert response.content["oom_killed"] is True

    def test_truncated_output_carries_the_spill_path(self):
        """When output is truncated, the response tells the model where to read."""
        fake = FakeSandbox(
            ExecResult(
                exit_code=0,
                stdout="tail",
                stderr="",
                duration_s=0.1,
                truncated=True,
            )
        )
        response = bash("cat big", stack=_stack_with_fake(fake))
        assert response.content["full_output"] == ".hugin/last_output.txt"

    def test_timeout_argument_is_passed_to_exec(self):
        """A caller-supplied timeout_s reaches the sandbox exec."""
        fake = FakeSandbox(
            ExecResult(exit_code=0, stdout="", stderr="", duration_s=0.1)
        )
        bash("make", timeout_s=120, stack=_stack_with_fake(fake))
        assert fake.last_call.timeout_s == 120


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

    def test_escalate_denies_in_a_non_interactive_session(self):
        """ask_human with no human (config.interactive False) is a clean deny."""
        fake = FakeSandbox()
        options = {"bash": {"policy": {"on_violation": "ask_human"}}}
        response = bash("shutdown now", stack=_stack_with_fake(fake, options))
        assert response.is_error is True
        assert "denied" in response.content
        assert "non-interactive" in response.content["note"]
        assert fake.calls == []  # never ran

    def test_escalate_defers_to_a_human_when_interactive(self):
        """ask_human in an interactive session parks on a BashApproval."""
        from gimle.hugin.interaction.bash_approval import BashApproval

        fake = FakeSandbox()
        options = {"bash": {"policy": {"on_violation": "ask_human"}}}
        response = bash(
            "shutdown now",
            stack=_stack_with_fake(fake, options, interactive=True),
        )
        assert response.is_error is False
        assert isinstance(response.response_interaction, BashApproval)
        assert response.response_interaction.command == "shutdown now"
        assert fake.calls == []  # not run until approved

    def test_malformed_policy_config_is_reported(self):
        """A bad policy block is a clear config error, not a silent default."""
        fake = FakeSandbox()
        options = {"bash": {"policy": {"modee": "allowlist"}}}
        response = bash("echo hi", stack=_stack_with_fake(fake, options))
        assert response.is_error is True
        assert "invalid bash policy config" in response.content["error"]

    def test_unparseable_command_is_surfaced_distinctly(self):
        """A parser limitation is reported as 'unparseable', not 'denied'.

        The model must not mistake "the guard's parser choked" for a policy
        refusal, or it will try other (also-unparseable) syntax instead of
        rephrasing.
        """
        fake = FakeSandbox()
        response = bash("ls '", stack=_stack_with_fake(fake))  # bad quoting
        assert response.is_error is True
        assert "unparseable" in response.content
        assert "denied" not in response.content
        assert "hint" in response.content
        assert fake.calls == []

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

    def test_audit_root_follows_session_storage(self, tmp_path):
        """A built manager writes its audit under <storage-base>/sandboxes.

        The tool derives the sandbox root from the session's storage, so a
        custom storage path keeps sandboxes (and their audit) beside its
        sessions rather than in a fixed ./storage/sandboxes.
        """
        storage = SimpleNamespace(base_path=tmp_path)
        environment = SimpleNamespace(env_vars={}, storage=storage)
        session = SimpleNamespace(
            id="sess-x", sandboxes={}, environment=environment
        )
        config = SimpleNamespace(options={"bash": {"backend": "local"}})
        agent = SimpleNamespace(
            id="agent-a",
            config=config,
            session=session,
            environment=environment,
        )
        stack = SimpleNamespace(agent=agent)

        bash("dd if=/dev/zero of=/dev/sda", stack=stack)  # denied -> audited

        audit = tmp_path / "sandboxes" / "sess-x" / ".hugin" / "audit.jsonl"
        assert audit.is_file()

    def test_denied_first_command_is_audited_without_preseeded_manager(self):
        """A denial is recorded even when no backend has been built yet.

        The audit is resolved before the policy check, so a session whose very
        first command is denied still counts it (previously dropped, because the
        manager — and its audit — was only built on the allow path).
        """
        import shutil

        stack = _stack(config_options={"bash": {"backend": "local"}})
        try:
            response = bash("dd if=/dev/zero of=/dev/sda", stack=stack)
            assert response.is_error is True
            assert "denied" in response.content
            manager = stack.agent.session.sandboxes[LOCAL]
            assert manager.audit.counters["denied"] == 1
        finally:  # the tool builds a real (unstarted) manager under ./storage
            shutil.rmtree(
                os.path.join("./storage/sandboxes", "session-1"),
                ignore_errors=True,
            )


class TestPerSpecOwnership:
    """A session owns one backend per spec — call order doesn't decide isolation."""

    def test_agents_with_different_specs_use_their_own_backend(self):
        """Agent B's command runs in B's backend, not whichever agent ran first.

        Under the old single-sandbox model, the first agent to run bash fixed
        the backend for the whole session, silently downgrading a later agent's
        isolation. Here each distinct spec gets its own manager.
        """
        spec_a = SandboxSpec(backend="local")
        spec_b = SandboxSpec(backend="local", network=True)  # a different spec
        fake_a = FakeSandbox(
            ExecResult(exit_code=0, stdout="A", stderr="", duration_s=0.1)
        )
        fake_b = FakeSandbox(
            ExecResult(exit_code=0, stdout="B", stderr="", duration_s=0.1)
        )
        session = SimpleNamespace(
            id="session-1",
            sandboxes={
                spec_a: SandboxManager(spec_a, "session-1", sandbox=fake_a),
                spec_b: SandboxManager(spec_b, "session-1", sandbox=fake_b),
            },
        )

        def _agent_stack(agent_id, bash_opts):
            config = SimpleNamespace(options={"bash": bash_opts})
            agent = SimpleNamespace(
                id=agent_id,
                config=config,
                session=session,
                environment=SimpleNamespace(env_vars={}),
            )
            return SimpleNamespace(agent=agent)

        stack_a = _agent_stack("agent-a", {"backend": "local"})
        stack_b = _agent_stack("agent-b", {"backend": "local", "network": True})

        # Agent A runs first (would have fixed the backend under the old model).
        result_a = bash("echo hi", stack=stack_a)
        result_b = bash("echo hi", stack=stack_b)

        assert result_a.content["stdout"] == "A"
        assert result_b.content["stdout"] == "B"  # B's own backend, not A's

    def test_same_spec_shares_one_backend(self):
        """Two agents with the same spec share the one manager (and container)."""
        fake = FakeSandbox(
            ExecResult(exit_code=0, stdout="", stderr="", duration_s=0.1)
        )
        spec = SandboxSpec(backend="local")
        session = SimpleNamespace(
            id="session-1",
            sandboxes={spec: SandboxManager(spec, "session-1", sandbox=fake)},
        )

        def _agent_stack(agent_id):
            config = SimpleNamespace(options={"bash": {"backend": "local"}})
            agent = SimpleNamespace(
                id=agent_id,
                config=config,
                session=session,
                environment=SimpleNamespace(env_vars={}),
            )
            return SimpleNamespace(agent=agent)

        bash("echo hi", stack=_agent_stack("agent-a"))
        bash("echo hi", stack=_agent_stack("agent-b"))

        assert len(session.sandboxes) == 1  # one shared backend, two agents


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


class TestEnvironmentAffordance:
    """The first successful bash use per agent carries a one-time env note."""

    def test_first_use_announces_environment_then_stops(self):
        """The first result carries an `environment` note; the second does not."""
        fake = FakeSandbox(
            ExecResult(exit_code=0, stdout="hi", stderr="", duration_s=0.0)
        )
        manager = SandboxManager(LOCAL, "session-1", sandbox=fake)
        stack = _stack(sandbox_manager=manager)

        first = bash("echo hi", stack=stack)
        assert "environment" in first.content
        env = first.content["environment"]
        assert env["backend"] == "local"
        assert "network" in env
        assert env["workspace"].startswith("/workspace/agents/agent-a")

        second = bash("echo again", stack=stack)
        assert "environment" not in second.content

    def test_error_result_does_not_carry_or_consume_the_note(self):
        """An infra_error first result gets no note (and doesn't consume it)."""
        fake = FakeSandbox(raises=RuntimeError("daemon down"))
        manager = SandboxManager(LOCAL, "session-1", sandbox=fake)
        first = bash("echo hi", stack=_stack(sandbox_manager=manager))
        assert first.is_error is True
        assert "environment" not in first.content
        assert manager.announce_once("agent-a") is True  # still un-announced

    def test_network_note_is_rendered_from_the_spec(self):
        """The network line is derived from the spec (no probe, never drifts)."""
        from gimle.hugin.tools.builtins.bash import _environment_note

        ws = "/workspace/agents/a/default"
        local = _environment_note(SandboxSpec(backend="local"), ws)["network"]
        assert "host network" in local

        off = _environment_note(SandboxSpec(backend="docker"), ws)["network"]
        assert "OFF" in off

        filtered = _environment_note(
            SandboxSpec(
                backend="docker", network=True, egress_allowlist=("pypi.org",)
            ),
            ws,
        )["network"]
        assert "filtered" in filtered and "pypi.org" in filtered

        unrestricted = _environment_note(
            SandboxSpec(
                backend="docker", network=True, allow_unrestricted_egress=True
            ),
            ws,
        )["network"]
        assert "unrestricted" in unrestricted

        remote = _environment_note(SandboxSpec(backend="ssh", host="h"), ws)[
            "network"
        ]
        assert "remote host" in remote
