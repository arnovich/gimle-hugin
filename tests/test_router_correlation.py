"""Tests for the gimle-router correlation header.

Covers the opt-in flag, the contextvar, adapter attachment, and the
multi-agent grouping invariant the feature exists for.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from gimle.hugin.agent.agent import Agent
from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.llm.router_correlation import (
    ROUTER_ROUTE_HEADER,
    ROUTER_TASK_HEADER,
    correlation_scope,
    router_headers,
)


@pytest.fixture
def enabled(monkeypatch):
    """Turn the opt-in integration on for a test."""
    monkeypatch.setenv("HUGIN_GIMLE_ROUTER", "1")


# --- the opt-in flag -------------------------------------------------------


def test_disabled_by_default_emits_no_header():
    """With no flag set, even inside a scope providers get nothing extra."""
    with correlation_scope("edition-1"):
        assert router_headers() == {}


def test_enabled_emits_the_header(enabled):
    """With the flag on, an in-scope call carries the x-gimle-task header."""
    with correlation_scope("edition-1"):
        assert router_headers() == {ROUTER_TASK_HEADER: "edition-1"}


# --- the contextvar --------------------------------------------------------


def test_no_header_outside_a_scope(enabled):
    """No scope active means no header, even when enabled."""
    assert router_headers() == {}


def test_scope_resets_on_exit(enabled):
    """The id is bound inside the block and cleared on exit."""
    with correlation_scope("edition-1"):
        assert router_headers()[ROUTER_TASK_HEADER] == "edition-1"
    assert router_headers() == {}


def test_nested_scopes_restore_the_outer_edition(enabled):
    """Exiting an inner scope restores the outer edition's id."""
    with correlation_scope("outer"):
        with correlation_scope("inner"):
            assert router_headers()[ROUTER_TASK_HEADER] == "inner"
        assert router_headers()[ROUTER_TASK_HEADER] == "outer"


def test_back_to_back_editions_do_not_leak(enabled):
    """The core invariant: each edition sees only its own id, nothing lingers."""
    with correlation_scope("edition-A"):
        assert router_headers()[ROUTER_TASK_HEADER] == "edition-A"
    with correlation_scope("edition-B"):
        assert router_headers()[ROUTER_TASK_HEADER] == "edition-B"
    assert router_headers() == {}


def test_none_session_id_yields_no_header(enabled):
    """A None id (unreachable in practice) is a safe no-header no-op."""
    with correlation_scope(None):
        assert router_headers() == {}


# --- the route (per-agent use-case) ----------------------------------------


def test_route_rides_alongside_the_task_id(enabled):
    """A route in scope adds x-gimle-route beside the task id."""
    with correlation_scope("edition-1", route="editor"):
        assert router_headers() == {
            ROUTER_TASK_HEADER: "edition-1",
            ROUTER_ROUTE_HEADER: "editor",
        }


def test_no_route_means_only_the_task_id(enabled):
    """Without a route, only x-gimle-task is emitted (back-compat)."""
    with correlation_scope("edition-1"):
        assert router_headers() == {ROUTER_TASK_HEADER: "edition-1"}


def test_route_resets_on_scope_exit(enabled):
    """The route is cleared on exit like the task id."""
    with correlation_scope("edition-1", route="editor"):
        assert ROUTER_ROUTE_HEADER in router_headers()
    assert router_headers() == {}


def test_route_emits_nothing_when_disabled():
    """A route in scope is still silent unless the integration is enabled."""
    with correlation_scope("edition-1", route="editor"):
        assert router_headers() == {}


def test_nested_scopes_restore_the_outer_route(enabled):
    """Exiting an inner scope restores the outer edition's route."""
    with correlation_scope("outer", route="journalist"):
        with correlation_scope("inner", route="editor"):
            assert router_headers()[ROUTER_ROUTE_HEADER] == "editor"
        assert router_headers()[ROUTER_ROUTE_HEADER] == "journalist"


# --- adapters attach it ----------------------------------------------------


