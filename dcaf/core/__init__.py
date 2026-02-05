"""
DCAF Core - Clean Architecture Abstraction Layer.

This module provides a simple, Pythonic API for building AI agents
with tool calling and human-in-the-loop approval.

Quick Start:
    from dcaf.core import Agent, serve, tool

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

from dcaf import __version__

# Simple API (what most users need)
# Stream event types (for type checking in streaming)
# NOTE: Using v2 schemas from core/schemas/ (not v1 dcaf/schemas/)
from .schemas.events import (
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    ToolCallsEvent,
)
from .agent import Agent, AgentResponse, PendingToolCall

# HelpDesk Protocol DTOs (for full compatibility)
from .application.dto import (
    AgentRequest,
    CommandDTO,
    DataDTO,
    ExecutedCommandDTO,
    ExecutedToolCallDTO,
    StreamEvent,
    StreamEventType,
    ToolCallDTO,
)

# Advanced API (for customization)
from .application.services import AgentService, ApprovalService

# Configuration API (for environment-driven setup)
from .config import (
    get_configured_provider,
    get_model_from_env,
    get_provider_from_env,
    is_provider_configured,
    load_agent_config,
)
from .domain.entities import Conversation, Message, ToolCall
from .domain.events import (
    ApprovalRequested,
    ConversationStarted,
    DomainEvent,
    ToolExecuted,
)

# Interceptors API (for request/response processing)
from .interceptors import (
    InterceptorError,
    LLMRequest,
    LLMResponse,
    create_request_from_messages,
    create_response_from_text,
)
from .models import ChatMessage, PlatformContext

# Primitives API (for custom agent functions)
from .primitives import (
    AgentResult,
    ToolApproval,
    ToolResult,
    from_agent_response,
)
from ..channel_routing import ChannelResponseRouter, SlackResponseRouter
from .server import create_app, serve
from .session import Session

# Tool decorator (v2 copy for complete separation)
from .tools import tool

__all__ = [
    # Simple API
    "Agent",
    "AgentResponse",
    "PendingToolCall",
    "tool",
    "ChatMessage",
    "PlatformContext",
    "Session",
    "serve",
    "create_app",
    # Configuration
    "load_agent_config",
    "get_provider_from_env",
    "get_model_from_env",
    "is_provider_configured",
    "get_configured_provider",
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
    # Channel Routing
    "ChannelResponseRouter",
    "SlackResponseRouter",
    # Events
    "DomainEvent",
    "ConversationStarted",
    "ApprovalRequested",
    "ToolExecuted",
]
