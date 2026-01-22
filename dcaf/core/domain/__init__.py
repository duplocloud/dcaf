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

from .entities import Conversation, Message, ToolCall
from .events import (
    ApprovalRequested,
    ConversationStarted,
    DomainEvent,
    ToolExecuted,
)
from .exceptions import (
    ConversationBlocked,
    DomainException,
    InvalidStateTransition,
    ToolCallNotFound,
)
from .services import ApprovalPolicy
from .value_objects import (
    ConversationId,
    MessageContent,
    PlatformContext,
    ToolCallId,
    ToolInput,
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
