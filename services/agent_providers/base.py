"""
Base Agent Provider Interface

Defines the contract that all agent framework providers must implement.
This allows us to swap between Agno, Strands, or other frameworks without
changing business logic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class ToolDefinition:
    """
    Framework-agnostic tool definition.

    Represents a tool that the agent can call, regardless of the
    underlying framework's native format.
    """
    name: str
    description: str
    function: Callable
    parameters: Optional[dict] = None


@dataclass
class AgentResponse:
    """
    Framework-agnostic agent response.

    Normalizes responses from different frameworks into a consistent format.
    """
    content: str
    metadata: dict[str, Any]
    tool_calls: list[dict[str, Any]] | None = None
    metrics: Optional[dict] = None

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []


class AgentProvider(ABC):
    """
    Abstract base class for agent framework providers.

    Any agent framework (Agno, Strands, LangChain, etc.) must implement
    this interface to be used in our application.

    Benefits:
    - Dependency Inversion: Business logic depends on abstraction, not concrete frameworks
    - Easy Testing: Mock the provider for unit tests
    - Framework Migration: Swap providers without changing business logic
    - Multi-Provider: Run A/B tests with different frameworks
    """

    @abstractmethod
    async def initialize_agent(
        self,
        system_prompt: str,
        tools: list[ToolDefinition],
        message_history: list[dict],
        **kwargs
    ) -> Any:
        """
        Initialize an agent with the given configuration.

        Args:
            system_prompt: Instructions for the agent
            tools: List of tools the agent can use
            message_history: Previous conversation messages
            **kwargs: Provider-specific configuration

        Returns:
            Provider-specific agent instance (opaque to caller)
        """
        pass

    @abstractmethod
    async def run_agent(
        self,
        agent: Any,
        user_message: str,
        **kwargs
    ) -> AgentResponse:
        """
        Execute the agent with a user message.

        Args:
            agent: Agent instance from initialize_agent()
            user_message: User's input message
            **kwargs: Provider-specific run options

        Returns:
            AgentResponse: Normalized response object
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Get the name of this provider (e.g., "agno", "strands").

        Returns:
            str: Provider identifier
        """
        pass

    @abstractmethod
    def get_provider_version(self) -> str:
        """
        Get the version of the underlying framework.

        Returns:
            str: Framework version
        """
        pass

    def supports_streaming(self) -> bool:
        """
        Check if this provider supports streaming responses.

        Returns:
            bool: True if streaming is supported
        """
        return False

    def supports_reasoning(self) -> bool:
        """
        Check if this provider supports explicit reasoning modes.

        Returns:
            bool: True if reasoning is supported
        """
        return False

    async def cleanup(self):
        """
        Clean up any resources held by the provider.

        Called when the provider is no longer needed (e.g., app shutdown).
        Override if your provider needs cleanup (close connections, etc.).
        """
        pass


