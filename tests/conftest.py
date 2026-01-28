"""Pytest configuration and fixtures."""

from typing import Any, Dict, List

import pytest

# Import tools package to ensure finish tool is registered
import gimle.hugin.tools  # noqa: F401
from gimle.hugin.agent.config import Config
from gimle.hugin.llm.models.model import Model, ModelResponse
from gimle.hugin.llm.models.model_registry import ModelRegistry
from gimle.hugin.storage.local import LocalStorage

# Import mock dependencies first
from .mock_dependencies import MockTool


class MockModel(Model):
    """Mock model for testing without actual LLM calls."""

    def __init__(
        self, config: Dict[str, Any], mock_response: Dict[str, Any] = None
    ):
        """Initialize the mock model."""
        super().__init__(config)
        self.mock_response = mock_response or {
            "role": "assistant",
            "content": "This is a mock response",
            "input_tokens": 10,
            "output_tokens": 5,
        }
        self.call_count = 0

    def chat_completion(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Any] = None,
    ) -> ModelResponse:
        """Mock implementation that returns a predefined response."""
        self.call_count += 1
        # Simulate some processing time
        import time

        time.sleep(0.001)

        return ModelResponse(
            role=self.mock_response["role"],
            content=self.mock_response["content"],
            input_tokens=self.mock_response.get("input_tokens"),
            output_tokens=self.mock_response.get("output_tokens"),
            extra_content={
                "call_count": self.call_count,
                "system_prompt": system_prompt,
                "message_count": len(messages),
                "tool_count": len(tools) if tools else 0,
            },
        )


@pytest.fixture
def mock_model_config():
    """Return standard configuration for mock models."""
    return {
        "model": "test-model",
        "temperature": 0.7,
        "max_tokens": 1000,
        "tool_choice": {"type": "auto"},
    }


@pytest.fixture
def mock_model(mock_model_config):
    """Create a mock model instance."""
    return MockModel(mock_model_config)


@pytest.fixture
def mock_model_with_custom_response(mock_model_config):
    """Create a mock model with custom response."""
    custom_response = {
        "role": "assistant",
        "content": "Custom mock response",
        "input_tokens": 20,
        "output_tokens": 10,
    }
    return MockModel(mock_model_config, custom_response)


@pytest.fixture
def model_registry():
    """Create a fresh model registry for testing."""
    return ModelRegistry()


@pytest.fixture
def sample_messages():
    """Sample messages for testing."""
    return [
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I'm doing well, thank you!"},
        {"role": "user", "content": "What's the weather like?"},
    ]


@pytest.fixture
def sample_tools():
    """Sample tools for testing."""
    tool1 = MockTool(
        name="get_weather",
        description="Get current weather information",
        parameters={
            "location": {
                "type": "string",
                "description": "City name",
                "required": True,
            }
        },
    )

    tool2 = MockTool(
        name="calculate",
        description="Perform mathematical calculations",
        parameters={
            "expression": {
                "type": "string",
                "description": "Math expression",
                "required": True,
            }
        },
    )

    return [tool1, tool2]


@pytest.fixture
def sample_system_prompt():
    """Sample system prompt for testing."""
    return "You are a helpful AI assistant. Please respond to user queries."


@pytest.fixture
def mock_session():
    """Create a mock session for testing."""
    from gimle.hugin.agent.environment import Environment
    from gimle.hugin.agent.session import Session

    environment = Environment(storage=LocalStorage())
    return Session(environment=environment)


@pytest.fixture
def mock_agent(mock_session):
    """Create a mock agent with stack for testing."""
    from unittest.mock import Mock

    from gimle.hugin.agent.agent import Agent

    agent_config = Config(
        llm_model="test-model",
        system_template="system",
        name="test-agent",
        description="Test agent",
    )
    agent = Agent(session=mock_session, config=agent_config)
    # Add agent_type for renderer compatibility
    agent.agent_type = "default"
    # Add agent_registry to session for renderer compatibility
    if not hasattr(mock_session, "agent_registry"):
        mock_session.agent_registry = {
            "default": {"system": "You are a helpful AI assistant."}
        }
    # Environment is already set up with template_registry
    # Add agent_dwh for renderer compatibility
    if not hasattr(mock_session, "agent_dwh"):
        mock_agent_dwh = Mock()
        mock_agent_dwh.dialect = "default"
        mock_session.agent_dwh = mock_agent_dwh
    return agent


@pytest.fixture
def mock_stack(mock_agent):
    """Create a mock stack for testing."""
    return mock_agent.stack


@pytest.fixture
def sample_prompt():
    """Create a sample Prompt object for testing."""
    from gimle.hugin.llm.prompt.prompt import Prompt

    return Prompt(type="text", text="Test prompt")
