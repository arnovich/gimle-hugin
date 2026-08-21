"""The report must say when it has altered the text it is showing.

Seen in a real improve run. The tool emitted `File not found: /tmp/x.csv`
correctly, via an f-string. `error_signature` masks paths, so the report showed
`File not found: <path>`. The model read the placeholder as the tool's literal
output and proposed "fix the f-string in this tool" -- confidently, citing a
real error rate, about code that was already correct.

The privacy measure created a false diagnosis, and nothing in the report said
the text had been altered. Note the citation guard cannot catch this: the
metric cited was real and accurately quoted. It checks evidence, not reasoning.
"""

import json

import pytest

from gimle.hugin.analysis.traces import analyze_traces


def _write_run(storage, run_id, error_text=None):
    agents = storage / "agents"
    interactions = storage / "interactions"
    agents.mkdir(parents=True, exist_ok=True)
    interactions.mkdir(parents=True, exist_ok=True)
    ids = []

    def add(kind, data):
        uuid = f"{run_id}-{len(ids)}"
        (interactions / uuid).write_text(
            json.dumps({"type": kind, "data": data})
        )
        ids.append(uuid)

    add("TaskDefinition", {"task": {"name": "t", "parameters": {}}})
    add("ToolCall", {"tool": "parse_csv", "args": {}, "tool_call_id": "c1"})
    add(
        "ToolResult",
        {
            "tool_name": "parse_csv",
            "tool_call_id": "c1",
            "is_error": bool(error_text),
            "result": {"error": error_text} if error_text else {"ok": 1},
        },
    )
    add("TaskResult", {"finish_type": "success", "branch": None})
    (agents / run_id).write_text(
        json.dumps(
            {
                "uuid": run_id,
                "config": {"name": "demo", "tools": ["parse_csv"]},
                "stack": {"interactions": ids},
            }
        )
    )


@pytest.fixture
def storage_with_error(tmp_path):
    root = tmp_path / "storage"
    _write_run(root, "run-1", "File not found: /tmp/expenses.csv")
    return root


class TestTheReportDeclaresItsOwnMasking:
    """A masked value that is not labelled reads as literal output."""

    def test_the_path_is_masked(self, storage_with_error):
        """The privacy behaviour that causes the confusion, still working."""
        report = analyze_traces(str(storage_with_error))

        assert "/tmp/expenses.csv" not in json.dumps(report)
        assert "<path>" in json.dumps(report)

    def test_a_caveat_says_the_text_was_altered(self, storage_with_error):
        """Without this the reader has no way to know."""
        caveats = " ".join(analyze_traces(str(storage_with_error))["caveats"])

        assert "placeholders" in caveats
        assert "<path>" in caveats

    def test_it_names_the_mistake_to_avoid(self, storage_with_error):
        """A note saying "these are masked" is weaker than one saying
        "so do not diagnose a formatting bug from them"."""
        caveats = " ".join(analyze_traces(str(storage_with_error))["caveats"])

        assert "formatting bug" in caveats

    def test_no_error_no_note(self, tmp_path):
        """A clean run should not carry a caveat about error text."""
        root = tmp_path / "storage"
        _write_run(root, "run-1", error_text=None)

        caveats = " ".join(analyze_traces(str(root))["caveats"])

        assert "placeholders" not in caveats
