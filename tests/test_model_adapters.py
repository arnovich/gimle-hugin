r"""Regression tests for LLM adapter plain-text content handling.

These tests pin the contract documented on ``ModelResponse.content``: on the
plain-text (non-tool-call) path the adapter must return the model's text
**verbatim**, with newlines preserved. They would fail if any adapter
reintroduced the old ``.replace("\\n", " ")`` newline collapse.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

MULTILINE = "line one\nline two\nline three"


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
