"""
Value Objects - Immutable objects without identity.

Value objects are defined by their attributes, not by an identity.
Two value objects are equal if all their attributes are equal.
They are immutable and side-effect free.
"""

from .tool_call_id import ToolCallId
from .conversation_id import ConversationId
from .tool_input import ToolInput
from .message_content import MessageContent, ContentBlock, ContentType
from .platform_context import PlatformContext

__all__ = [
    "ToolCallId",
    "ConversationId",
    "ToolInput",
    "MessageContent",
    "ContentBlock",
    "ContentType",
    "PlatformContext",
]
