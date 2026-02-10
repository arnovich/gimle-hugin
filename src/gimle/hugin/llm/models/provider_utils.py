"""Provider detection and credential utilities."""

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ProviderStatus:
    """Status of an LLM provider."""

    name: str
    available: bool
    credential_source: Optional[str] = None  # "env", "dotenv", "local", None
    models: List[str] = field(default_factory=list)
    error: Optional[str] = None
    api_key: Optional[str] = None  # Masked or actual key


def load_dotenv_credentials() -> Dict[str, str]:
    """Load credentials from .env files.

    Checks current directory first, then looks for project root.
    Returns dict of environment variable names to values.
    """
    try:
        from dotenv import dotenv_values
    except ImportError:
        return {}

    env_vars: Dict[str, str] = {}

    # Check current working directory
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        loaded = dotenv_values(cwd_env)
        env_vars.update({k: v for k, v in loaded.items() if v is not None})

    # Check parent directories for project root .env
    current = Path.cwd()
    for _ in range(5):  # Look up to 5 levels
        parent = current.parent
        if parent == current:
            break
        parent_env = parent / ".env"
        if parent_env.exists() and parent_env != cwd_env:
            # Only add keys not already found in cwd
            parent_values = dotenv_values(parent_env)
            for key, value in parent_values.items():
                if key not in env_vars and value is not None:
                    env_vars[key] = value
            break
        current = parent

    return env_vars


def mask_api_key(key: str) -> str:
    """Mask an API key for display, showing first 8 and last 4 chars."""
    if len(key) <= 12:
        return key[:4] + "..." + key[-2:]
    return key[:8] + "..." + key[-4:]


def check_anthropic() -> ProviderStatus:
    """Check Anthropic availability and credentials."""
    # Check environment variable first
    key = os.environ.get("ANTHROPIC_API_KEY")
    source = "env" if key else None

    # If not in env, check dotenv files
    if not key:
        dotenv = load_dotenv_credentials()
        key = dotenv.get("ANTHROPIC_API_KEY")
        source = "dotenv" if key else None

    models = ["sonnet-latest", "haiku-latest", "opus-latest"]

    if key:
        return ProviderStatus(
            name="Anthropic",
            available=True,
            credential_source=source,
            models=models,
            api_key=mask_api_key(key),
        )

    return ProviderStatus(
        name="Anthropic",
        available=False,
        error="ANTHROPIC_API_KEY not found in environment or .env file",
        models=models,
    )


def check_openai() -> ProviderStatus:
    """Check OpenAI availability and credentials."""
    # Check environment variable first
    key = os.environ.get("OPENAI_API_KEY")
    source = "env" if key else None

    # If not in env, check dotenv files
    if not key:
        dotenv = load_dotenv_credentials()
        key = dotenv.get("OPENAI_API_KEY")
        source = "dotenv" if key else None

    models = ["gpt-4o", "gpt-4o-mini"]

    if key:
        return ProviderStatus(
            name="OpenAI",
            available=True,
            credential_source=source,
            models=models,
            api_key=mask_api_key(key),
        )

    return ProviderStatus(
        name="OpenAI",
        available=False,
        error="OPENAI_API_KEY not found in environment or .env file",
        models=models,
    )


def parse_ollama_list(output: str) -> List[str]:
    """Parse ollama list output to get model names."""
    models = []
    lines = output.strip().split("\n")

    # Skip header line
    for line in lines[1:]:
        if line.strip():
            # First column is the model name
            parts = line.split()
            if parts:
                model_name = parts[0]
                # Remove :latest suffix for cleaner display
                if model_name.endswith(":latest"):
                    model_name = model_name[:-7]
                models.append(model_name)

    return models


