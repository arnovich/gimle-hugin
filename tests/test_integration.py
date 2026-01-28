"""Integration tests that test the complete flow without actual LLM calls.

These tests use the MockModel to simulate real LLM behavior.
"""

from unittest.mock import Mock, patch

import pytest

from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.llm.completion import chat_completion
from tests.conftest import MockModel


class TestModelIntegration:
    """Integration tests for the complete model system."""

    @patch("gimle.hugin.llm.completion.get_model_registry")
    def test_complete_llm_workflow(
        self,
        mock_get_registry,
        sample_system_prompt,
        sample_messages,
        sample_tools,
    ):
        """Test the complete workflow from LLMCall to model response."""
        # Setup mock registry with MockModel
        mock_registry = Mock()
        mock_model = MockModel(
            {
                "model": "test-model",
                "temperature": 0.7,
                "max_tokens": 1000,
                "tool_choice": {"type": "auto"},
            }
        )
        mock_registry.get_model.return_value = mock_model
        mock_get_registry.return_value = mock_registry

        # Test chat_completion function
        response = chat_completion(
            system_prompt=sample_system_prompt,
            messages=sample_messages,
            tools=sample_tools,
            llm_model="test-model",
        )

        # Verify response structure
        assert "role" in response
        assert "content" in response
        assert "input_tokens" in response
        assert "output_tokens" in response
        assert response["extra_content"]["call_count"] == 1
        assert response["extra_content"]["message_count"] == len(
            sample_messages
        )
        assert response["extra_content"]["tool_count"] == len(sample_tools)

    @patch("gimle.hugin.llm.completion.get_model_registry")
    def test_multiple_model_calls(
        self, mock_get_registry, sample_system_prompt, sample_messages
    ):
        """Test multiple calls to the same model."""
        # Setup mock registry
        mock_registry = Mock()
        mock_model = MockModel(
            {
                "model": "test-model",
                "temperature": 0.7,
                "max_tokens": 1000,
                "tool_choice": {"type": "auto"},
            }
        )
        mock_registry.get_model.return_value = mock_model
        mock_get_registry.return_value = mock_registry

        # Make multiple calls
        response1 = chat_completion(
            system_prompt=sample_system_prompt,
            messages=sample_messages,
            tools=[],
            llm_model="test-model",
        )

        response2 = chat_completion(
            system_prompt=sample_system_prompt,
            messages=sample_messages,
            tools=[],
            llm_model="test-model",
        )

        # Verify both calls succeeded and call count increased
        assert response1["extra_content"]["call_count"] == 1
        assert response2["extra_content"]["call_count"] == 2
        assert (
            response1["content"] == response2["content"]
        )  # Same mock response

    @patch("gimle.hugin.llm.completion.get_model_registry")
    def test_different_models(
        self, mock_get_registry, sample_system_prompt, sample_messages
    ):
        """Test using different models."""
        # Setup mock registry with multiple models
        mock_registry = Mock()

        model1 = MockModel(
            {
                "model": "model-1",
                "temperature": 0.7,
                "max_tokens": 1000,
                "tool_choice": {"type": "auto"},
            },
            {"content": "Response from model 1", "role": "assistant"},
        )

        model2 = MockModel(
            {
                "model": "model-2",
                "temperature": 0.5,
                "max_tokens": 2000,
                "tool_choice": {"type": "auto"},
            },
            {"content": "Response from model 2", "role": "assistant"},
        )

        def get_model_side_effect(model_name):
            if model_name == "model-1":
                return model1
            elif model_name == "model-2":
                return model2
            else:
                raise ValueError(f"Model {model_name} not found")

        mock_registry.get_model.side_effect = get_model_side_effect
        mock_get_registry.return_value = mock_registry

        # Test first model
        response1 = chat_completion(
            system_prompt=sample_system_prompt,
            messages=sample_messages,
            tools=[],
            llm_model="model-1",
        )

        # Test second model
        response2 = chat_completion(
            system_prompt=sample_system_prompt,
            messages=sample_messages,
            tools=[],
            llm_model="model-2",
        )

        # Verify different responses
        assert response1["content"] == "Response from model 1"
        assert response2["content"] == "Response from model 2"
        assert response1["extra_content"]["call_count"] == 1
        assert response2["extra_content"]["call_count"] == 1

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_llm_call_integration(
        self, mock_chat_completion, mock_stack, mock_agent, sample_prompt
    ):
        """Test LLMCall integration with mocked chat_completion."""
        # Setup mock response
        mock_response = {
            "role": "assistant",
            "content": "Integration test response",
            "input_tokens": 20,
            "output_tokens": 10,
        }
        mock_chat_completion.return_value = mock_response

        # Create LLMCall
        llm_call = AskOracle(
            stack=mock_stack,
            prompt=sample_prompt,
            template_inputs={"prompt": "Integration test prompt"},
        )

        # Execute step
        result = llm_call.step()

        # Verify success
        assert result is True

        # Verify chat_completion was called
        mock_chat_completion.assert_called_once()
        call_args = mock_chat_completion.call_args
        assert call_args[1]["llm_model"] == "test-model"

        # Verify interaction was added to stack
        assert len(mock_stack.interactions) == 1
        interaction = mock_stack.interactions[0]
        assert interaction.response == mock_response


