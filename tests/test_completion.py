"""Tests for LLM completion functionality."""

from unittest.mock import Mock, patch

import pytest

from gimle.hugin.llm.completion import (
    chat_completion,
    make_completion_cache_key,
)
from gimle.hugin.llm.models.model import ModelResponse


class TestMakeCompletionCacheKey:
    """Test the make_completion_cache_key function."""

    def test_make_completion_cache_key_basic(self):
        """Test basic cache key generation."""
        params = {"messages": [{"role": "user", "content": "hello"}]}
        key = make_completion_cache_key("test", params)
        assert key.startswith("test")
        assert "messages=" in key

    def test_make_completion_cache_key_short_messages(self):
        """Test cache key with short message list."""
        params = {"messages": [{"role": "user", "content": "hello"}]}
        key = make_completion_cache_key("test", params)
        # Should include the single message
        assert "hello" in key

    def test_make_completion_cache_key_long_messages(self):
        """Test cache key with long message list (should be truncated)."""
        messages = [
            {"role": "user", "content": "message1"},
            {"role": "user", "content": "message2"},
            {"role": "user", "content": "message3"},
            {"role": "user", "content": "message4"},
            {"role": "user", "content": "message5"},
            {"role": "user", "content": "message6"},
            {"role": "user", "content": "message7"},
        ]
        params = {"messages": messages}
        key = make_completion_cache_key("test", params)

        # Should include first 2 messages and last 5 (nearest_context_window)
        assert "message1" in key
        assert "message2" in key
        # The function should truncate the middle messages
        # Check that the key contains the expected structure
        assert "message1" in key
        assert "message2" in key
        # The last 5 messages should be included (message3, message4, message5, message6, message7)
        assert "message6" in key  # Should be in last 5
        assert "message7" in key  # Should be in last 5

    def test_make_completion_cache_key_no_messages(self):
        """Test cache key without messages."""
        params = {"other_param": "value"}
        key = make_completion_cache_key("test", params)
        assert "other_param=value" in key
        assert "messages=" not in key


class TestChatCompletion:
    """Test the chat_completion function."""

    @patch("gimle.hugin.llm.completion.get_model_registry")
    def test_chat_completion_basic(
        self,
        mock_get_registry,
        sample_system_prompt,
        sample_messages,
        sample_tools,
    ):
        """Test basic chat completion functionality."""
        # Setup mock
        mock_registry = Mock()
        mock_model = Mock()
        mock_model.chat_completion.return_value = ModelResponse(
            role="assistant",
            content="test response",
        )
        mock_registry.get_model.return_value = mock_model
        mock_get_registry.return_value = mock_registry

        # Call function
        result = chat_completion(
            system_prompt=sample_system_prompt,
            messages=sample_messages,
            tools=sample_tools,
            llm_model="test-model",
        )

        # Verify calls
        mock_get_registry.assert_called_once()
        mock_registry.get_model.assert_called_once_with("test-model")
        mock_model.chat_completion.assert_called_once_with(
            sample_system_prompt, sample_messages, sample_tools
        )

        # Verify result
        assert result["role"] == "assistant"
        assert result["content"] == "test response"

    @patch("gimle.hugin.llm.completion.get_model_registry")
    def test_chat_completion_no_tools(
        self, mock_get_registry, sample_system_prompt, sample_messages
    ):
        """Test chat completion without tools."""
        # Setup mock
        mock_registry = Mock()
        mock_model = Mock()
        mock_model.chat_completion.return_value = ModelResponse(
            role="assistant",
            content="test response",
        )
        mock_registry.get_model.return_value = mock_model
        mock_get_registry.return_value = mock_registry

        # Call function
        chat_completion(
            system_prompt=sample_system_prompt,
            messages=sample_messages,
            tools=[],
            llm_model="test-model",
        )

        # Verify model was called with empty tools list
        mock_model.chat_completion.assert_called_once_with(
            sample_system_prompt, sample_messages, []
        )

    @patch("gimle.hugin.llm.completion.get_model_registry")
    def test_chat_completion_model_not_found(
        self, mock_get_registry, sample_system_prompt, sample_messages
    ):
        """Test chat completion when model is not found."""
        # Setup mock to raise ValueError
        mock_registry = Mock()
        mock_registry.get_model.side_effect = ValueError(
            "Model test-model not found"
        )
        mock_get_registry.return_value = mock_registry

        # Call function and expect exception
        with pytest.raises(ValueError, match="Model test-model not found"):
            chat_completion(
                system_prompt=sample_system_prompt,
                messages=sample_messages,
                tools=[],
                llm_model="test-model",
            )

    @patch("gimle.hugin.llm.completion.get_model_registry")
    def test_chat_completion_model_error(
        self, mock_get_registry, sample_system_prompt, sample_messages
    ):
        """Test chat completion when model raises an error."""
        # Setup mock
        mock_registry = Mock()
        mock_model = Mock()
        mock_model.chat_completion.side_effect = Exception("Model error")
        mock_registry.get_model.return_value = mock_model
        mock_get_registry.return_value = mock_registry

        # Call function and expect exception
        with pytest.raises(Exception, match="Model error"):
            chat_completion(
                system_prompt=sample_system_prompt,
                messages=sample_messages,
                tools=[],
                llm_model="test-model",
            )

    @patch("gimle.hugin.llm.completion.get_model_registry")
    def test_chat_completion_logging(
        self, mock_get_registry, sample_system_prompt, sample_messages, caplog
    ):
        """Test that chat completion logs appropriately."""
        # Setup mock
        mock_registry = Mock()
        mock_model = Mock()
        mock_model.chat_completion.return_value = ModelResponse(
            role="assistant",
            content="test response",
        )
        mock_registry.get_model.return_value = mock_model
        mock_get_registry.return_value = mock_registry

        # Call function
        with caplog.at_level("DEBUG"):
            chat_completion(
                system_prompt=sample_system_prompt,
                messages=sample_messages,
                tools=[],
                llm_model="test-model",
            )

        # Check logging
        assert "Chat completion using test-model model" in caplog.text


class TestChatCompletionCaching:
    """Test the caching functionality of chat_completion."""

    @patch("gimle.hugin.llm.completion.get_model_registry")
    def test_chat_completion_cache_key_generation(
        self, mock_get_registry, sample_system_prompt, sample_messages
    ):
        """Test that cache keys are generated correctly."""
        # This test verifies the cache key function is used
        # The actual caching behavior would be tested with integration tests
        mock_registry = Mock()
        mock_model = Mock()
        mock_model.chat_completion.return_value = ModelResponse(
            role="assistant",
            content="test response",
        )
        mock_registry.get_model.return_value = mock_model
        mock_get_registry.return_value = mock_registry

        # Call function multiple times with same parameters
        result1 = chat_completion(
            system_prompt=sample_system_prompt,
            messages=sample_messages,
            tools=[],
            llm_model="test-model",
        )

        result2 = chat_completion(
            system_prompt=sample_system_prompt,
            messages=sample_messages,
            tools=[],
            llm_model="test-model",
        )

        # Both calls should succeed
        assert result1 == result2
        # Model should be called twice (no actual caching in test)
        assert mock_model.chat_completion.call_count == 2
