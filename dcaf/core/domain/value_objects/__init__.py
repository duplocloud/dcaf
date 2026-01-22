"""
Value Objects - Immutable objects without identity.

Value objects are defined by their attributes, not by an identity.
Two value objects are equal if all their attributes are equal.
They are immutable and side-effect free.
"""

from .conversation_id import ConversationId
from .message_content import ContentBlock, ContentType, MessageContent
from .platform_context import PlatformContext
from .tool_call_id import ToolCallId
from .tool_input import ToolInput

__all__ = [
    "ToolCallId",
    "ConversationId",
    "ToolInput",
    "MessageContent",
    "ContentBlock",
    "ContentType",
    "PlatformContext",
]
