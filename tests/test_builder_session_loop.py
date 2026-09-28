"""Exercise builder delegation through the real CLI and interaction loop."""

from typing import Any

import pytest

from gimle.hugin.cli import create_agent
from gimle.hugin.interaction.agent_result import AgentResult
from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.interaction.task_result import TaskResult
from gimle.hugin.interaction.tool_result import ToolResult


def test_create_runs_child_and_returns_result(
    builder_cli_run: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """Complete all four build stages and return the child's result."""
    run = builder_cli_run

    assert create_agent.main(run.args) == 0

    parent, child = run.session.agents
    child_result = next(
        item
        for item in child.stack.interactions
        if isinstance(item, TaskResult)
    )
    assert child_result.finish_type == "success"
    assert child_result.result["result"] == "Hello from the generated child"
    assert any(
        isinstance(item, AgentResult) and item.task_result_id == child_result.id
        for item in parent.stack.interactions
    )
    assert "Hello from the generated child" in str(run.messages[-1])
    assert [
        item.task.name
        for item in parent.stack.interactions
        if isinstance(item, TaskDefinition)
    ] == ["build_agent", "review_agent", "finalize_agent", "test_agent"]
    assert any(
        isinstance(item, TaskResult)
        and item.result["result"] == "Child test reviewed"
        for item in parent.stack.interactions
    )
    assert 0 < run.steps < 200
    assert run.error is None
    assert run.closed
    assert (run.output / "configs" / "demo.yaml").is_file()
    assert "maximum session steps" not in capsys.readouterr().out.lower()


@pytest.mark.parametrize("child_finished", [False, True])
def test_create_reports_capped_session_work(
    builder_cli_run: Any,
    capsys: pytest.CaptureFixture[str],
    child_finished: bool,
) -> None:
    """Preserve written files without assuming the child test is unfinished."""
    run = builder_cli_run
    # preview_files is available to the builder; save_text to the child.
    # Repeat useful tool calls rather than finishing, to genuinely hit the cap.
    if child_finished:
        run.builder_script[-1] = {"tool": "preview_files", "input": {}}
    else:
        run.child_script[:] = [
            {
                "tool": "save_text",
                "input": {"content": "Still working", "format": "plain"},
            }
        ]

    assert create_agent.main(run.args + ["--max-steps", "80"]) == 0

    child = run.session.agents[1]
    assert (
        any(isinstance(item, TaskResult) for item in child.stack.interactions)
        == child_finished
    )
    results = [
        item
        for item in child.stack.interactions
        if isinstance(item, ToolResult)
    ]
    assert results
    assert not any(item.is_error for item in results)
    assert run.steps == 80
    assert run.error is None
    assert run.closed
    assert (run.output / "configs" / "demo.yaml").is_file()
    output = capsys.readouterr().out
    assert "session steps (80)" in output
    assert "builder session did not finish" in output
    assert "test run after it did not" not in output


def test_create_reports_child_exception_and_closes_session(
    builder_cli_run: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Surface child execution failures through the existing CLI error path."""
    run = builder_cli_run

    def fail_completion(*args: Any, **kwargs: Any) -> None:
        """Simulate a provider error in the generated child's test run."""
        raise RuntimeError("child model unavailable")

    monkeypatch.setattr(run.child, "chat_completion", fail_completion)

    assert create_agent.main(run.args) == 1
    assert isinstance(run.error, RuntimeError)
    assert run.closed
    assert "child model unavailable" in capsys.readouterr().out


def test_create_cap_before_write_is_failure(
    builder_cli_run: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """Keep a genuinely exhausted pre-write budget a failed build."""
    run = builder_cli_run

    assert create_agent.main(run.args + ["--max-steps", "1"]) == 1
    assert run.steps == 1
    assert run.closed
    assert not run.output.exists()
    assert "maximum session steps (1)" in capsys.readouterr().out


def test_improve_advances_delegated_child(improve_cli_run: Any) -> None:
    """Keep improve capable of running child agents through the same loop."""
    from gimle.hugin.cli import improve_agent

    run = improve_cli_run

    assert improve_agent.main(run.args) == 0

    parent, child = run.session.agents
    result = next(
        item
        for item in child.stack.interactions
        if isinstance(item, TaskResult)
    )
    assert result.finish_type == "success"
    assert any(
        isinstance(item, AgentResult) and item.task_result_id == result.id
        for item in parent.stack.interactions
    )
    assert "Hello from the generated child" in str(run.messages[-1])
    assert run.steps < 80
    assert run.error is None
    assert run.closed
