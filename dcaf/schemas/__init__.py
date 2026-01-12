"""
DCAF Schemas - Data models and validation schemas.

These Pydantic models define the wire format for the HelpDesk protocol.
They are the canonical source of truth for protocol-level data structures.
"""

from .messages import (
    # Message types
    AgentMessage,
    UserMessage,
    Message,
    Messages,
    # Commands
    Command,
    ExecutedCommand,
    FileObject,
    # Tool calls
    ToolCall,
    ExecutedToolCall,
    # Data containers
    Data,
    PlatformContext,
    AmbientContext,
    URLConfig,
    # Identity
    User,
    Agent,
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
