"""Human escalation: an out-of-policy bash command asks, then runs or refuses.

`on_violation: ask_human` escalates an out-of-policy command to a human. In an
interactive session the command parks on a `BashApproval`; approving runs THAT
exact command (never a durable "allow this binary") and returns its result,
denying refuses it. In a non-interactive session there is no human, so it
degrades to a clean deny rather than parking forever. These tests drive the real
Session/Agent loop with a scripted model and set the decision the way a human
(via the CLI) would, asserting the command runs only on approval.
"""

from types import SimpleNamespace

import gimle.hugin.tools  # noqa: F401  (registers bash)
from gimle.hugin.agent.environment import Environment
from gimle.hugin.agent.session import Session
from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.bash_approval import BashApproval
from gimle.hugin.llm.models.model_registry import get_model_registry
from gimle.hugin.sandbox.fake import FakeSandbox
from gimle.hugin.sandbox.manager import SandboxManager
from gimle.hugin.sandbox.sandbox import ExecResult, SandboxSpec
from gimle.hugin.storage.local import LocalStorage

from .conftest import ScriptedToolModel

LOCAL = SandboxSpec(backend="local")
ESCALATE = {"backend": "local", "policy": {"on_violation": "ask_human"}}


def _run_escalation(tmp_path, model_name, *, interactive, fake):
    """Drive an agent that runs an out-of-policy command; return the agent.

    Steps until it either parks on a BashApproval (interactive) or finishes
    (non-interactive deny). The caller sets the decision and steps on.
    """
    storage = LocalStorage(base_path=str(tmp_path / "storage"))
    env = Environment.load("examples/bash_agent", storage=storage)
    registry = get_model_registry()
    registry.register_model(
        model_name,
        ScriptedToolModel(
            model_name,
            [
                {"tool": "bash", "input": {"command": "shutdown now"}},
                {
                    "tool": "finish",
                    "input": {
                        "finish_type": "success",
                        "result": "done",
                        "reason": "done",
                    },
                },
            ],
        ),
    )
    session = Session(environment=env)
    config = env.config_registry.get("bash_agent")
    config.options["bash"] = ESCALATE
    config.interactive = interactive
    config.llm_model = model_name
    session.sandboxes[LOCAL] = SandboxManager(LOCAL, session.id, sandbox=fake)
    task = env.task_registry.get("explore")
    session.create_agent_from_task(config, task)
    agent = session.agents[0]
    return SimpleNamespace(session=session, agent=agent, name=model_name)


def _pending_approval(agent):
    """Return the parked BashApproval on the agent's stack, if any."""
    for interaction in agent.stack.interactions:
        if isinstance(interaction, BashApproval):
            return interaction
    return None


def _bash_tool_result(agent):
    """Return the resolved bash tool_result AskOracle, if present."""
    for interaction in agent.stack.interactions:
        if (
            isinstance(interaction, AskOracle)
            and interaction.prompt is not None
            and getattr(interaction.prompt, "type", None) == "tool_result"
            and (interaction.template_inputs or {}).get("command")
            == "shutdown now"
        ):
            return interaction
    return None


class TestHumanEscalation:
    """Escalate → ask → run/refuse, and the non-interactive degrade."""

    def test_approval_runs_the_exact_command(self, tmp_path):
        """An approved out-of-policy command runs and returns its result."""
        fake = FakeSandbox(
            ExecResult(exit_code=0, stdout="RAN-IT", stderr="", duration_s=0.0)
        )
        ctx = _run_escalation(
            tmp_path, "approve-run", interactive=True, fake=fake
        )
        try:
            for _ in range(6):
                ctx.agent.step()
                if _pending_approval(ctx.agent):
                    break
            approval = _pending_approval(ctx.agent)
            assert approval is not None, "did not park on approval"
            assert fake.calls == []  # not run yet

            approval.decision = "y"  # the human approves
            for _ in range(6):
                ctx.agent.step()

            assert [c.command for c in fake.calls] == ["shutdown now"]
            result = _bash_tool_result(ctx.agent)
            assert result is not None
            assert result.template_inputs.get("stdout") == "RAN-IT"
        finally:
            get_model_registry().models.pop(ctx.name, None)
            ctx.session.close()

    def test_denial_refuses_without_running(self, tmp_path):
        """A denied command never runs; the model gets a human-refusal result."""
        fake = FakeSandbox()
        ctx = _run_escalation(
            tmp_path, "deny-refuse", interactive=True, fake=fake
        )
        try:
            for _ in range(6):
                ctx.agent.step()
                if _pending_approval(ctx.agent):
                    break
            approval = _pending_approval(ctx.agent)
            assert approval is not None

            approval.decision = "n"  # the human denies
            for _ in range(6):
                ctx.agent.step()

            assert fake.calls == []  # never ran
            result = _bash_tool_result(ctx.agent)
            assert result is not None
            assert "denied by a human" in result.template_inputs.get(
                "denied", ""
            )
            assert result.template_inputs.get("is_error") is True
        finally:
            get_model_registry().models.pop(ctx.name, None)
            ctx.session.close()

    def test_non_interactive_degrades_to_deny(self, tmp_path):
        """With no human, an escalated command is denied, not parked."""
        fake = FakeSandbox()
        ctx = _run_escalation(
            tmp_path, "no-human", interactive=False, fake=fake
        )
        try:
            for _ in range(6):
                ctx.agent.step()
            # Never parks on an approval, and never runs the command.
            assert _pending_approval(ctx.agent) is None
            assert fake.calls == []
        finally:
            get_model_registry().models.pop(ctx.name, None)
            ctx.session.close()

    def test_model_cannot_self_approve_via_a_kwarg(self):
        """A model-supplied bypass kwarg cannot run an out-of-policy command.

        ``execute_tool`` passes a tool_call's args straight to the function, so
        the approval bypass must NOT be a bash parameter (a leading underscore
        does not protect a **kwargs-passed arg). It isn't — bash rejects the
        unknown kwarg (fails closed), and the out-of-policy command never runs.
        """
        import pytest

        from gimle.hugin.sandbox.manager import SandboxManager
        from gimle.hugin.tools.tool import Tool

        fake = FakeSandbox()
        manager = SandboxManager(LOCAL, "s", sandbox=fake)
        session = SimpleNamespace(id="s", sandboxes={LOCAL: manager})
        config = SimpleNamespace(options={"bash": ESCALATE}, interactive=False)
        stack = SimpleNamespace(
            agent=SimpleNamespace(
                id="a",
                config=config,
                session=session,
                environment=SimpleNamespace(env_vars={}),
            )
        )
        tool = Tool.get_tool("builtins.bash")
        with pytest.raises(TypeError):
            Tool.execute_tool(
                tool,
                stack=stack,
                branch=None,
                command="shutdown now",
                _approved=True,
            )
        assert fake.calls == []  # the out-of-policy command never ran

    def test_bash_has_no_approval_bypass_parameter(self):
        """Guard against re-introducing a model-settable approval bypass."""
        import inspect

        from gimle.hugin.tools.builtins.bash import bash

        params = inspect.signature(bash).parameters
        assert "_approved" not in params
        assert not any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
