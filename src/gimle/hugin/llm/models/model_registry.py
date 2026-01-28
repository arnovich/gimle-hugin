"""Model registry module."""

from functools import lru_cache
from typing import Dict, List, Optional

from .model import Model

# Model metadata for provider grouping
MODEL_PROVIDERS: Dict[str, str] = {
    # Anthropic models
    "haiku-latest": "anthropic",
    "sonnet-latest": "anthropic",
    "opus-latest": "anthropic",
    # OpenAI models
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "gpt-4.1-nano": "openai",
    "gpt-4.1-mini": "openai",
    "gpt-5-nano": "openai",
    "gpt-5.2": "openai",
    # Ollama models
    "qwen3:8b": "ollama",
    "llama3.1-8b": "ollama",
    "qwen2.5-0.5b": "ollama",
    "llama3.2-latest": "ollama",
    "qwen3-14b": "ollama",
    "qwen3-30b-a3b": "ollama",
    "llama3.3-70b": "ollama",
    "mistral-small3.2": "ollama",
}


class ModelRegistry:
    """Registry for LLM models."""

    def __init__(self) -> None:
        """Initialize the model registry."""
        self.models: Dict[str, Model] = {}

    def register_model(self, model_name: str, model: Model) -> None:
        """Register a model with the given name."""
        self.models[model_name] = model

    def get_model(self, model_name: str) -> Model:
        """Get a model by name."""
        if model_name not in self.models:
            raise ValueError(f"Model {model_name} not found")
        return self.models[model_name]

    def get_models_by_provider(self, provider: str) -> List[str]:
        """Get all registered model names for a given provider."""
        return [
            name
            for name, prov in MODEL_PROVIDERS.items()
            if prov == provider and name in self.models
        ]

    def get_provider(self, model_name: str) -> Optional[str]:
        """Get the provider for a model name."""
        return MODEL_PROVIDERS.get(model_name)


@lru_cache(maxsize=1)
def get_model_registry() -> ModelRegistry:
    """Get the global model registry instance."""
    from .anthropic import AnthropicModel
    from .ollama import OllamaModel
    from .openai import OpenAIModel

    model_registry = ModelRegistry()

    # Anthropic models
    model_registry.register_model(
        "haiku-latest",
        AnthropicModel(
            model_name="claude-haiku-4-5",
        ),
    )
    model_registry.register_model(
        "sonnet-latest",
        AnthropicModel(
            model_name="claude-sonnet-4-5",
        ),
    )
    model_registry.register_model(
        "opus-latest",
        AnthropicModel(
            model_name="claude-opus-4-5",
        ),
    )

    # OpenAI models
    model_registry.register_model(
        "gpt-4o",
        OpenAIModel(
            model_name="gpt-4o",
        ),
    )
    model_registry.register_model(
        "gpt-4o-mini",
        OpenAIModel(
            model_name="gpt-4o-mini",
        ),
    )

    model_registry.register_model(
        "gpt-4.1-nano",
        OpenAIModel(
            model_name="gpt-4.1-nano",
        ),
    )
    model_registry.register_model(
        "gpt-4.1-mini",
        OpenAIModel(
            model_name="gpt-4.1-mini",
        ),
    )
    model_registry.register_model(
        "gpt-5-nano",
        OpenAIModel(
            model_name="gpt-5-nano",
            temperature=None,
        ),
    )
    model_registry.register_model(
        "gpt-5.2",
        OpenAIModel(
            model_name="gpt-5.2",
            temperature=None,
        ),
    )

    # Ollama models
    # PRIMARY RECOMMENDATION: qwen3:8b - best tool calling performance
    model_registry.register_model(
        "qwen3:8b",
        OllamaModel(
            model_name="qwen3:8b",
            strict_tool_calling=True,
            timeout_seconds=120,
        ),
    )
    model_registry.register_model(
        "llama3.1-8b",
        OllamaModel(
            model_name="llama3.1:8b",
            strict_tool_calling=True,
            timeout_seconds=120,
        ),
    )
    model_registry.register_model(
        "qwen2.5-0.5b",
        OllamaModel(
            model_name="qwen2.5:0.5b",
            strict_tool_calling=True,
            timeout_seconds=30,
        ),
    )
    model_registry.register_model(
        "llama3.2-latest",
        OllamaModel(
            model_name="llama3.2:latest",
            strict_tool_calling=True,
            timeout_seconds=120,
        ),
    )
    model_registry.register_model(
        "qwen3-14b",
        OllamaModel(
            model_name="qwen3:14b",
            strict_tool_calling=True,
            timeout_seconds=120,
        ),
    )
    model_registry.register_model(
        "qwen3-30b-a3b",
        OllamaModel(
            model_name="qwen3:30b-a3b",
            strict_tool_calling=True,
            timeout_seconds=120,
        ),
    )
    model_registry.register_model(
        "llama3.3-70b",
        OllamaModel(
            model_name="llama3.3:70b",
            strict_tool_calling=True,
            timeout_seconds=300,
        ),
    )
    model_registry.register_model(
        "mistral-small3.2",
        OllamaModel(
            model_name="mistral-small3.2",
            strict_tool_calling=True,
            timeout_seconds=300,
        ),
    )

    return model_registry