def _anthropic_create():
    client = MagicMock()
    create = client.with_options.return_value.messages.create
    create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="hi")],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        id="r",
    )
    return client, create


def _run_anthropic():
    from gimle.hugin.llm.models.anthropic import AnthropicModel

    client, create = _anthropic_create()
    model = AnthropicModel(model_name="claude-test")
    with patch("anthropic.Anthropic", return_value=client):
        model.chat_completion(
            system_prompt="sys",
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
        )
    return create


def test_anthropic_stamps_the_header_when_enabled_and_in_scope(enabled):
    """The Anthropic adapter forwards the header on its create call."""
    with correlation_scope("edition-7"):
        create = _run_anthropic()
    assert create.call_args.kwargs["extra_headers"] == {
        ROUTER_TASK_HEADER: "edition-7"
    }


def test_anthropic_sends_no_header_outside_a_scope(enabled):
    """The Anthropic adapter sends an empty header dict with no scope."""
    create = _run_anthropic()
    assert create.call_args.kwargs["extra_headers"] == {}


def test_anthropic_forwards_the_route_when_in_scope(enabled):
    """The adapter forwards x-gimle-route alongside the task id."""
    with correlation_scope("edition-7", route="editor"):
        create = _run_anthropic()
    assert create.call_args.kwargs["extra_headers"] == {
        ROUTER_TASK_HEADER: "edition-7",
        ROUTER_ROUTE_HEADER: "editor",
    }


def _run_openai():
    from gimle.hugin.llm.models.openai import OpenAIModel

    message = SimpleNamespace(content="hi", tool_calls=None)
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        id="r",
    )
    model = OpenAIModel(model_name="gpt-test")
    with patch("openai.OpenAI", return_value=client):
        model.chat_completion(
            system_prompt="sys",
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
        )
    return client.chat.completions.create


def test_openai_stamps_the_header_when_enabled_and_in_scope(enabled):
    """The OpenAI adapter forwards the header in its create kwargs."""
    with correlation_scope("edition-9"):
        create = _run_openai()
    assert create.call_args.kwargs["extra_headers"] == {
        ROUTER_TASK_HEADER: "edition-9"
    }


def test_openai_sends_no_header_outside_a_scope(enabled):
    """The OpenAI adapter sends an empty header dict with no scope."""
    create = _run_openai()
    assert create.call_args.kwargs["extra_headers"] == {}


# --- the gateway threads the session id, shared across an edition ----------


@patch("gimle.hugin.llm.completion.chat_completion")
def test_ask_oracle_stamps_the_session_id(
    mock_chat_completion, enabled, mock_stack, mock_agent, sample_prompt
):
    """Bind the session id as the header for the call the gateway makes."""
    seen = {}

    def capture(**kwargs):
        seen["headers"] = router_headers()
        return {"role": "assistant", "content": "ok"}

    mock_chat_completion.side_effect = capture
    AskOracle(stack=mock_stack, prompt=sample_prompt, template_inputs={}).step()
    assert seen["headers"] == {
        ROUTER_TASK_HEADER: mock_stack.agent.session.id,
        ROUTER_ROUTE_HEADER: mock_stack.agent.config.name,
    }


@patch("gimle.hugin.llm.completion.chat_completion")
def test_sub_agents_of_one_edition_share_the_id(
    mock_chat_completion, enabled, mock_stack, mock_agent, sample_prompt
):
    """Every sub-agent of one Session tags its calls with the same id."""
    seen = []

    def capture(**kwargs):
        seen.append(router_headers())
        return {"role": "assistant", "content": "ok"}

    mock_chat_completion.side_effect = capture
    AskOracle(stack=mock_stack, prompt=sample_prompt, template_inputs={}).step()
    child = Agent(session=mock_agent.session, config=mock_agent.config)
    child.agent_type = "default"
    AskOracle(
        stack=child.stack, prompt=sample_prompt, template_inputs={}
    ).step()

    expected = {
        ROUTER_TASK_HEADER: mock_agent.session.id,
        ROUTER_ROUTE_HEADER: mock_agent.config.name,
    }
    assert seen == [expected, expected]
