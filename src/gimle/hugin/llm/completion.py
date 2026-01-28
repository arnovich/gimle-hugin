"""Chat completion."""

import logging
from typing import Any, Dict, List

from ..tools.tool import Tool
from .models.model_registry import get_model_registry
from .models.provider_utils import ensure_credentials_loaded


def make_completion_cache_key(prefix: str, params: Dict[str, Any]) -> str:
    """Make a completion cache key."""
    nearest_context_window = 5
    if "messages" in params:
        shortened_messages = params["messages"][:2]
        if len(params["messages"]) > 2:
            start_index = -(
                min(nearest_context_window, len(params["messages"]) - 2)
            )
            shortened_messages += params["messages"][start_index:]
        params["messages"] = shortened_messages
    return f"{prefix}{'_'.join([f'{k}={v}' for k, v in params.items()])}"


# TODO would be good to cache this at some point
# would also allow for local playback
# use make_completion_cache_key with messages, llm_model and system_prompt as params
def chat_completion(
    system_prompt: str,
    messages: List[Dict[str, Any]],
    tools: List[Tool],
    llm_model: str,
) -> dict:
    """Chat completion."""
    logging.debug(f"Chat completion using {llm_model} model")

    # Temporarily suppress noisy third-party library logging during LLM call
    third_party_loggers = ["httpcore", "httpx", "anthropic"]
    original_levels = {}
    for logger_name in third_party_loggers:
        lib_logger = logging.getLogger(logger_name)
        # Store current effective level (handles NOTSET/inherited levels)
        original_levels[logger_name] = lib_logger.getEffectiveLevel()
        lib_logger.setLevel(logging.WARNING)

    try:
        model_registry = get_model_registry()
        model = model_registry.get_model(llm_model)
        provider = model_registry.get_provider(llm_model)
        if provider:
            ensure_credentials_loaded(provider)
        return model.chat_completion(system_prompt, messages, tools).to_dict()
    finally:
        # Restore original log levels
        for logger_name, original_level in original_levels.items():
            lib_logger = logging.getLogger(logger_name)
            lib_logger.setLevel(original_level)
