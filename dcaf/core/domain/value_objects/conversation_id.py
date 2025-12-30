"""Strongly-typed identifier for conversations."""

from dataclasses import dataclass
import uuid
from typing import Optional


@dataclass(frozen=True)
class ConversationId:
    """
    Strongly-typed identifier for conversations.
    
    Immutable value object that ensures conversation IDs are never empty
    and provides a type-safe way to pass around conversation identifiers.
    """
    
    value: str
    
    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("ConversationId cannot be empty")
        if not isinstance(self.value, str):
            raise TypeError("ConversationId value must be a string")
    
    def __str__(self) -> str:
        return self.value
    
    def __repr__(self) -> str:
        return f"ConversationId({self.value!r})"
    
    @classmethod
    def generate(cls) -> "ConversationId":
        """Generate a new unique ConversationId."""
        return cls(str(uuid.uuid4()))
    
    @classmethod
    def from_string(cls, value: Optional[str]) -> Optional["ConversationId"]:
        """Create a ConversationId from a string, returning None if value is None."""
        if value is None:
            return None
        return cls(value)
