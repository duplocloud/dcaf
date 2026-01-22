"""
DTOs - Data Transfer Objects.

DTOs are simple data containers used for communication between
layers and with external systems. They have no business logic.

These DTOs are fully compatible with the DuploCloud HelpDesk
messaging protocol.

Schema Reuse:
    Several classes are now imported from dcaf.schemas.messages to
    maintain a single source of truth. Backward-compatible aliases
    are provided (e.g., CommandDTO = Command).

    See docs/plans/schema-reuse-analysis.md for details.
"""

# FileObject is not yet implemented in responses - define a placeholder
from typing import Any

from .requests import AgentRequest, ApprovalRequest, ToolCallApproval
from .responses import (
    # Main response
    AgentResponse,
    # Schema classes (canonical names)
    Command,
    # Commands - imported from schemas with DTO aliases
    CommandDTO,  # Alias for schemas.Command
    # Data container
    DataDTO,
    ExecutedCommand,
    ExecutedCommandDTO,  # Alias for schemas.ExecutedCommand
    ExecutedToolCall,
    ExecutedToolCallDTO,  # Alias for schemas.ExecutedToolCall
    # Streaming
    StreamEvent,
    StreamEventType,
    # Tool calls
    ToolCallDTO,  # Core-specific (has additional fields)
)

FileObject = Any

__all__ = [
    # Requests
    "AgentRequest",
    "ApprovalRequest",
    "ToolCallApproval",
    # Main Response
    "AgentResponse",
    # Data container (HelpDesk protocol)
    "DataDTO",
    # Commands - Schema classes (canonical)
    "Command",
    "ExecutedCommand",
    "FileObject",
    # Commands - DTO aliases (backward compatibility)
    "CommandDTO",
    "ExecutedCommandDTO",
    # Tool calls - Schema classes (canonical)
    "ExecutedToolCall",
    # Tool calls - Core/DTO versions
    "ToolCallDTO",
    "ExecutedToolCallDTO",
    # Streaming
    "StreamEvent",
    "StreamEventType",
]
