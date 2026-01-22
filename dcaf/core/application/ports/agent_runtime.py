"""AgentRuntime port - interface for LLM framework adapters."""

from collections.abc import AsyncGenerator
from typing import Protocol, runtime_checkable

from ...domain.entities import Message
from ..dto.responses import AgentResponse, StreamEvent


class ToolLike(Protocol):
    """Protocol for tool-like objects."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def requires_approval(self) -> bool: ...


@runtime_checkable
class AgentRuntime(Protocol):
    """
    Outbound port for LLM framework adapters.

    This protocol defines the interface that framework adapters
    (Agno, LangChain, Strands, etc.) must implement to integrate
    with the DCAF application layer.

    All methods are async since DCAF runs in FastAPI's async context.

    Implementations:
        - AgnoAdapter: For Agno framework
        - LangChainAdapter: For LangChain framework
        - BedrockDirectAdapter: For direct Bedrock access

    Example:
        class AgnoAdapter(AgentRuntime):
            async def invoke(self, messages, tools) -> AgentResponse:
                # Convert to Agno format
                # Call Agno SDK
                # Convert response back
                pass
    """

    async def invoke(
        self,
        messages: list[Message],
        tools: list[ToolLike],
        system_prompt: str | None = None,
        platform_context: dict | None = None,
        static_system: str | None = None,
        dynamic_system: str | None = None,
    ) -> AgentResponse:
        """
        Invoke the agent with messages and tools.

        Args:
            messages: List of messages in the conversation
            tools: List of tools available to the agent
            system_prompt: Optional system prompt to prepend
            platform_context: Optional platform context dict containing:
                - tenant_id, tenant_name: Tenant identification
                - k8s_namespace, kubeconfig: Kubernetes context
                - duplo_base_url, duplo_token: DuploCloud credentials
                - aws_region: AWS configuration
                - user_id: User identifier for tracing
                - session_id: Session identifier for grouping runs
                - run_id: Unique execution run identifier
                - request_id: HTTP request correlation ID
            static_system: Optional static system prompt part (for caching)
            dynamic_system: Optional dynamic system prompt part (for caching)

        Returns:
            AgentResponse containing the agent's response and any tool calls
        """
        ...

    def invoke_stream(
        self,
        messages: list[Message],
        tools: list[ToolLike],
        system_prompt: str | None = None,
        platform_context: dict | None = None,
        static_system: str | None = None,
        dynamic_system: str | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Invoke the agent with streaming response.

        Yields StreamEvent objects as the response is generated.

        Note: Implementations should be async generators (async def with yield).
        The Protocol signature omits 'async' for mypy compatibility with async generators.

        Args:
            messages: List of messages in the conversation
            tools: List of tools available to the agent
            system_prompt: Optional system prompt to prepend
            platform_context: Optional platform context dict containing:
                - tenant_id, tenant_name: Tenant identification
                - k8s_namespace, kubeconfig: Kubernetes context
                - duplo_base_url, duplo_token: DuploCloud credentials
                - aws_region: AWS configuration
                - user_id: User identifier for tracing
                - session_id: Session identifier for grouping runs
                - run_id: Unique execution run identifier
                - request_id: HTTP request correlation ID
            static_system: Optional static system prompt part (for caching)
            dynamic_system: Optional dynamic system prompt part (for caching)

        Yields:
            StreamEvent objects containing chunks of the response
        """
        ...
