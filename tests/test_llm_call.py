"""Tests for LLM call functionality."""

from unittest.mock import patch

import pytest

from gimle.hugin.agent.task import Task
from gimle.hugin.interaction.ask_oracle import AskOracle
from gimle.hugin.interaction.oracle_response import OracleResponse
from gimle.hugin.interaction.task_definition import TaskDefinition


class TestLLMCall:
    """Test the LLMCall interaction class."""

    def test_llm_call_initialization(self, mock_stack, sample_prompt):
        """Test that LLMCall can be initialized with prompt and template_inputs."""
        llm_call = AskOracle(
            stack=mock_stack,
            prompt=sample_prompt,
            template_inputs={"test": "value"},
        )
        assert llm_call.prompt == sample_prompt
        assert llm_call.template_inputs == {"test": "value"}

    def test_llm_call_inherits_from_interaction(
        self, mock_stack, sample_prompt
    ):
        """Test that LLMCall inherits from Interaction."""
        llm_call = AskOracle(
            stack=mock_stack, prompt=sample_prompt, template_inputs={}
        )
        assert hasattr(llm_call, "stack")
        assert hasattr(llm_call, "branch")
        assert hasattr(llm_call, "step")

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_llm_call_step_success(
        self, mock_chat_completion, mock_stack, mock_agent, sample_prompt
    ):
        """Test successful execution of LLMCall step."""
        # Setup mock
        mock_response = {
            "role": "assistant",
            "content": "Test response",
            "input_tokens": 10,
            "output_tokens": 5,
        }
        mock_chat_completion.return_value = mock_response

        # Create LLMCall instance
        llm_call = AskOracle(
            stack=mock_stack,
            prompt=sample_prompt,
            template_inputs={"test": "value"},
        )

        # Execute step
        result = llm_call.step()

        # Verify result
        assert result is True

        # Verify chat_completion was called
        mock_chat_completion.assert_called_once()
        call_args = mock_chat_completion.call_args
        assert call_args[1]["messages"] == []
        assert call_args[1]["tools"] == []
        assert call_args[1]["llm_model"] == "test-model"

        # Verify interaction was added to stack
        assert len(mock_stack.interactions) == 1
        added_interaction = mock_stack.interactions[0]
        assert isinstance(added_interaction, OracleResponse)
        assert added_interaction.response == mock_response

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_llm_call_step_with_custom_options(
        self, mock_chat_completion, mock_stack, mock_agent, sample_prompt
    ):
        """Test LLMCall step with custom options."""
        # Setup mock
        mock_response = {"role": "assistant", "content": "Test response"}
        mock_chat_completion.return_value = mock_response

        llm_call = AskOracle(
            stack=mock_stack, prompt=sample_prompt, template_inputs={}
        )

        # Execute step
        llm_call.step()

        # Verify custom model was used
        call_args = mock_chat_completion.call_args
        assert call_args[1]["llm_model"] == "test-model"

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_llm_call_step_chat_completion_error(
        self, mock_chat_completion, mock_stack, sample_prompt
    ):
        """Test LLMCall step when chat_completion raises an error."""
        # Setup mock to raise error
        mock_chat_completion.side_effect = Exception("API Error")

        # Create LLMCall instance
        llm_call = AskOracle(
            stack=mock_stack, prompt=sample_prompt, template_inputs={}
        )

        # Execute step and expect exception
        with pytest.raises(Exception, match="API Error"):
            llm_call.step()

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_llm_call_step_logging(
        self, mock_chat_completion, caplog, mock_stack, sample_prompt
    ):
        """Test that LLMCall step logs appropriately."""
        # Setup mock
        mock_response = {"role": "assistant", "content": "Test response"}
        mock_chat_completion.return_value = mock_response

        # Create LLMCall instance
        llm_call = AskOracle(
            stack=mock_stack, prompt=sample_prompt, template_inputs={}
        )

        # Execute step with logging
        with caplog.at_level("INFO"):
            llm_call.step()

        # Check logging
        assert "No interactions found on the stack" in caplog.text

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_llm_call_step_with_interactions(
        self, mock_chat_completion, mock_stack, sample_prompt
    ):
        """Test LLMCall step with existing interactions."""
        # Setup mock
        mock_response = {"role": "assistant", "content": "Test response"}
        mock_chat_completion.return_value = mock_response

        # Create a task definition
        task_definition = TaskDefinition(
            stack=mock_stack,
            task=Task(
                name="test-task",
                description="Test task",
                parameters={},
                prompt="Test prompt",
            ),
        )
        mock_stack.add_interaction(task_definition)

        # Create LLMCall instance with existing interactions on stack
        llm_call = AskOracle(
            stack=mock_stack, prompt=sample_prompt, template_inputs={}
        )
        mock_stack.interactions.append(llm_call)

        # Execute step
        result = llm_call.step()

        # Verify step completed
        assert result is True

    def test_llm_call_registration(self):
        """Test that AskOracle is properly registered."""
        # This tests the @register decorator
        from gimle.hugin.interaction.interaction import Interaction

        # Check if AskOracle is in registered interactions
        assert "AskOracle" in Interaction._registry
        assert Interaction._registry["AskOracle"] == AskOracle
        assert AskOracle.__name__ == "AskOracle"


