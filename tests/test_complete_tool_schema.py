"""Full schemas survive Hugin storage and provider formatting without losing constraints."""

from copy import deepcopy
from dataclasses import asdict

from gimle.hugin.tools.tool import Tool, ToolConfig


def test_complete_schema_roundtrip_and_no_implicit_null_arguments(
    complete_tool_schema,
):
    """Preserve nested inputs without injecting absent optional values."""
    calls = []
    tool = Tool(
        "complete_schema",
        "Nested arguments",
        {},
        False,
        ToolConfig(),
        func=lambda **kwargs: calls.append(kwargs) or {"content": kwargs},
        input_schema=complete_tool_schema,
    )
    serialized = deepcopy(tool.to_dict())
    serialized["options"] = asdict(tool.options)
    restored = Tool.from_dict(serialized, register=False)
    assert restored.input_schema == complete_tool_schema
    Tool.execute_tool(tool, None, None, artifacts=[{"uri": "artifact:1"}])
    assert "limit" not in calls[0]
    assert calls[0]["artifacts"] == [{"uri": "artifact:1"}]


def test_provider_wire_preserves_nested_schema(
    schema_wire, complete_tool_schema
):
    """Every provider receives all schema constraints and its own copy."""
    import pytest

    tool = Tool(
        "complete_schema",
        "Nested arguments",
        {},
        False,
        ToolConfig(),
        input_schema=complete_tool_schema,
    )
    with pytest.raises(schema_wire.captured):
        schema_wire.model.chat_completion(
            "Fixture", [{"role": "user", "content": "Check"}], [tool]
        )
    wire = schema_wire.call.call_args.kwargs["tools"][0]
    schema = (
        wire["input_schema"]
        if schema_wire.provider == "anthropic"
        else wire["function"]["parameters"]
    )
    assert schema == complete_tool_schema
    schema["properties"].clear()
    assert tool.input_schema == complete_tool_schema


def test_complete_schema_rejects_mixed_or_injected_arguments(
    complete_tool_schema,
):
    """Reject ambiguous legacy defaults and framework context parameters."""
    import pytest

    with pytest.raises(ValueError, match="cannot mix"):
        Tool(
            "bad",
            "Bad",
            {"legacy": {"type": "string"}},
            False,
            ToolConfig(),
            input_schema=complete_tool_schema,
        )
    with pytest.raises(ValueError, match="cannot mix"):
        Tool(
            "bad",
            "Bad",
            {},
            False,
            ToolConfig(include_reason=True),
            input_schema=complete_tool_schema,
        )
    complete_tool_schema["properties"]["stack"] = {"type": "string"}
    with pytest.raises(ValueError, match="injected context"):
        Tool(
            "bad",
            "Bad",
            {},
            False,
            ToolConfig(),
            input_schema=complete_tool_schema,
        )
