"""
Domain Layer - Pure Business Logic.

This layer contains:
    - Entities: Objects with identity and lifecycle (Conversation, ToolCall, Message)
    - Value Objects: Immutable objects without identity (ToolCallId, ToolInput)
    - Domain Services: Stateless business operations (ApprovalPolicy)
    - Domain Events: Records of significant domain happenings
    - Exceptions: Domain-specific error types

The domain layer has NO external dependencies - it knows nothing about
HTTP, databases, or LLM frameworks.
"""

from .entities import Conversation, ToolCall, Message
from .value_objects import (
    ConversationId,
    ToolCallId,
    ToolInput,
    MessageContent,
    PlatformContext,
)
from .services import ApprovalPolicy
from .events import (
    DomainEvent,
    ApprovalRequested,
    ToolExecuted,
    ConversationStarted,
)
from .exceptions import (
    DomainException,
    ConversationBlocked,
    InvalidStateTransition,
    ToolCallNotFound,
)

__all__ = [
    # Entities
    "Conversation",
    "ToolCall",
    "Message",
    # Value Objects
    "ConversationId",
    "ToolCallId",
    "ToolInput",
    "MessageContent",
    "PlatformContext",
    # Services
    "ApprovalPolicy",
    # Events
    "DomainEvent",
    "ApprovalRequested",
    "ToolExecuted",
    "ConversationStarted",
    # Exceptions
    "DomainException",
    "ConversationBlocked",
    "InvalidStateTransition",
    "ToolCallNotFound",
]