def check_ollama() -> ProviderStatus:
    """Check Ollama availability and installed models."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            models = parse_ollama_list(result.stdout)
            return ProviderStatus(
                name="Ollama",
                available=True,
                credential_source="local",
                models=models if models else ["(no models installed)"],
            )
    except FileNotFoundError:
        return ProviderStatus(
            name="Ollama",
            available=False,
            error="Ollama not installed (https://ollama.ai)",
            models=[],
        )
    except subprocess.TimeoutExpired:
        return ProviderStatus(
            name="Ollama",
            available=False,
            error="Ollama not responding (is the daemon running?)",
            models=[],
        )

    return ProviderStatus(
        name="Ollama",
        available=False,
        error="Ollama command failed",
        models=[],
    )


def get_ollama_remote_host() -> Optional[str]:
    """Get remote Ollama host from environment or .env files."""
    host = os.environ.get("OLLAMA_REMOTE_HOST")
    if host:
        return host

    dotenv = load_dotenv_credentials()
    return dotenv.get("OLLAMA_REMOTE_HOST")


def check_remote_ollama(host: str) -> ProviderStatus:
    """Check remote Ollama availability and installed models."""
    try:
        from ollama import Client

        # Ensure OLLAMA_API_KEY is loaded from .env
        _load_ollama_api_key()
        client = Client(host=host)
        response = client.list()
        models: List[str] = []
        for model_info in response.models:
            name = model_info.model
            if not name:
                continue
            if name.endswith(":latest"):
                name = name[:-7]
            models.append(name)
        return ProviderStatus(
            name="Ollama (remote)",
            available=True,
            credential_source="remote",
            models=models if models else ["(no models installed)"],
        )
    except ImportError:
        return ProviderStatus(
            name="Ollama (remote)",
            available=False,
            error="ollama Python package not installed",
            models=[],
        )
    except Exception as e:
        return ProviderStatus(
            name="Ollama (remote)",
            available=False,
            error=f"Remote Ollama at {host} not reachable: {e}",
            models=[],
        )


def detect_all_providers(
    remote_ollama_host: Optional[str] = None,
) -> Dict[str, ProviderStatus]:
    """Detect all available providers and their status."""
    providers: Dict[str, ProviderStatus] = {
        "ollama": check_ollama(),
        "anthropic": check_anthropic(),
        "openai": check_openai(),
    }

    host = remote_ollama_host or get_ollama_remote_host()
    if host:
        providers["ollama_remote"] = check_remote_ollama(host)

    return providers


def get_credential_for_provider(provider: str) -> Optional[str]:
    """Get the actual API key for a provider (for setting in environment)."""
    if provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            dotenv = load_dotenv_credentials()
            key = dotenv.get("ANTHROPIC_API_KEY")
        return key
    elif provider == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            dotenv = load_dotenv_credentials()
            key = dotenv.get("OPENAI_API_KEY")
        return key
    elif provider in ("ollama", "ollama_remote"):
        key = os.environ.get("OLLAMA_API_KEY")
        if not key:
            dotenv = load_dotenv_credentials()
            key = dotenv.get("OLLAMA_API_KEY")
        return key
    return None


def ensure_credentials_loaded(provider: str) -> bool:
    """Ensure credentials are loaded into environment for a provider.

    If credentials are found in .env but not in environment, load them.
    Returns True if credentials are available, False otherwise.
    """
    if provider == "ollama":
        # Local Ollama needs no credentials, but load
        # OLLAMA_API_KEY if present (used by remote too).
        _load_ollama_api_key()
        return True

    if provider == "ollama_remote":
        # Remote may need OLLAMA_API_KEY — load if available.
        _load_ollama_api_key()
        return True  # Key is optional; server may be open

    env_var = f"{provider.upper()}_API_KEY"

    # Already in environment
    if os.environ.get(env_var):
        return True

    # Try to load from dotenv
    dotenv = load_dotenv_credentials()
    key = dotenv.get(env_var)
    if key:
        os.environ[env_var] = key
        return True

    return False


def _load_ollama_api_key() -> None:
    """Load OLLAMA_API_KEY from .env into environment if not set.

    The ollama Python Client reads OLLAMA_API_KEY from the
    environment automatically and sends it as a Bearer token.
    """
    if os.environ.get("OLLAMA_API_KEY"):
        return
    dotenv = load_dotenv_credentials()
    key = dotenv.get("OLLAMA_API_KEY")
    if key:
        os.environ["OLLAMA_API_KEY"] = key
