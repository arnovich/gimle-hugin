"""Tests for agent builder generate task schema validation."""


def test_agent_builder_generate_task_rejects_scalar_parameters(mock_stack):
    """Test that generate_task rejects old scalar-style parameters."""
    from gimle.hugin.apps.agent_builder.tools.generate_task import generate_task

    resp = generate_task(
        task_name="t",
        description="d",
        prompt="p",
        parameters={"ticker": "AAPL"},
        tools=None,
        stack=mock_stack,
    )
    assert resp.is_error is True
    assert (
        "Old scalar-style parameters are not supported" in resp.content["error"]
    )
