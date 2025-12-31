"""
DCAF Core - Clean Architecture Abstraction Layer.

This module provides a simple, Pythonic API for building AI agents
with tool calling and human-in-the-loop approval.

Quick Start:
    from dcaf.core import Agent, serve
    from dcaf.tools import tool
    
    @tool(description="Get current weather")
    def get_weather(city: str) -> str:
        return f"Weather in {city}: Sunny, 72°F"
    
    agent = Agent(tools=[get_weather])
    serve(agent)  # Server running at http://0.0.0.0:8000

With Interceptors:
    from dcaf.core import Agent, LLMRequest, LLMResponse, InterceptorError
    
    def add_context(request: LLMRequest) -> LLMRequest:
        '''Add tenant info before sending to LLM.'''
        tenant = request.context.get("tenant_name", "unknown")
        request.add_system_context(f"User's tenant: {tenant}")
        return request
    
    def validate_input(request: LLMRequest) -> LLMRequest:
        '''Block suspicious input.'''
        if "ignore instructions" in request.get_latest_user_message().lower():
            raise InterceptorError("I can't process this request.")
        return request
    
    agent = Agent(
        tools=[get_weather],
        request_interceptors=[validate_input, add_context],
    )

For advanced usage, see the domain, application, and adapters submodules.
"""

__version__ = "1.0.0"

# Simple API (what most users need)
from .models import ChatMessage, PlatformContext
from .agent import Agent, AgentResponse, PendingToolCall
from .server import serve, create_app
from .session import Session

# HelpDesk Protocol DTOs (for full compatibility)
from .application.dto import (
    DataDTO,
    CommandDTO,
    ExecutedCommandDTO,
    ToolCallDTO,
    ExecutedToolCallDTO,
    StreamEvent,
    StreamEventType,
)

# Interceptors API (for request/response processing)
from .interceptors import (
    LLMRequest,
    LLMResponse,
    InterceptorError,
    create_request_from_messages,
    create_response_from_text,
)

# Primitives API (for custom agent functions)
from .primitives import (
    AgentResult,
    ToolApproval,
    ToolResult,
    from_agent_response,
)

# Stream event types (for type checking in streaming)
from ..schemas.events import (
    TextDeltaEvent,
    ToolCallsEvent,
    DoneEvent,
    ErrorEvent,
)

# Advanced API (for customization)
from .application.services import AgentService, ApprovalService
from .application.dto import AgentRequest
from .domain.entities import Conversation, Message, ToolCall
from .domain.events import (
    DomainEvent,
    ConversationStarted,
    ApprovalRequested,
    ToolExecuted,
)

__all__ = [
    # Simple API
    "Agent",
    "AgentResponse", 
    "PendingToolCall",
    "ChatMessage",
    "PlatformContext",
    "Session",
    "serve",
    "create_app",
    # HelpDesk Protocol DTOs
    "DataDTO",
    "CommandDTO",
    "ExecutedCommandDTO",
    "ToolCallDTO",
    "ExecutedToolCallDTO",
    "StreamEvent",
    "StreamEventType",
    # Interceptors API
    "LLMRequest",
    "LLMResponse",
    "InterceptorError",
    "create_request_from_messages",
    "create_response_from_text",
    # Primitives API (for custom agent functions)
    "AgentResult",
    "ToolApproval",
    "ToolResult",
    "from_agent_response",
    # Stream events (legacy)
    "TextDeltaEvent",
    "ToolCallsEvent",
    "DoneEvent",
    "ErrorEvent",
    # Advanced API
    "AgentService",
    "ApprovalService",
    "AgentRequest",
    "Conversation",
    "Message",
    "ToolCall",
    # Events
    "DomainEvent",
    "ConversationStarted",
    "ApprovalRequested",
    "ToolExecuted",
]
