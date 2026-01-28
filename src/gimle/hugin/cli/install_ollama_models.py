#!/usr/bin/env python3
"""Install Ollama models from the model registry."""

import argparse
import sys

from ollama import pull

from gimle.hugin.llm.models.model_registry import get_model_registry
from gimle.hugin.llm.models.ollama import OllamaModel


def install_model(registry_name: str, model_name: str) -> bool:
    """Install a single Ollama model.

    Args:
        registry_name: The name used in the model registry
        model_name: The actual Ollama model name to download

    Returns:
        True if successful, False otherwise
    """
    print(
        f"Installing model '{model_name}' (registry name: '{registry_name}')..."
    )
    try:
        # ollama.pull() streams progress, so we iterate through it
        for progress in pull(model_name, stream=True):
            if "status" in progress:
                print(f"  {progress['status']}", end="\r")
            if "completed" in progress and "total" in progress:
                completed = progress.get("completed", 0)
                total = progress.get("total", 0)
                if total > 0:
                    percent = (completed / total) * 100
                    print(
                        f"  Progress: {percent:.1f}% ({completed}/{total})",
                        end="\r",
                    )
        print()  # New line after progress
        print(f"✓ Successfully installed '{model_name}'")
        return True
    except Exception as e:
        print(f"✗ Failed to install '{model_name}': {e}")
        return False


def main() -> int:
    """Install Ollama models from the model registry."""
    parser = argparse.ArgumentParser(
        description="Install Ollama models from the model registry",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Install all Ollama models from the registry
  uv run install-ollama-models

  # Install a specific model by registry name
  uv run install-ollama-models --model qwen3:8b

  # Install a specific model by registry name (alternative format)
  uv run install-ollama-models --model llama3.1-8b
        """,
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Registry name of the model to install (if not specified, installs all Ollama models)",
    )

    args = parser.parse_args()

    # Get the model registry
    registry = get_model_registry()

    # Collect all Ollama models
    ollama_models: dict[str, str] = {}
    for registry_name, model in registry.models.items():
        if isinstance(model, OllamaModel):
            ollama_models[registry_name] = model.model_name

    if not ollama_models:
        print("No Ollama models found in the registry.")
        return 0

    # If a specific model is requested
    if args.model:
        if args.model not in ollama_models:
            print(f"Error: Model '{args.model}' not found in registry.")
            print(f"Available Ollama models: {', '.join(ollama_models.keys())}")
            return 1

        model_name = ollama_models[args.model]
        success = install_model(args.model, model_name)
        return 0 if success else 1

    # Install all Ollama models
    print(f"Found {len(ollama_models)} Ollama model(s) in registry:")
    for registry_name in ollama_models.keys():
        print(f"  - {registry_name}")
    print()

    success_count = 0
    for registry_name, model_name in ollama_models.items():
        if install_model(registry_name, model_name):
            success_count += 1
        print()  # Blank line between models

    print(
        f"Installed {success_count}/{len(ollama_models)} model(s) successfully."
    )
    return 0 if success_count == len(ollama_models) else 1


if __name__ == "__main__":
    sys.exit(main())
