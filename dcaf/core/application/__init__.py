"""
Application Layer - Service Orchestration.

This layer contains:
    - Ports: Interfaces (protocols) for external systems
    - Services: Application services that orchestrate business operations
    - DTOs: Request/Response objects for communication

The application layer coordinates domain logic with infrastructure,
but contains no business logic itself. It depends only on the domain layer.
"""

from .ports import (
    AgentRuntime,
    ConversationRepository,
    ApprovalCallback,
    EventPublisher,
)
from .services import (
    AgentService,
    ApprovalService,
)
from .dto import (
    AgentRequest,
    AgentResponse,
    ApprovalRequest,
    StreamEvent,
)

__all__ = [
    # Ports
    "AgentRuntime",
    "ConversationRepository",
    "ApprovalCallback",
    "EventPublisher",
    # Services
    "AgentService",
    "ApprovalService",
    # DTOs
    "AgentRequest",
    "AgentResponse",
    "ApprovalRequest",
    "StreamEvent",
]
