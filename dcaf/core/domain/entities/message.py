"""Message entity representing a single communication unit."""

from datetime import UTC, datetime
from enum import Enum

from ..value_objects.message_content import ContentBlock, MessageContent


class MessageRole(Enum):
    """Role of the message sender."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message:
    """
    Entity representing a single message in a conversation.

    A message has identity (implicit via position in conversation),
    a role (user/assistant/system), and content that may include
    text, tool use requests, or tool results.

    Attributes:
        role: Who sent the message (user, assistant, system)
        content: The message content (text, tool use, tool result)
        created_at: When the message was created
    """

    def __init__(
        self,
        role: MessageRole,
        content: MessageContent,
        created_at: datetime | None = None,
    ) -> None:
        """
        Initialize a new Message.

        Args:
            role: The message role
            content: The message content
            created_at: Creation timestamp (defaults to now)
        """
        self._role = role
        self._content = content
        self._created_at = created_at or datetime.now(UTC)

    @property
    def role(self) -> MessageRole:
        return self._role

    @property
    def content(self) -> MessageContent:
        return self._content

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def text(self) -> str | None:
        """Get the text content of the message, if any."""
        return self._content.text

    @property
    def has_tool_use(self) -> bool:
        """Check if this message contains tool use requests."""
        return self._content.has_tool_use

    @property
    def tool_use_blocks(self) -> list[ContentBlock]:
        """Get all tool use blocks in this message."""
        return self._content.tool_use_blocks

    @property
    def is_user_message(self) -> bool:
        return self._role == MessageRole.USER

    @property
    def is_assistant_message(self) -> bool:
        return self._role == MessageRole.ASSISTANT

    @property
    def is_system_message(self) -> bool:
        return self._role == MessageRole.SYSTEM

    def __repr__(self) -> str:
        text_preview = self.text[:50] + "..." if self.text and len(self.text) > 50 else self.text
        return f"Message(role={self._role.value}, text={text_preview!r})"

    # Factory methods

    @classmethod
    def user(cls, text: str) -> "Message":
        """Create a user message from text."""
        return cls(
            role=MessageRole.USER,
            content=MessageContent.from_text(text),
        )

    @classmethod
    def assistant(cls, text: str) -> "Message":
        """Create an assistant message from text."""
        return cls(
            role=MessageRole.ASSISTANT,
            content=MessageContent.from_text(text),
        )

    @classmethod
    def system(cls, text: str) -> "Message":
        """Create a system message from text."""
        return cls(
            role=MessageRole.SYSTEM,
            content=MessageContent.from_text(text),
        )

    @classmethod
    def assistant_with_content(cls, content: MessageContent) -> "Message":
        """Create an assistant message with complex content."""
        return cls(
            role=MessageRole.ASSISTANT,
            content=content,
        )

    @classmethod
    def user_with_content(cls, content: MessageContent) -> "Message":
        """Create a user message with complex content."""
        return cls(
            role=MessageRole.USER,
            content=content,
        )
