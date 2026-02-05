"""
DCAF Core Schemas - V2 message and event schemas.

These are the v2 versions of the schemas, independent from the v1 schemas
in dcaf/schemas/. This allows v1 and v2 to evolve independently.
"""

from .events import (
    CommandsEvent,
    DoneEvent,
    ErrorEvent,
    ExecutedCommandsEvent,
    ExecutedToolCallsEvent,
    StreamEvent,
    TextDeltaEvent,
    ToolCallsEvent,
)
from .messages import (
    AgentMessage,
    AmbientContext,
    Command,
    Data,
    ExecutedCommand,
    ExecutedToolCall,
    FileObject,
    Message,
    Messages,
    PlatformContext,
    ToolCall,
    URLConfig,
    User,
    UserMessage,
)

__all__ = [
    # Events
    "StreamEvent",
    "TextDeltaEvent",
    "ToolCallsEvent",
    "CommandsEvent",
    "ExecutedToolCallsEvent",
    "ExecutedCommandsEvent",
    "DoneEvent",
    "ErrorEvent",
    # Messages
    "Message",
    "UserMessage",
    "AgentMessage",
    "Messages",
    "Data",
    "Command",
    "ExecutedCommand",
    "ToolCall",
    "ExecutedToolCall",
    "FileObject",
    "URLConfig",
    "PlatformContext",
    "AmbientContext",
    "User",
]
