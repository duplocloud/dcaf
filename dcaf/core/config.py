"""
Configuration management for DCAF.

This module provides centralized configuration loading from environment variables,
allowing provider settings (Bedrock, Gemini, Anthropic, etc.) to be driven by
environment rather than hardcoded in application code.

Example .env file (Google on GCP):
    DCAF_PROVIDER=google
    DCAF_MODEL=gemini-2.5-pro
    # Project/location auto-detected on GCP!

Example usage:
    from dcaf.core import Agent
    from dcaf.core.config import load_agent_config

    # Load all config from environment
    config = load_agent_config()
    agent = Agent(**config)
"""

import logging
import os
from typing import Any

from .adapters.outbound.agno.types import (
    DEFAULT_AWS_REGION,
    DEFAULT_FRAMEWORK,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL_ID,
    DEFAULT_PROVIDER,
    DEFAULT_TEMPERATURE,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Default Configuration
# ============================================================================

DEFAULTS = {
    "provider": DEFAULT_PROVIDER,
    "model": DEFAULT_MODEL_ID,
    "framework": DEFAULT_FRAMEWORK,
    "temperature": DEFAULT_TEMPERATURE,
    "max_tokens": DEFAULT_MAX_TOKENS,
    "aws_region": DEFAULT_AWS_REGION,
}

# Provider-specific model defaults
PROVIDER_MODEL_DEFAULTS = {
    "bedrock": "anthropic.claude-3-sonnet-20240229-v1:0",
    "anthropic": "claude-3-sonnet-20240229",
    "google": "gemini-3-flash",
    "openai": "gpt-4",
    "azure": "gpt-4",
    "ollama": "llama2",
}


# ============================================================================
# Environment Variable Names
# ============================================================================


class EnvVars:
    """Environment variable names used by DCAF."""

    # Core configuration
    PROVIDER = "DCAF_PROVIDER"
    MODEL = "DCAF_MODEL"
    FRAMEWORK = "DCAF_FRAMEWORK"
    TEMPERATURE = "DCAF_TEMPERATURE"
    MAX_TOKENS = "DCAF_MAX_TOKENS"

    # AWS Bedrock
    AWS_PROFILE = "AWS_PROFILE"
    AWS_REGION = "AWS_REGION"
    AWS_ACCESS_KEY_ID = "AWS_ACCESS_KEY_ID"
    AWS_SECRET_ACCESS_KEY = "AWS_SECRET_ACCESS_KEY"

    # API Keys (non-AWS providers)
    ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
    OPENAI_API_KEY = "OPENAI_API_KEY"
    AZURE_OPENAI_API_KEY = "AZURE_OPENAI_API_KEY"

    # Google Vertex AI
    GOOGLE_PROJECT_ID = "GOOGLE_CLOUD_PROJECT"  # Auto-detected on GCP
    GOOGLE_MODEL_LOCATION = (
        "DCAF_GOOGLE_MODEL_LOCATION"  # Where Gemini models run (default: us-central1)
    )

    # A2A Identity
    AGENT_NAME = "DCAF_AGENT_NAME"
    AGENT_DESCRIPTION = "DCAF_AGENT_DESCRIPTION"

    # Behavior flags
    TOOL_CALL_LIMIT = "DCAF_TOOL_CALL_LIMIT"
    DISABLE_HISTORY = "DCAF_DISABLE_HISTORY"
    DISABLE_TOOL_FILTERING = "DCAF_DISABLE_TOOL_FILTERING"


# ============================================================================
# Configuration Loading
# ============================================================================


def get_env(key: str, default: Any = None, cast: type = str) -> Any:
    """
    Get environment variable with type casting.

    Args:
        key: Environment variable name
        default: Default value if not set
        cast: Type to cast to (str, int, float, bool)

    Returns:
        Value from environment or default
    """
    value = os.getenv(key)

    if value is None:
        return default

    if cast is bool:
        return value.lower() in ("true", "1", "yes", "on")
    elif cast in (int, float):
        try:
            return cast(value)
        except (ValueError, TypeError):
            logger.warning(
                f"Invalid {cast.__name__} value for {key}: {value}, using default: {default}"
            )
            return default

    return value


def load_agent_config(
    provider: str | None = None, model: str | None = None, **overrides: Any
) -> dict[str, Any]:
    """
    Load agent configuration from environment variables.

    This function loads all agent configuration from environment variables,
    with sensible defaults. You can override any value by passing it as a
    keyword argument.

    Args:
        provider: Override provider (default: from DCAF_PROVIDER env var)
        model: Override model (default: from DCAF_MODEL env var)
        **overrides: Any other Agent() parameters to override

    Returns:
        Dictionary of configuration suitable for Agent(**config)

    Example:
        # Load everything from environment
        config = load_agent_config()
        agent = Agent(tools=[my_tool], **config)

        # Override specific values
        config = load_agent_config(provider="google", model="gemini-3-flash")
        agent = Agent(**config)

    Environment Variables:
        Core:
            DCAF_PROVIDER - Provider name (bedrock, google, anthropic, etc.)
            DCAF_MODEL - Model identifier
            DCAF_FRAMEWORK - LLM framework (default: agno)
            DCAF_TEMPERATURE - Sampling temperature (0.0-1.0)
            DCAF_MAX_TOKENS - Maximum output tokens

        AWS (for provider=bedrock):
            AWS_PROFILE - AWS credentials profile name
            AWS_REGION - AWS region
            AWS_ACCESS_KEY_ID - AWS access key
            AWS_SECRET_ACCESS_KEY - AWS secret key

        API Keys (for other providers):
            ANTHROPIC_API_KEY - For provider=anthropic
            OPENAI_API_KEY - For provider=openai
            AZURE_OPENAI_API_KEY - For provider=azure

        Google Vertex AI:
            GOOGLE_CLOUD_PROJECT - Google Cloud project ID (auto-detected on GCP)
            DCAF_GOOGLE_MODEL_LOCATION - Region for Gemini models (default: us-central1)

        A2A:
            DCAF_AGENT_NAME - Agent name for A2A protocol
            DCAF_AGENT_DESCRIPTION - Agent description

        Behavior:
            DCAF_TOOL_CALL_LIMIT - Max concurrent tool calls
            DCAF_DISABLE_HISTORY - Disable message history
            DCAF_DISABLE_TOOL_FILTERING - Disable tool message filtering
    """
    config: dict[str, Any] = {}

    # Provider (required)
    config["provider"] = provider or get_env(EnvVars.PROVIDER) or DEFAULTS["provider"]

    # Model (auto-detect based on provider if not specified)
    config["model"] = (
        model
        or get_env(EnvVars.MODEL)
        or PROVIDER_MODEL_DEFAULTS.get(config["provider"])
        or DEFAULTS["model"]
    )

    # Framework
    config["framework"] = get_env(EnvVars.FRAMEWORK, DEFAULTS["framework"])

    # Model parameters
    config["temperature"] = get_env(EnvVars.TEMPERATURE, DEFAULTS["temperature"], cast=float)
    config["max_tokens"] = get_env(EnvVars.MAX_TOKENS, DEFAULTS["max_tokens"], cast=int)

    # AWS configuration (for Bedrock)
    if config["provider"] == "bedrock":
        if profile := get_env(EnvVars.AWS_PROFILE):
            config["aws_profile"] = profile
        if region := get_env(EnvVars.AWS_REGION):
            config["aws_region"] = region
        if access_key := get_env(EnvVars.AWS_ACCESS_KEY_ID):
            config["aws_access_key"] = access_key
        if secret_key := get_env(EnvVars.AWS_SECRET_ACCESS_KEY):
            config["aws_secret_key"] = secret_key

    # API keys (for non-AWS providers)
    else:
        api_key = None

        if config["provider"] == "anthropic":
            api_key = get_env(EnvVars.ANTHROPIC_API_KEY)
        elif config["provider"] == "google":
            # Google always uses Vertex AI (auto-detects project/location on GCP)
            if project_id := get_env(EnvVars.GOOGLE_PROJECT_ID):
                config["google_project_id"] = project_id
            if location := get_env(EnvVars.GOOGLE_MODEL_LOCATION):
                config["google_location"] = location

        elif config["provider"] == "openai":
            api_key = get_env(EnvVars.OPENAI_API_KEY)
        elif config["provider"] == "azure":
            api_key = get_env(EnvVars.AZURE_OPENAI_API_KEY)

        if api_key:
            config["api_key"] = api_key

    # A2A identity
    if name := get_env(EnvVars.AGENT_NAME):
        config["name"] = name
    if description := get_env(EnvVars.AGENT_DESCRIPTION):
        config["description"] = description

    # Behavior flags
    if tool_limit := get_env(EnvVars.TOOL_CALL_LIMIT, cast=int):
        config["tool_call_limit"] = tool_limit
    if disable_history := get_env(EnvVars.DISABLE_HISTORY, cast=bool):
        config["disable_history"] = disable_history
    if disable_filtering := get_env(EnvVars.DISABLE_TOOL_FILTERING, cast=bool):
        config["disable_tool_filtering"] = disable_filtering

    # Apply overrides
    config.update(overrides)

    # Log configuration (without sensitive data)
    _log_config(config)

    return config


def _log_config(config: dict[str, Any]) -> None:
    """Log configuration without sensitive values."""
    safe_config = {
        k: v for k, v in config.items() if k not in ("api_key", "aws_access_key", "aws_secret_key")
    }

    # Redact AWS profile name (might contain sensitive info)
    if "aws_profile" in safe_config:
        safe_config["aws_profile"] = "***"

    logger.info(f"Loaded agent configuration: {safe_config}")


def get_provider_from_env() -> str:
    """
    Get the provider from environment.

    Returns:
        Provider name (bedrock, google, anthropic, etc.)
    """
    result = get_env(EnvVars.PROVIDER, DEFAULTS["provider"])
    return str(result) if result is not None else str(DEFAULTS["provider"])


def get_model_from_env(provider: str | None = None) -> str:
    """
    Get the model from environment.

    Args:
        provider: Provider name (auto-detects if not specified)

    Returns:
        Model identifier
    """
    if not provider:
        provider = get_provider_from_env()

    result = get_env(EnvVars.MODEL) or PROVIDER_MODEL_DEFAULTS.get(provider) or DEFAULTS["model"]
    return str(result)


def is_provider_configured(provider: str) -> bool:
    """
    Check if a provider has required credentials configured.

    Args:
        provider: Provider name to check

    Returns:
        True if provider credentials are available
    """
    if provider == "bedrock":
        # Check for AWS credentials
        return bool(
            get_env(EnvVars.AWS_PROFILE)
            or (get_env(EnvVars.AWS_ACCESS_KEY_ID) and get_env(EnvVars.AWS_SECRET_ACCESS_KEY))
        )
    elif provider == "anthropic":
        return bool(get_env(EnvVars.ANTHROPIC_API_KEY))
    elif provider == "google":
        # Google always uses Vertex AI - credentials auto-detected via ADC on GCP
        # Just need provider and model set, everything else is auto-detected
        return True
    elif provider == "openai":
        return bool(get_env(EnvVars.OPENAI_API_KEY))
    elif provider == "azure":
        return bool(get_env(EnvVars.AZURE_OPENAI_API_KEY))
    elif provider == "ollama":
        return True  # Ollama doesn't need credentials

    return False


def get_configured_provider() -> str | None:
    """
    Get the first configured provider with credentials.

    Returns:
        Provider name if credentials found, None otherwise
    """
    providers = ["bedrock", "google", "anthropic", "openai", "azure", "ollama"]

    for provider in providers:
        if is_provider_configured(provider):
            return provider

    return None


# ============================================================================
# Legacy Support
# ============================================================================


def load_aws_config() -> dict[str, Any]:
    """
    Load AWS configuration for backwards compatibility.

    Returns:
        Dictionary with AWS credentials
    """
    config = {}

    if profile := get_env(EnvVars.AWS_PROFILE):
        config["aws_profile"] = profile
    if region := get_env(EnvVars.AWS_REGION):
        config["aws_region"] = region
    if access_key := get_env(EnvVars.AWS_ACCESS_KEY_ID):
        config["aws_access_key"] = access_key
    if secret_key := get_env(EnvVars.AWS_SECRET_ACCESS_KEY):
        config["aws_secret_key"] = secret_key

    return config
