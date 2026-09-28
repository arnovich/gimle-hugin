"""Keep declared inputs available and validated across task boundaries."""

from copy import deepcopy
from typing import Any

import pytest
import yaml

from gimle.hugin.agent.config import Config
from gimle.hugin.agent.task import Task
from gimle.hugin.apps.agent_builder.tools.validate_agent import validate_files
from gimle.hugin.interaction.stack import Stack
from gimle.hugin.interaction.task_chain import TaskChain
from gimle.hugin.interaction.task_definition import TaskDefinition


def _parameter(**fields: Any) -> dict[str, Any]:
    """Build a required string parameter, with explicit test overrides."""
    return {
        "type": "string",
        "description": "Test input",
        "required": True,
        **fields,
    }


def _task(name: str, **fields: Any) -> Task:
    """Build a task with only the fields relevant to the scenario."""
    return Task(name=name, description=name, prompt="Do the task.", **fields)


def _advance(
    stack: Stack,
    first: Task,
    second: Task,
    result: Any = None,
    branch: str | None = None,
) -> Task:
    """Run a real TaskChain with an already-completed predecessor."""
    stack.agent.environment.task_registry.register(second, name=second.name)
    stack.add_interaction(
        TaskDefinition(stack=stack, task=first, branch=branch)
    )
    chain = TaskChain(
        stack=stack,
        next_task_name=second.name,
        previous_result=result,
        branch=branch,
    )
    stack.add_interaction(chain)
    assert chain.step()
    return stack.interactions[-1].task


@pytest.mark.parametrize("value", ["0.3.0", "", False, 0, [], {}])
def test_inherit_declared_values_without_mutating_sources(
    mock_stack: Stack, value: Any
) -> None:
    """Carry even falsy values, using the receiving type and separate copies."""
    kind = {
        str: "string",
        bool: "boolean",
        int: "integer",
        list: "array",
        dict: "object",
    }[type(value)]
    first = _task(
        "first", parameters={"version": _parameter(type=kind, value=value)}
    )
    second = _task("second", parameters={"version": _parameter(type=kind)})
    before = deepcopy(second.to_dict())

    child = _advance(mock_stack, first, second)

    assert child.parameters["version"]["value"] == value
    assert second.to_dict() == before
    if isinstance(value, (dict, list)):
        assert child.parameters["version"]["value"] is not value


def test_inherited_input_overrides_successor_default(mock_stack: Stack) -> None:
    """Treat successor defaults as fallbacks to the caller's actual input."""
    child = _advance(
        mock_stack,
        _task("first", parameters={"version": _parameter(value="0.3.0")}),
        _task("second", parameters={"version": _parameter(default="unknown")}),
    )
    assert child.parameters["version"]["value"] == "0.3.0"


def test_none_uses_successor_default_and_drops_undeclared_inputs(
    mock_stack: Stack,
) -> None:
    """Keep defaults when no value arrives, without spreading other inputs."""
    child = _advance(
        mock_stack,
        _task(
            "first",
            parameters={
                "version": _parameter(required=False),
                "private": _parameter(value="local"),
            },
        ),
        _task("second", parameters={"version": _parameter(default="fallback")}),
    )
    assert child.parameters["version"]["value"] == "fallback"
    assert "private" not in child.parameters


@pytest.mark.parametrize("declared", [False, True])
@pytest.mark.parametrize("result", [{}, {"result": "done"}])
def test_result_injection_wins_and_preserves_raw_mapping(
    mock_stack: Stack, declared: bool, result: dict[str, Any]
) -> None:
    """Preserve result dictionaries, including empty ones and legacy schemas."""
    child = _advance(
        mock_stack,
        _task(
            "first",
            parameters={"payload": _parameter(value="old")},
            pass_result_as="payload",
        ),
        _task(
            "second",
            parameters=(
                {"payload": _parameter(default="default")} if declared else {}
            ),
        ),
        result,
    )
    assert child.parameters["payload"]["value"] == result
    assert isinstance(child.parameters["payload"]["value"], dict)
    assert child.parameters["payload"]["value"] is not result


