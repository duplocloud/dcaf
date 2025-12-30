"""
Persistence Adapters - Repository Implementations.

This module contains repository implementations for conversation persistence.

Implementations:
    - InMemoryConversationRepository: For testing and simple use cases
"""

from .in_memory_conversation_repo import InMemoryConversationRepository

__all__ = [
    "InMemoryConversationRepository",
]
