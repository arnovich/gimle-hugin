"""Model registry module."""

import logging
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
    # Ollama cloud models (require OLLAMA_REMOTE_HOST + OLLAMA_API_KEY)
    "qwen3-coder-next-cloud": "ollama_cloud",
    "kimi-k2.5-cloud": "ollama_cloud",
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
    # Auto-register remote Ollama models if configured
    from .provider_utils import _load_ollama_api_key, get_ollama_remote_host

    remote_host = get_ollama_remote_host()
    if remote_host:
        _load_ollama_api_key()
        register_remote_ollama_models(model_registry, remote_host)

        # Ollama cloud models (known large models)
        model_registry.register_model(
            "qwen3-coder-next-cloud",
            OllamaModel(
                model_name="qwen3-coder-next:cloud",
                host=remote_host,
                strict_tool_calling=True,
                timeout_seconds=300,
            ),
        )
        model_registry.register_model(
            "kimi-k2.5-cloud",
            OllamaModel(
                model_name="kimi-k2.5:cloud",
                host=remote_host,
                strict_tool_calling=True,
                timeout_seconds=300,
            ),
        )

    return model_registry


def register_remote_ollama_models(
    registry: ModelRegistry,
    host: str,
    models: Optional[List[str]] = None,
) -> None:
    """Register remote Ollama models in the registry.

    Args:
        registry: The model registry to register models in.
        host: The remote Ollama server URL.
        models: Explicit list of model names. If None, auto-detect
                via the remote server.
    """
    from .ollama import OllamaModel

    if models is None:
        try:
            from ollama import Client

            client = Client(host=host)
            response = client.list()
            models = []
            for model_info in response.models:
                name = model_info.model
                if not name:
                    continue
                if name.endswith(":latest"):
                    name = name[:-7]
                models.append(name)
        except Exception as e:
            logging.warning(
                f"Could not list models from remote Ollama " f"at {host}: {e}"
            )
            return

    for model_name in models:
        registry_name = "remote/" + model_name.replace(":", "-").replace(
            ".", "-"
        )
        registry.register_model(
            registry_name,
            OllamaModel(
                model_name=model_name,
                host=host,
                strict_tool_calling=True,
                timeout_seconds=300,
            ),
        )
        MODEL_PROVIDERS[registry_name] = "ollama_remote"

    if models:
        logging.info(
            f"Registered {len(models)} remote Ollama model(s) " f"from {host}"
        )
