"""Tests for monitor agents to_jsonable function."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone


def test_monitor_agents_to_jsonable_handles_dataclasses_and_datetime():
    """Test that to_jsonable converts dataclasses and datetime objects."""
    from gimle.hugin.cli.monitor_agents import to_jsonable
    from gimle.hugin.llm.prompt.prompt import Prompt

    @dataclass
    class Inner:
        x: int

    payload = {
        "prompt": Prompt(type="text", text="hello"),
        "dt": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "inner": Inner(3),
        "set": {"a", "b"},
    }

    converted = to_jsonable(payload)
    # Should be JSON-serializable
    json.dumps(converted)
    assert converted["prompt"]["text"] == "hello"
