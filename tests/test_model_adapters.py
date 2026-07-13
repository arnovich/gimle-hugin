r"""Regression tests for LLM adapter plain-text content handling.

These tests pin the contract documented on ``ModelResponse.content``: on the
plain-text (non-tool-call) path the adapter must return the model's text
**verbatim**, with newlines preserved. They would fail if any adapter
reintroduced the old ``.replace("\\n", " ")`` newline collapse.

They also pin the *single-tool-call* contract: ``ModelResponse`` carries exactly
one tool call, so every adapter forces one tool call at the request layer and
must never *silently* drop a second one the provider returns anyway — it keeps
the first deterministically and logs a warning naming the dropped calls.
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

MULTILINE = "line one\nline two\nline three"


def _tool_use(name, input, id):
    """Build an Anthropic-style tool_use content block."""
    return SimpleNamespace(type="tool_use", name=name, input=input, id=id)


def _openai_tool_call(name, arguments, id):
    """Build an OpenAI-style tool_call for the assistant message."""
    return SimpleNamespace(
        id=id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class TestSingleToolCallContract:
    """Every adapter is single-tool: forced at request, never dropped silently."""

    def test_anthropic_request_disables_parallel_tool_use(self):
        """The Anthropic request forces exactly one tool call."""
        from gimle.hugin.llm.models.anthropic import AnthropicModel

        fake_response = SimpleNamespace(
            content=[_tool_use("read_file", {"path": "a"}, "t1")],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            id="r",
        )
        create = MagicMock(return_value=fake_response)
        fake_client = MagicMock()
        fake_client.with_options.return_value.messages.create = create

        tool = SimpleNamespace(
            name="read_file",
            description="d",
            parameters={"path": {"type": "string", "description": "p"}},
        )
        model = AnthropicModel(model_name="claude-test")
        with patch("anthropic.Anthropic", return_value=fake_client):
            model.chat_completion(
                "sys", [{"role": "user", "content": "hi"}], [tool]
            )

        tool_choice = create.call_args.kwargs["tool_choice"]
        assert tool_choice["disable_parallel_tool_use"] is True

    def test_anthropic_keeps_first_tool_use_and_warns_on_extras(self, caplog):
        """Two tool_use blocks → keep the first, warn (never silent drop)."""
        from gimle.hugin.llm.models.anthropic import AnthropicModel

        fake_response = SimpleNamespace(
            content=[
                _tool_use("ls", {"path": "."}, "t1"),
                _tool_use("cat", {"path": "README"}, "t2"),
            ],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            id="r",
        )
        fake_client = MagicMock()
        fake_client.with_options.return_value.messages.create.return_value = (
            fake_response
        )

        tool = SimpleNamespace(
            name="ls",
            description="d",
            parameters={"path": {"type": "string", "description": "p"}},
        )
        model = AnthropicModel(model_name="claude-test")
        with caplog.at_level(logging.WARNING):
            with patch("anthropic.Anthropic", return_value=fake_client):
                resp = model.chat_completion(
                    "sys", [{"role": "user", "content": "hi"}], [tool]
                )

        assert resp.tool_call == "ls"
        assert resp.tool_call_id == "t1"
        assert "cat" in caplog.text

    def test_openai_request_disables_parallel_tool_calls(self):
        """The OpenAI request forces exactly one tool call."""
        from gimle.hugin.llm.models.openai import OpenAIModel

        message = SimpleNamespace(
            content=None,
            tool_calls=[_openai_tool_call("read_file", '{"path": "a"}', "t1")],
        )
        fake_response = SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            id="r",
        )
        create = MagicMock(return_value=fake_response)
        fake_client = MagicMock()
        fake_client.chat.completions.create = create

        tool = SimpleNamespace(
            name="read_file",
            description="d",
            parameters={"path": {"type": "string", "description": "p"}},
        )
        model = OpenAIModel(model_name="gpt-test")
        with patch("openai.OpenAI", return_value=fake_client):
            model.chat_completion(
                "sys", [{"role": "user", "content": "hi"}], [tool]
            )

        assert create.call_args.kwargs["parallel_tool_calls"] is False

    def test_openai_keeps_first_tool_call_and_warns_on_extras(self, caplog):
        """Two tool_calls → keep the first, warn (never silent drop)."""
        from gimle.hugin.llm.models.openai import OpenAIModel

        message = SimpleNamespace(
            content=None,
            tool_calls=[
                _openai_tool_call("ls", '{"path": "."}', "t1"),
                _openai_tool_call("cat", '{"path": "README"}', "t2"),
            ],
        )
        fake_response = SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            id="r",
        )
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_response

        tool = SimpleNamespace(
            name="ls",
            description="d",
            parameters={"path": {"type": "string", "description": "p"}},
        )
        model = OpenAIModel(model_name="gpt-test")
        with caplog.at_level(logging.WARNING):
            with patch("openai.OpenAI", return_value=fake_client):
                resp = model.chat_completion(
                    "sys", [{"role": "user", "content": "hi"}], [tool]
                )

        assert resp.tool_call == "ls"
        assert resp.tool_call_id == "t1"
        assert "cat" in caplog.text


class TestAnthropicAdapterPreservesNewlines:
    """The Anthropic adapter must not collapse newlines in text responses."""

    def test_multiline_text_roundtrips_verbatim(self):
        """Multi-line model text comes back verbatim (no newline collapse)."""
        from gimle.hugin.llm.models.anthropic import AnthropicModel

        fake_response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=MULTILINE)],
            usage=SimpleNamespace(input_tokens=3, output_tokens=5),
            id="resp_test",
        )

        fake_client = MagicMock()
        fake_client.with_options.return_value.messages.create.return_value = (
            fake_response
        )

        model = AnthropicModel(model_name="claude-test")
        with patch("anthropic.Anthropic", return_value=fake_client):
            response = model.chat_completion(
                system_prompt="sys",
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
            )

        assert response.role == "assistant"
        assert response.tool_call is None
        assert response.content == MULTILINE
        assert "\n" in response.content


class TestOpenAIAdapterPreservesNewlines:
    """The OpenAI adapter must not collapse newlines in text responses."""

    def test_multiline_text_roundtrips_verbatim(self):
        """Multi-line model text comes back verbatim (no newline collapse)."""
        from gimle.hugin.llm.models.openai import OpenAIModel

        message = SimpleNamespace(content=MULTILINE, tool_calls=None)
        fake_response = SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5),
            id="resp_test",
        )

        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_response

        model = OpenAIModel(model_name="gpt-test")
        with patch("openai.OpenAI", return_value=fake_client):
            response = model.chat_completion(
                system_prompt="sys",
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
            )

        assert response.role == "assistant"
        assert response.tool_call is None
        assert response.content == MULTILINE
        assert "\n" in response.content
