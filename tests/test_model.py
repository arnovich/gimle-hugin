"""Tests for LLM model functionality."""

import logging

import pytest

from gimle.hugin.llm.models.model import Model


class TestModel:
    """Test the base Model class interface and properties."""

    def test_model_initialization(self, mock_model_config):
        """Test that a model can be initialized with config."""
        model = Model(mock_model_config)
        assert model.config == mock_model_config

    def test_model_name_property(self, mock_model_config):
        """Test the model_name property."""
        model = Model(mock_model_config)
        assert model.model_name == "test-model"

    def test_model_name_missing(self):
        """Test that model_name raises ValueError when missing."""
        model = Model({})
        with pytest.raises(ValueError, match="model_name not set"):
            _ = model.model_name

    def test_temperature_property(self, mock_model_config):
        """Test the temperature property."""
        model = Model(mock_model_config)
        assert model.temperature == 0.7

    def test_temperature_missing(self):
        """Test that temperature returns None when not set."""
        model = Model({})
        assert model.temperature is None

    def test_max_tokens_property(self, mock_model_config):
        """Test the max_tokens property."""
        model = Model(mock_model_config)
        assert model.max_tokens == 1000

    def test_max_tokens_missing(self):
        """Test that max_tokens raises ValueError when missing."""
        model = Model({})
        with pytest.raises(ValueError, match="max_tokens not set"):
            _ = model.max_tokens

    def test_tool_choice_property(self, mock_model_config):
        """Test the tool_choice property."""
        model = Model(mock_model_config)
        assert model.tool_choice == {"type": "auto"}

    def test_tool_choice_missing(self):
        """Test that tool_choice raises ValueError when missing."""
        model = Model({})
        with pytest.raises(ValueError, match="tool_choice not set"):
            _ = model.tool_choice

    def test_chat_completion_not_implemented(
        self, mock_model_config, sample_system_prompt, sample_messages
    ):
        """Test that chat_completion raises NotImplementedError."""
        model = Model(mock_model_config)
        with pytest.raises(
            NotImplementedError, match="chat_completion not implemented"
        ):
            model.chat_completion(sample_system_prompt, sample_messages)

    def test_pretty_print_messages(self, sample_messages, caplog):
        """Test the pretty_print_messages static method."""
        with caplog.at_level(
            logging.DEBUG, logger="gimle.hugin.llm.models.model"
        ):
            Model.log_messages(sample_messages)

        assert "USER message 0" in caplog.text
        assert "ASSISTANT message 1" in caplog.text
        assert "Hello, how are you?" in caplog.text
        assert "I'm doing well, thank you!" in caplog.text


class TestMockModel:
    """Test the MockModel implementation."""

    def test_mock_model_initialization(self, mock_model):
        """Test that MockModel can be initialized."""
        assert mock_model.config["model"] == "test-model"
        assert mock_model.call_count == 0

    def test_mock_model_chat_completion(
        self, mock_model, sample_system_prompt, sample_messages
    ):
        """Test that MockModel returns expected response."""
        response = mock_model.chat_completion(
            sample_system_prompt, sample_messages
        )

        assert response.role == "assistant"
        assert response.content == "This is a mock response"
        assert response.input_tokens == 10
        assert response.output_tokens == 5
        assert response.extra_content["call_count"] == 1
        assert response.extra_content["system_prompt"] == sample_system_prompt
        assert response.extra_content["message_count"] == len(sample_messages)
        assert response.extra_content["tool_count"] == 0

    def test_mock_model_with_tools(
        self, mock_model, sample_system_prompt, sample_messages, sample_tools
    ):
        """Test MockModel with tools."""
        response = mock_model.chat_completion(
            sample_system_prompt, sample_messages, sample_tools
        )

        assert response.extra_content["tool_count"] == len(sample_tools)
        assert response.extra_content["call_count"] == 1

    def test_mock_model_call_count(
        self, mock_model, sample_system_prompt, sample_messages
    ):
        """Test that call count increments correctly."""
        assert mock_model.call_count == 0

        mock_model.chat_completion(sample_system_prompt, sample_messages)
        assert mock_model.call_count == 1

        mock_model.chat_completion(sample_system_prompt, sample_messages)
        assert mock_model.call_count == 2

    def test_mock_model_custom_response(
        self,
        mock_model_with_custom_response,
        sample_system_prompt,
        sample_messages,
    ):
        """Test MockModel with custom response."""
        response = mock_model_with_custom_response.chat_completion(
            sample_system_prompt, sample_messages
        )

        assert response.content == "Custom mock response"
        assert response.input_tokens == 20
        assert response.output_tokens == 10
