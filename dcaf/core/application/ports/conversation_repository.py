"""ConversationRepository port - persistence interface."""

from typing import Protocol, runtime_checkable

from ...domain.entities import Conversation
from ...domain.value_objects import ConversationId


@runtime_checkable
class ConversationRepository(Protocol):
    """
    Persistence port for conversations.

    This protocol defines the interface for storing and retrieving
    conversations. Implementations can use any storage mechanism
    (in-memory, database, cache, etc.).

    Implementations:
        - InMemoryConversationRepository: For testing and simple use cases
        - RedisConversationRepository: For distributed caching
        - PostgresConversationRepository: For persistent storage

    Example:
        class InMemoryConversationRepository(ConversationRepository):
            def __init__(self):
                self._store = {}

            def get(self, id: ConversationId) -> Optional[Conversation]:
                return self._store.get(str(id))

            def save(self, conversation: Conversation) -> None:
                self._store[str(conversation.id)] = conversation
    """

    def get(self, id: ConversationId) -> Conversation | None:
        """
        Retrieve a conversation by ID.

        Args:
            id: The conversation ID to look up

        Returns:
            The conversation if found, None otherwise
        """
        ...

    def save(self, conversation: Conversation) -> None:
        """
        Save a conversation.

        This should persist the conversation and all its messages.
        If the conversation already exists, it should be updated.

        Args:
            conversation: The conversation to save
        """
        ...

    def delete(self, id: ConversationId) -> bool:
        """
        Delete a conversation by ID.

        Args:
            id: The conversation ID to delete

        Returns:
            True if deleted, False if not found
        """
        ...

    def exists(self, id: ConversationId) -> bool:
        """
        Check if a conversation exists.

        Args:
            id: The conversation ID to check

        Returns:
            True if exists, False otherwise
        """
        ...

    def get_or_create(self, id: ConversationId) -> Conversation:
        """
        Get an existing conversation or create a new one.

        Args:
            id: The conversation ID

        Returns:
            The existing or newly created conversation
        """
        ...
