"""
DTOs - Data Transfer Objects.

DTOs are simple data containers used for communication between
layers and with external systems. They have no business logic.

These DTOs are fully compatible with the DuploCloud HelpDesk
messaging protocol.
"""

from .requests import AgentRequest, ApprovalRequest, ToolCallApproval
from .responses import (
    # Main response
    AgentResponse,
    # Data container
    DataDTO,
    # Commands
    CommandDTO,
    ExecutedCommandDTO,
    FileObject,
    # Tool calls
    ToolCallDTO,
    ExecutedToolCallDTO,
    # Streaming
    StreamEvent,
    StreamEventType,
)

__all__ = [
    # Requests
    "AgentRequest",
    "ApprovalRequest",
    "ToolCallApproval",
    # Main Response
    "AgentResponse",
    # Data container (HelpDesk protocol)
    "DataDTO",
    # Commands (HelpDesk protocol)
    "CommandDTO",
    "ExecutedCommandDTO",
    "FileObject",
    # Tool calls
    "ToolCallDTO",
    "ExecutedToolCallDTO",
    # Streaming
    "StreamEvent",
    "StreamEventType",
]