class TestLLMCallIntegration:
    """Integration tests for LLMCall with mocked dependencies."""

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_llm_call_full_workflow(
        self, mock_chat_completion, mock_stack, mock_agent, sample_prompt
    ):
        """Test the full workflow of LLMCall."""
        # Setup mock response
        mock_response = {
            "role": "assistant",
            "content": "This is a test response from the LLM",
            "input_tokens": 15,
            "output_tokens": 8,
        }
        mock_chat_completion.return_value = mock_response

        # Create and configure LLMCall
        llm_call = AskOracle(
            stack=mock_stack,
            prompt=sample_prompt,
            template_inputs={"question": "What is the weather like?"},
        )

        # Execute step
        success = llm_call.step()

        # Verify success
        assert success is True

        # Verify chat_completion was called with correct parameters
        mock_chat_completion.assert_called_once()
        call_args = mock_chat_completion.call_args
        assert call_args[1]["messages"] == []
        assert call_args[1]["tools"] == []
        assert call_args[1]["llm_model"] == "test-model"

        # Verify interaction was added to stack
        assert len(mock_stack.interactions) == 1
        interaction = mock_stack.interactions[0]
        assert isinstance(interaction, OracleResponse)
        assert interaction.response == mock_response

    @patch("gimle.hugin.llm.completion.chat_completion")
    def test_llm_call_multiple_steps(
        self, mock_chat_completion, mock_stack, sample_prompt
    ):
        """Test multiple steps of LLMCall."""
        # Setup mock responses
        responses = [
            {
                "role": "assistant",
                "content": "First response",
                "tool_call_id": "call_1",
                "tool_call": "search_tool",
            },
            {
                "role": "assistant",
                "content": "Second response",
                "tool_call_id": "call_2",
                "tool_call": "calculate_tool",
            },
        ]
        mock_chat_completion.side_effect = responses

        # Create a task definition
        task_definition = TaskDefinition(
            stack=mock_stack,
            task=Task(
                name="test-task",
                description="Test task",
                parameters={},
                prompt="Test prompt",
            ),
        )
        mock_stack.add_interaction(task_definition)

        # Create first LLMCall
        llm_call1 = AskOracle(
            stack=mock_stack, prompt=sample_prompt, template_inputs={}
        )

        # Execute first step
        result1 = llm_call1.step()
        assert result1 is True
        assert len(mock_stack.interactions) == 2

        # Create second LLMCall
        llm_call2 = AskOracle(
            stack=mock_stack, prompt=sample_prompt, template_inputs={}
        )

        # Execute second step
        result2 = llm_call2.step()
        assert result2 is True
        assert len(mock_stack.interactions) == 3

        # Verify both responses were captured
        assert mock_stack.interactions[1].response == responses[0]
        assert mock_stack.interactions[2].response == responses[1]
