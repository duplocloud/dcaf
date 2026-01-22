"""
Entities - Objects with identity and lifecycle.

Entities are distinguished by their identity, not their attributes.
Two entities with the same attributes but different IDs are different entities.
Entities have lifecycle and can change state over time.
"""

from .conversation import Conversation
from .message import Message, MessageRole
from .tool_call import ToolCall, ToolCallStatus

__all__ = [
    "ToolCall",
    "ToolCallStatus",
    "Message",
    "MessageRole",
    "Conversation",
]