def test_missing_required_value_fails_before_config_or_stack_change(
    mock_stack: Stack,
) -> None:
    """Reject an unsatisfied stage before it can prompt or alter the agent."""
    replacement = Config(
        name="replacement",
        description="Replacement",
        system_template="Replacement.",
    )
    mock_stack.agent.environment.config_registry.register(
        replacement, name="replacement"
    )
    original_config = mock_stack.agent.config
    with pytest.raises(ValueError, match="Missing required.*second"):
        _advance(
            mock_stack,
            _task("first"),
            _task(
                "second",
                parameters={"version": _parameter()},
                chain_config="replacement",
            ),
        )
    assert mock_stack.agent.config is original_config
    assert isinstance(mock_stack.interactions[-1], TaskChain)


def test_inherited_values_are_checked_against_receiving_schema(
    mock_stack: Stack,
) -> None:
    """Reject an upstream choice the successor does not accept."""
    with pytest.raises(ValueError, match="Invalid value for 'mode'"):
        _advance(
            mock_stack,
            _task("first", parameters={"mode": _parameter(value="unsafe")}),
            _task(
                "second",
                parameters={
                    "mode": _parameter(type="categorical", choices=["safe"])
                },
            ),
        )


def test_branch_inherits_its_own_task_inputs(mock_stack: Stack) -> None:
    """Do not copy the main branch's parameters into a sibling transition."""
    mock_stack.add_interaction(
        TaskDefinition(
            stack=mock_stack,
            task=_task(
                "main", parameters={"version": _parameter(value="main")}
            ),
        )
    )
    child = _advance(
        mock_stack,
        _task("branch", parameters={"version": _parameter(value="branch")}),
        _task("second", parameters={"version": _parameter()}),
        branch="explore",
    )
    assert child.parameters["version"]["value"] == "branch"


def _validate(*tasks: Task) -> list[dict[str, str]]:
    """Return chain-parameter findings from the full static validator."""
    files = {
        "configs/demo.yaml": "name: demo\ndescription: Demo\nsystem_template: Do the task.\ntools: [builtins.finish:finish]\n"
    }
    files.update(
        {
            f"tasks/{task.name}.yaml": yaml.safe_dump(task.to_dict())
            for task in tasks
        }
    )
    report = validate_files(files)
    return [
        item
        for item in report["errors"]
        if item["check"] == "task-chain-parameters"
    ]


def test_validator_rejects_unsourced_required_parameter() -> None:
    """Name the broken edge and missing input before the chain can run."""
    findings = _validate(
        _task("first", next_task="second"),
        _task("second", parameters={"version": _parameter()}),
    )
    assert findings
    assert all(
        word in findings[0]["message"]
        for word in ("first", "second", "version")
    )


@pytest.mark.parametrize(
    "source", ["declared", "default", "result", "optional"]
)
def test_validator_accepts_possible_sources(source: str) -> None:
    """Allow caller values, local defaults, immediate results and optional inputs."""
    first = _task("first", next_task="second")
    second = _task("second", parameters={"version": _parameter()})
    if source in ("declared", "optional"):
        first.parameters["version"] = _parameter(required=source == "declared")
    elif source == "default":
        second.parameters["version"]["default"] = "0.3.0"
    else:
        first.pass_result_as = "version"
    assert not _validate(first, second)


def test_validator_tracks_sequence_edges_and_intermediate_drops() -> None:
    """An entry's value cannot skip a stage that does not declare it."""
    first = _task(
        "first",
        parameters={"version": _parameter()},
        task_sequence=["middle", "last"],
    )
    middle = _task("middle")
    last = _task("last", parameters={"version": _parameter()})
    findings = _validate(first, middle, last)
    assert any(
        "middle" in item["message"] and "version" in item["message"]
        for item in findings
    )
    middle.parameters["version"] = _parameter()
    assert not _validate(first, middle, last)


def test_validator_tracks_undeclared_injected_result_into_next_stage() -> None:
    """An injected result can be inherited by a later declaration."""
    assert not _validate(
        _task(
            "first", task_sequence=["middle", "last"], pass_result_as="version"
        ),
        _task("middle", pass_result_as="other"),
        _task("last", parameters={"version": _parameter()}),
    )


