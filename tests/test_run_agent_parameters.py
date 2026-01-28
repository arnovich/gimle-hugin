"""Tests for run_agent parameter handling."""

import json
from pathlib import Path


def _write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _get_first_agent_task_parameters(storage_path: Path) -> dict:
    agents_dir = storage_path / "agents"
    agent_files = sorted([p for p in agents_dir.iterdir() if p.is_file()])
    assert agent_files, f"No agent files found in {agents_dir}"
    agent_data = json.loads(agent_files[0].read_text(encoding="utf-8"))

    # Agent -> stack -> interactions(ids) -> interaction file -> TaskDefinition -> task -> parameters
    stack = agent_data["stack"]
    interaction_ids = stack["interactions"]
    assert interaction_ids, "No interactions saved on agent stack"

    interactions_dir = storage_path / "interactions"
    task_def_payload = None
    for interaction_id in interaction_ids:
        payload = json.loads(
            (interactions_dir / interaction_id).read_text(encoding="utf-8")
        )
        if payload.get("type") == "TaskDefinition":
            task_def_payload = payload
            break

    assert task_def_payload is not None, "No TaskDefinition interaction found"
    return task_def_payload["data"]["task"]["parameters"]


def _make_minimal_agent_dir(tmp_path: Path, task_yaml: str) -> Path:
    agent_dir = tmp_path / "agent_pkg"
    _write_yaml(
        agent_dir / "configs" / "config.yaml",
        "\n".join(
            [
                "name: test_config",
                "description: test config",
                "system_template: system",
                "llm_model: test-model",
                "tools: []",
                "",
            ]
        ),
    )
    _write_yaml(agent_dir / "tasks" / "task.yaml", task_yaml)
    return agent_dir


def test_run_agent_noninteractive_applies_defaults(tmp_path, monkeypatch):
    """Test that default parameter values are applied in non-interactive mode."""
    from gimle.hugin.cli import run_agent

    agent_dir = _make_minimal_agent_dir(
        tmp_path,
        "\n".join(
            [
                "name: test_task",
                "description: test task",
                "parameters:",
                "  foo:",
                "    type: string",
                "    description: Foo value",
                "    required: false",
                "    default: hello",
                "prompt: |",
                "  Foo is {{ foo }}",
                "",
            ]
        ),
    )

    storage_path = tmp_path / "storage"
    monkeypatch.setattr(
        run_agent.sys,
        "argv",
        [
            "hugin-run",
            "--non-interactive",
            "--task",
            "test_task",
            "--task-path",
            str(agent_dir),
            "--storage-path",
            str(storage_path),
            "--max-steps",
            "0",
            "--log-level",
            "ERROR",
        ],
    )

    exit_code = run_agent.main()
    assert exit_code == 0

    params = _get_first_agent_task_parameters(storage_path)
    assert params["foo"]["value"] == "hello"


def test_run_agent_noninteractive_coerces_types(tmp_path, monkeypatch):
    """Test that parameter types are coerced correctly."""
    from gimle.hugin.cli import run_agent

    agent_dir = _make_minimal_agent_dir(
        tmp_path,
        "\n".join(
            [
                "name: test_task",
                "description: test task",
                "parameters:",
                "  count:",
                "    type: integer",
                "    description: Count",
                "    required: false",
                "    default: 1",
                "  flag:",
                "    type: boolean",
                "    description: Flag",
                "    required: false",
                "    default: false",
                "prompt: |",
                "  Count={{ count }}, Flag={{ flag }}",
                "",
            ]
        ),
    )

    storage_path = tmp_path / "storage"
    monkeypatch.setattr(
        run_agent.sys,
        "argv",
        [
            "hugin-run",
            "--non-interactive",
            "--task",
            "test_task",
            "--task-path",
            str(agent_dir),
            "--storage-path",
            str(storage_path),
            "--max-steps",
            "0",
            "--log-level",
            "ERROR",
            "--parameters",
            json.dumps({"count": "5", "flag": True}),
        ],
    )

    exit_code = run_agent.main()
    assert exit_code == 0

    params = _get_first_agent_task_parameters(storage_path)
    assert params["count"]["value"] == 5
    assert params["flag"]["value"] is True


def test_run_agent_noninteractive_missing_required_returns_error(
    tmp_path, monkeypatch, capsys
):
    """Test that missing required parameters return an error."""
    from gimle.hugin.cli import run_agent

    agent_dir = _make_minimal_agent_dir(
        tmp_path,
        "\n".join(
            [
                "name: test_task",
                "description: test task",
                "parameters:",
                "  must_have:",
                "    type: string",
                "    description: Must be provided",
                "    required: true",
                "prompt: |",
                "  {{ must_have }}",
                "",
            ]
        ),
    )

    storage_path = tmp_path / "storage"
    monkeypatch.setattr(
        run_agent.sys,
        "argv",
        [
            "hugin-run",
            "--non-interactive",
            "--task",
            "test_task",
            "--task-path",
            str(agent_dir),
            "--storage-path",
            str(storage_path),
            "--max-steps",
            "0",
            "--log-level",
            "ERROR",
        ],
    )

    exit_code = run_agent.main()
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "Missing required parameter(s) for task 'test_task'" in out


def test_run_agent_noninteractive_categorical_choices(tmp_path, monkeypatch):
    """Test that categorical parameters apply default choices correctly."""
    from gimle.hugin.cli import run_agent

    agent_dir = _make_minimal_agent_dir(
        tmp_path,
        "\n".join(
            [
                "name: test_task",
                "description: test task",
                "parameters:",
                "  mode:",
                "    type: categorical",
                "    description: Mode",
                "    required: false",
                "    default: fast",
                "    choices: [fast, slow]",
                "prompt: |",
                "  Mode={{ mode }}",
                "",
            ]
        ),
    )

    storage_path = tmp_path / "storage"
    # Default applied
    monkeypatch.setattr(
        run_agent.sys,
        "argv",
        [
            "hugin-run",
            "--non-interactive",
            "--task",
            "test_task",
            "--task-path",
            str(agent_dir),
            "--storage-path",
            str(storage_path),
            "--max-steps",
            "0",
            "--log-level",
            "ERROR",
        ],
    )
    assert run_agent.main() == 0
    params = _get_first_agent_task_parameters(storage_path)
    assert params["mode"]["value"] == "fast"


def test_run_agent_noninteractive_categorical_invalid_value(
    tmp_path, monkeypatch, capsys
):
    """Test that invalid categorical values return an error."""
    from gimle.hugin.cli import run_agent

    agent_dir = _make_minimal_agent_dir(
        tmp_path,
        "\n".join(
            [
                "name: test_task",
                "description: test task",
                "parameters:",
                "  mode:",
                "    type: categorical",
                "    description: Mode",
                "    required: false",
                "    default: fast",
                "    choices: [fast, slow]",
                "prompt: |",
                "  Mode={{ mode }}",
                "",
            ]
        ),
    )

    storage_path = tmp_path / "storage"
    monkeypatch.setattr(
        run_agent.sys,
        "argv",
        [
            "hugin-run",
            "--non-interactive",
            "--task",
            "test_task",
            "--task-path",
            str(agent_dir),
            "--storage-path",
            str(storage_path),
            "--max-steps",
            "0",
            "--log-level",
            "ERROR",
            "--parameters",
            json.dumps({"mode": "nope"}),
        ],
    )
    exit_code = run_agent.main()
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "Invalid value for 'mode'" in out
