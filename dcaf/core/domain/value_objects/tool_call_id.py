"""Strongly-typed identifier for tool calls."""

import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ToolCallId:
    """
    Strongly-typed identifier for tool calls.

    Immutable value object that ensures tool call IDs are never empty
    and provides a type-safe way to pass around tool call identifiers.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("ToolCallId cannot be empty")
        if not isinstance(self.value, str):
            raise TypeError("ToolCallId value must be a string")

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"ToolCallId({self.value!r})"

    @classmethod
    def generate(cls) -> "ToolCallId":
        """Generate a new unique ToolCallId."""
        return cls(str(uuid.uuid4()))

    @classmethod
    def from_string(cls, value: str | None) -> Optional["ToolCallId"]:
        """Create a ToolCallId from a string, returning None if value is None."""
        if value is None:
            return None
        return cls(value)
