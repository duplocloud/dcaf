"""
Runtime Adapter Protocol - The contract for LLM framework adapters.

All framework adapters (Agno, Strands, LangChain, etc.) must implement
this protocol. This enables the plugin-style architecture where new
frameworks can be added without modifying the Agent class.

Convention:
    Each adapter module must:
    1. Be located at: dcaf/core/adapters/outbound/{framework_name}/
    2. Export a create_adapter(**kwargs) function in __init__.py
    3. Return an adapter that implements RuntimeAdapter

Example:
    # dcaf/core/adapters/outbound/strands/__init__.py
    def create_adapter(**kwargs):
        from .adapter import StrandsAdapter
        return StrandsAdapter(**kwargs)
"""

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dcaf.core.events import EventRegistry


@runtime_checkable
class RuntimeAdapter(Protocol):
    """
    Protocol that all framework adapters must implement.

    This is the contract between DCAF's Agent class and any LLM framework.
    Implementing this protocol allows seamless swapping of frameworks.

    All methods are async since DCAF runs in FastAPI's async context.

    Required Methods:
        invoke: Async request/response
        invoke_stream: Async streaming response (async generator)

    Properties:
        model_id: The model being used
        provider: The provider (for frameworks that support multiple)
    """

    @property
    def model_id(self) -> str:
        """Get the model identifier."""
        ...

    @property
    def provider(self) -> str:
        """Get the provider name."""
        ...

    async def invoke(
        self,
        messages: list[Any],
        tools: list[Any],
        system_prompt: str | None = None,
        static_system: str | None = None,
        dynamic_system: str | None = None,
        platform_context: dict[str, Any] | None = None,
    ) -> Any:  # Returns AgentResponse
        """
        Execute a single request and return the response.

        Args:
            messages: List of conversation messages
            tools: List of tools available to the agent
            system_prompt: Optional system instructions
            static_system: Static portion of system prompt (for caching)
            dynamic_system: Dynamic portion of system prompt (not cached)
            platform_context: Optional platform context to inject into tools

        Returns:
            AgentResponse with the result
        """
        ...

    def invoke_stream(
        self,
        messages: list[Any],
        tools: list[Any],
        system_prompt: str | None = None,
        static_system: str | None = None,
        dynamic_system: str | None = None,
        platform_context: dict[str, Any] | None = None,
        event_registry: "EventRegistry | None" = None,
    ) -> AsyncGenerator[Any, None]:  # Yields StreamEvent
        """
        Execute with async streaming response.

        Note: Implementations should be async generators (async def with yield).
        The Protocol signature omits 'async' for mypy compatibility.

        Args:
            messages: List of conversation messages
            tools: List of tools available to the agent
            system_prompt: Optional system instructions
            static_system: Static portion of system prompt (for caching)
            dynamic_system: Dynamic portion of system prompt (not cached)
            platform_context: Optional platform context to inject into tools
            event_registry: Optional event registry for subscription-based events

        Yields:
            StreamEvent objects
        """
        ...
