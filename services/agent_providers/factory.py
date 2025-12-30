"""
Agent Provider Factory

Creates the appropriate agent provider based on configuration.
Supports runtime switching between frameworks.
"""

import logging
import os
from typing import Optional

from .agno_provider import AgnoProvider
from .base import AgentProvider
from .strands_provider import StrandsProvider

logger = logging.getLogger(__name__)

# Global provider instance (singleton pattern for performance)
_provider_instance: Optional[AgentProvider] = None
_provider_type: Optional[str] = None


def get_agent_provider(provider_type: Optional[str] = None, force_new: bool = False) -> AgentProvider:
    """
    Get or create an agent provider instance.

    Uses singleton pattern for performance (avoids re-initialization).

    Args:
        provider_type: Which provider to use ("agno", "strands", etc.)
                      If None, reads from AGENT_PROVIDER env var (defaults to "agno")
        force_new: Force creation of a new instance (ignores cache)

    Returns:
        AgentProvider: The requested provider instance

    Raises:
        ValueError: If provider_type is not supported

    Examples:
        # Use default provider (from env or "agno")
        provider = get_agent_provider()

        # Explicitly request Agno
        provider = get_agent_provider("agno")

        # Force new instance (for testing)
        provider = get_agent_provider(force_new=True)
    """
    global _provider_instance, _provider_type

    # Determine which provider to use
    if provider_type is None:
        provider_type = os.getenv("AGENT_PROVIDER", "agno").lower()
    else:
        provider_type = provider_type.lower()

    # Return cached instance if available and type matches
    if not force_new and _provider_instance is not None and _provider_type == provider_type:
        logger.debug(f"Returning cached {provider_type} provider")
        return _provider_instance

    # Create new provider instance
    logger.info(f"Creating new {provider_type} provider")

    if provider_type == "agno":
        _provider_instance = AgnoProvider()
    elif provider_type == "strands":
        _provider_instance = StrandsProvider()
    else:
        raise ValueError(
            f"Unknown agent provider: {provider_type}. "
            f"Supported providers: agno, strands"
        )

    _provider_type = provider_type

    logger.info(
        f"Initialized {provider_type} provider "
        f"(version: {_provider_instance.get_provider_version()})"
    )

    return _provider_instance


def reset_provider():
    """
    Reset the cached provider instance.

    Useful for:
    - Testing (reset between tests)
    - Runtime provider switching
    - Cleanup on shutdown
    """
    global _provider_instance, _provider_type

    if _provider_instance is not None:
        logger.info(f"Resetting {_provider_type} provider")
        # Call cleanup if implemented
        import asyncio
        try:
            asyncio.create_task(_provider_instance.cleanup())
        except Exception as e:
            logger.warning(f"Error during provider cleanup: {e}")

    _provider_instance = None
    _provider_type = None


def list_available_providers() -> list[str]:
    """
    List all available provider implementations.

    Returns:
        list[str]: Names of available providers
    """
    return ["agno", "strands"]