def test_validator_does_not_borrow_another_predecessors_result() -> None:
    """Check each incoming path rather than pooling all possible injections."""
    findings = _validate(
        _task("good", next_task="middle", pass_result_as="version"),
        _task("bad", next_task="middle"),
        _task("middle", next_task="last"),
        _task("last", parameters={"version": _parameter()}),
    )
    assert findings


def test_validator_terminates_on_next_task_cycles() -> None:
    """Repeated valid states cannot keep static validation running forever."""
    assert not _validate(
        _task(
            "first", next_task="second", parameters={"version": _parameter()}
        ),
        _task(
            "second", next_task="first", parameters={"version": _parameter()}
        ),
    )


def test_restored_chain_keeps_inputs_and_converts_receiving_type(
    mock_stack: Stack,
) -> None:
    """Resume with persisted values and apply the next stage's conversion."""
    first = Task.from_dict(
        _task("first", parameters={"count": _parameter(value="12")}).to_dict()
    )
    second = _task("second", parameters={"count": _parameter(type="integer")})
    mock_stack.agent.environment.task_registry.register(
        second, name=second.name
    )
    mock_stack.add_interaction(TaskDefinition(stack=mock_stack, task=first))
    original = TaskChain(stack=mock_stack, next_task_name="second")
    restored = TaskChain._from_dict(
        original.to_dict()["data"], stack=mock_stack, artifacts=[]
    )
    assert restored.step()
    assert mock_stack.interactions[-1].task.parameters["count"]["value"] == 12


def test_task_result_selects_the_branchs_chain(mock_stack: Stack) -> None:
    """Launch a named branch's successor using that branch's own parameters."""
    from gimle.hugin.interaction.task_result import TaskResult

    for branch, name in ((None, "main"), ("explore", "side")):
        mock_stack.add_interaction(
            TaskDefinition(
                stack=mock_stack,
                branch=branch,
                task=_task(name, next_task=f"{name}_next"),
            )
        )
    result = TaskResult(
        stack=mock_stack,
        branch="explore",
        finish_type="success",
        result={"result": "done"},
    )
    mock_stack.add_interaction(result)
    assert result.step()
    chain = mock_stack.interactions[-1]
    assert isinstance(chain, TaskChain)
    assert chain.next_task_name == "side_next"
    assert chain.branch == "explore"


def test_validator_accepts_result_forwarding_through_next_task_links() -> None:
    """Follow result availability across ordinary links as well as sequences."""
    assert not _validate(
        _task("first", next_task="middle", pass_result_as="version"),
        _task("middle", next_task="last"),
        _task("last", parameters={"version": _parameter()}),
    )


def test_validator_does_not_treat_none_as_a_default() -> None:
    """A required null default does not supply the missing parameter."""
    assert _validate(
        _task("first", next_task="second"),
        _task("second", parameters={"version": _parameter(default=None)}),
    )


def test_validator_handles_sequence_including_its_start() -> None:
    """Skip the starting name just as TaskResult does for a new sequence."""
    assert not _validate(
        _task(
            "first",
            task_sequence=["first", "last"],
            parameters={"version": _parameter()},
        ),
        _task("last", parameters={"version": _parameter()}),
    )


def test_validator_keeps_schema_errors_separate() -> None:
    """Malformed parameter declarations should report findings, not crash."""
    report = validate_files(
        {
            "tasks/first.yaml": "name: first\ndescription: First\nprompt: Go.\nnext_task: second\nparameters: []\n",
            "tasks/second.yaml": "name: second\ndescription: Second\nprompt: Go.\nparameters:\n  version: invalid\n",
        }
    )
    assert any(item["check"] == "task-parameters" for item in report["errors"])


def test_validator_follows_next_task_after_an_empty_sequence() -> None:
    """An empty sequence must not hide a broken next_task transition."""
    assert _validate(
        _task("first", task_sequence=[], next_task="second"),
        _task("second", parameters={"version": _parameter()}),
    )
