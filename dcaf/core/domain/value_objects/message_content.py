"""Immutable message content."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ContentType(Enum):
    """Types of content that can be in a message."""

    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"


@dataclass(frozen=True)
class ContentBlock:
    """A single block of content within a message."""

    content_type: ContentType
    text: str | None = None
    tool_use_id: str | None = None
    tool_name: str | None = None
    tool_input: tuple | None = None  # Stored as tuple for immutability
    tool_result: str | None = None

    @classmethod
    def text_block(cls, text: str) -> "ContentBlock":
        """Create a text content block."""
        return cls(content_type=ContentType.TEXT, text=text)

    @classmethod
    def tool_use_block(
        cls, tool_use_id: str, tool_name: str, tool_input: dict[str, Any]
    ) -> "ContentBlock":
        """Create a tool use content block."""
        return cls(
            content_type=ContentType.TOOL_USE,
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            tool_input=tuple(sorted(tool_input.items())),
        )

    @classmethod
    def tool_result_block(cls, tool_use_id: str, result: str) -> "ContentBlock":
        """Create a tool result content block."""
        return cls(
            content_type=ContentType.TOOL_RESULT,
            tool_use_id=tool_use_id,
            tool_result=result,
        )

    def get_tool_input_dict(self) -> dict[str, Any]:
        """Get tool input as a dictionary."""
        if self.tool_input is None:
            return {}
        return dict(self.tool_input)


@dataclass(frozen=True)
class MessageContent:
    """
    Immutable, validated message content.

    A message can contain multiple content blocks (text, tool use, tool result).
    This value object ensures content is immutable and validated.
    """

    blocks: tuple  # Tuple of ContentBlock for immutability

    def __init__(self, blocks: list[ContentBlock]) -> None:
        """
        Initialize with a list of content blocks.

        Args:
            blocks: List of content blocks
        """
        if not blocks:
            raise ValueError("MessageContent must have at least one block")
        object.__setattr__(self, "blocks", tuple(blocks))

    @property
    def text(self) -> str | None:
        """Get the combined text content, if any."""
        text_parts = [
            block.text
            for block in self.blocks
            if block.content_type == ContentType.TEXT and block.text
        ]
        return " ".join(text_parts) if text_parts else None

    @property
    def has_tool_use(self) -> bool:
        """Check if content contains tool use blocks."""
        return any(block.content_type == ContentType.TOOL_USE for block in self.blocks)

    @property
    def tool_use_blocks(self) -> list[ContentBlock]:
        """Get all tool use blocks."""
        return [block for block in self.blocks if block.content_type == ContentType.TOOL_USE]

    def __repr__(self) -> str:
        return f"MessageContent(blocks={list(self.blocks)!r})"

    @classmethod
    def from_text(cls, text: str) -> "MessageContent":
        """Create MessageContent from a simple text string."""
        return cls([ContentBlock.text_block(text)])

    @classmethod
    def from_blocks(cls, blocks: list[ContentBlock]) -> "MessageContent":
        """Create MessageContent from a list of content blocks."""
        return cls(blocks)
