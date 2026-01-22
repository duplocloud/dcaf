"""
DCAF Schemas - Data models and validation schemas.

These Pydantic models define the wire format for the HelpDesk protocol.
They are the canonical source of truth for protocol-level data structures.
"""

from .messages import (
    Agent,
    # Message types
    AgentMessage,
    AmbientContext,
    # Commands
    Command,
    # Data containers
    Data,
    ExecutedCommand,
    ExecutedToolCall,
    FileObject,
    Message,
    Messages,
    PlatformContext,
    # Tool calls
    ToolCall,
    URLConfig,
    # Identity
    User,
    UserMessage,
)

__all__ = [
    # Message types
    "AgentMessage",
    "UserMessage",
    "Message",
    "Messages",
    # Commands (reusable in core)
    "Command",
    "ExecutedCommand",
    "FileObject",
    # Tool calls (reusable in core)
    "ToolCall",
    "ExecutedToolCall",
    # Data containers
    "Data",
    "PlatformContext",
    "AmbientContext",
    "URLConfig",
    # Identity
    "User",
    "Agent",
]
