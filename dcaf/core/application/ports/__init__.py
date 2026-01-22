"""
Ports - Interfaces for external systems.

Ports define how the application layer interacts with the outside world.
They are implemented by adapters in the adapters layer.

- Inbound ports: How external systems call into the application (use cases)
- Outbound ports: How the application calls external systems (defined here)
"""

from .agent_runtime import AgentRuntime
from .approval_callback import ApprovalCallback
from .conversation_repository import ConversationRepository
from .event_publisher import EventPublisher
from .mcp_protocol import MCPToolLike

__all__ = [
    "AgentRuntime",
    "ConversationRepository",
    "ApprovalCallback",
    "EventPublisher",
    "MCPToolLike",
]
