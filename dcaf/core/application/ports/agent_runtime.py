"""AgentRuntime port - interface for LLM framework adapters."""

from typing import Protocol, List, Iterator, Optional, runtime_checkable

from ..dto.responses import AgentResponse, StreamEvent
from ...domain.entities import Message


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
    
    Implementations:
        - AgnoAdapter: For Agno framework
        - LangChainAdapter: For LangChain framework
        - BedrockDirectAdapter: For direct Bedrock access
    
    Example:
        class AgnoAdapter(AgentRuntime):
            def invoke(self, messages, tools) -> AgentResponse:
                # Convert to Agno format
                # Call Agno SDK
                # Convert response back
                pass
    """
    
    def invoke(
        self, 
        messages: List[Message],
        tools: List[ToolLike],
        system_prompt: Optional[str] = None,
    ) -> AgentResponse:
        """
        Invoke the agent with messages and tools.
        
        This is the synchronous entry point for agent execution.
        The implementation should:
        1. Convert messages to framework format
        2. Convert tools to framework format
        3. Call the framework's invoke method
        4. Convert the response back to AgentResponse
        
        Args:
            messages: List of messages in the conversation
            tools: List of tools available to the agent
            system_prompt: Optional system prompt to prepend
            
        Returns:
            AgentResponse containing the agent's response and any tool calls
        """
        ...
    
    def invoke_stream(
        self, 
        messages: List[Message],
        tools: List[ToolLike],
        system_prompt: Optional[str] = None,
    ) -> Iterator[StreamEvent]:
        """
        Invoke the agent with streaming response.
        
        This is the streaming entry point for agent execution.
        Yields StreamEvent objects as the response is generated.
        
        Args:
            messages: List of messages in the conversation
            tools: List of tools available to the agent
            system_prompt: Optional system prompt to prepend
            
        Yields:
            StreamEvent objects containing chunks of the response
        """
        ...