class TestErrorHandling:
    """Test error handling in the model system."""

    @patch("gimle.hugin.llm.completion.get_model_registry")
    def test_model_not_found_error(
        self, mock_get_registry, sample_system_prompt, sample_messages
    ):
        """Test error handling when model is not found."""
        # Setup mock to raise error
        mock_registry = Mock()
        mock_registry.get_model.side_effect = ValueError(
            "Model nonexistent not found"
        )
        mock_get_registry.return_value = mock_registry

        # Test that error is propagated
        with pytest.raises(ValueError, match="Model nonexistent not found"):
            chat_completion(
                system_prompt=sample_system_prompt,
                messages=sample_messages,
                tools=[],
                llm_model="nonexistent",
            )

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_llm_call_error_handling(
        self, mock_chat_completion, mock_stack, sample_prompt
    ):
        """Test error handling in LLMCall."""
        # Setup mock to raise error
        mock_chat_completion.side_effect = Exception("Network error")

        # Create LLMCall
        llm_call = AskOracle(
            stack=mock_stack, prompt=sample_prompt, template_inputs={}
        )

        # Test that error is propagated
        with pytest.raises(Exception, match="Network error"):
            llm_call.step()


class TestPerformance:
    """Test performance characteristics without actual LLM calls."""

    @patch("gimle.hugin.llm.completion.get_model_registry")
    def test_model_response_time(
        self, mock_get_registry, sample_system_prompt, sample_messages
    ):
        """Test that mock model responds quickly."""
        import time

        # Setup mock registry
        mock_registry = Mock()
        mock_model = MockModel(
            {
                "model": "test-model",
                "temperature": 0.7,
                "max_tokens": 1000,
                "tool_choice": {"type": "auto"},
            }
        )
        mock_registry.get_model.return_value = mock_model
        mock_get_registry.return_value = mock_registry

        # Measure response time
        start_time = time.time()
        response = chat_completion(
            system_prompt=sample_system_prompt,
            messages=sample_messages,
            tools=[],
            llm_model="test-model",
        )
        end_time = time.time()

        # Verify response time is reasonable (should be very fast for mock)
        response_time = end_time - start_time
        assert response_time < 0.1  # Should be much faster than 100ms
        assert response is not None

    @patch("gimle.hugin.llm.completion.get_model_registry")
    def test_concurrent_model_calls(
        self, mock_get_registry, sample_system_prompt, sample_messages
    ):
        """Test concurrent calls to the same model."""
        import threading

        # Setup mock registry
        mock_registry = Mock()
        mock_model = MockModel(
            {
                "model": "test-model",
                "temperature": 0.7,
                "max_tokens": 1000,
                "tool_choice": {"type": "auto"},
            }
        )
        mock_registry.get_model.return_value = mock_model
        mock_get_registry.return_value = mock_registry

        results = []
        errors = []

        def make_call():
            try:
                response = chat_completion(
                    system_prompt=sample_system_prompt,
                    messages=sample_messages,
                    tools=[],
                    llm_model="test-model",
                )
                results.append(response)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=make_call)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify all calls succeeded
        assert len(errors) == 0
        assert len(results) == 5

        # Verify all responses are valid
        for response in results:
            assert "role" in response
            assert "content" in response
            assert "extra_content" in response
            assert "call_count" in response["extra_content"]
