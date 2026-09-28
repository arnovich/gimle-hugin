"""Guard the golden release pipeline's runtime parameter hand-off."""

from typing import Any

from gimle.hugin.interaction.task_definition import TaskDefinition
from gimle.hugin.interaction.task_result import TaskResult


def test_release_version_reaches_second_stage(
    versioned_release_pipeline: Any,
) -> None:
    """Require the exact input in stage two without embedding it in stage one's result."""
    run = versioned_release_pipeline
    assert run.case.expect_tasks == 2
    assert run.session.run(max_steps=50) < 50
    assert len(run.prompts) == 2
    assert "Release version: 0.3.0" in str(run.prompts[1]["content"])
    stages = [
        item
        for item in run.session.agents[0].stack.interactions
        if isinstance(item, TaskDefinition)
    ]
    assert stages[1].task.parameters["version"]["value"] == "0.3.0"
    results = [
        item
        for item in run.session.agents[0].stack.interactions
        if isinstance(item, TaskResult)
    ]
    assert len(results) == 2
    assert "0.3.0" not in str(results[0].result)
    assert results[1].finish_type == "success"
