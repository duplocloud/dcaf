"""
Agno Adapter Module.

This module contains ALL Agno-specific code for the DCAF framework.
It provides an implementation of the RuntimeAdapter protocol using the Agno SDK.

The Agno SDK (https://docs.agno.com/) provides a unified interface for
multiple LLM providers including AWS Bedrock, Anthropic, OpenAI, and more.

Components:
    - AgnoAdapter: Implements RuntimeAdapter protocol
    - AgnoToolConverter: Converts dcaf Tools to Agno format
    - AgnoMessageConverter: Converts messages bidirectionally
    - create_adapter: Factory function for dynamic loading

Usage:
    from dcaf.core.adapters.outbound.agno import AgnoAdapter
    
    adapter = AgnoAdapter(
        model_id="anthropic.claude-3-sonnet",
        provider="bedrock",
        aws_profile="production",
    )
    
    response = adapter.invoke(messages, tools)

Dynamic Loading:
    The create_adapter() function enables convention-based discovery:
    
    from dcaf.core.adapters.loader import load_adapter
    adapter = load_adapter("agno", model_id="...", provider="bedrock")
"""

from .adapter import AgnoAdapter
from .tool_converter import AgnoToolConverter
from .message_converter import AgnoMessageConverter


def create_adapter(**kwargs) -> AgnoAdapter:
    """
    Factory function for creating an AgnoAdapter.
    
    This function is REQUIRED by the adapter loader convention.
    It enables dynamic discovery and loading of this adapter.
    
    Args:
        **kwargs: Passed directly to AgnoAdapter constructor:
            - model_id: Model identifier (e.g., "anthropic.claude-3-sonnet...")
            - provider: Provider name ("bedrock", "anthropic", "openai", "google", etc.)
            - aws_profile: AWS profile name (for Bedrock)
            - aws_region: AWS region (for Bedrock)
            - api_key: API key (for non-AWS providers)
            - vertexai: Use Google Vertex AI (for service account auth)
            - google_project_id: Google Cloud project ID (for Vertex AI)
            - google_location: Google Cloud region (for Vertex AI)
            - max_tokens: Maximum response tokens
            - temperature: Sampling temperature
            
    Returns:
        Configured AgnoAdapter instance
        
    Example:
        adapter = create_adapter(
            model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            provider="bedrock",
            aws_profile="production",
        )
    """
    return AgnoAdapter(**kwargs)


__all__ = [
    "AgnoAdapter",
    "AgnoToolConverter",
    "AgnoMessageConverter",
    "create_adapter",
]
