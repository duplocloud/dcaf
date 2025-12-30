"""In-memory implementation of ConversationRepository."""

from typing import Dict, Optional
import threading

from ....domain.entities import Conversation
from ....domain.value_objects import ConversationId


class InMemoryConversationRepository:
    """
    In-memory implementation of ConversationRepository.
    
    This implementation stores conversations in a dictionary,
    suitable for:
    - Testing
    - Development
    - Single-instance deployments
    - Short-lived conversations
    
    Note: Data is lost when the process ends. For persistent
    storage, use a database-backed implementation.
    
    Thread-safe: Uses a lock for concurrent access.
    
    Example:
        repo = InMemoryConversationRepository()
        
        # Save a conversation
        conversation = Conversation.create()
        repo.save(conversation)
        
        # Retrieve it
        loaded = repo.get(conversation.id)
    """
    
    def __init__(self) -> None:
        """Initialize the repository."""
        self._store: Dict[str, Conversation] = {}
        self._lock = threading.RLock()
    
    def get(self, id: ConversationId) -> Optional[Conversation]:
        """
        Retrieve a conversation by ID.
        
        Args:
            id: The conversation ID
            
        Returns:
            The conversation if found, None otherwise
        """
        with self._lock:
            return self._store.get(str(id))
    
    def save(self, conversation: Conversation) -> None:
        """
        Save a conversation.
        
        If the conversation exists, it will be updated.
        
        Args:
            conversation: The conversation to save
        """
        with self._lock:
            self._store[str(conversation.id)] = conversation
    
    def delete(self, id: ConversationId) -> bool:
        """
        Delete a conversation by ID.
        
        Args:
            id: The conversation ID
            
        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            if str(id) in self._store:
                del self._store[str(id)]
                return True
            return False
    
    def exists(self, id: ConversationId) -> bool:
        """
        Check if a conversation exists.
        
        Args:
            id: The conversation ID
            
        Returns:
            True if exists, False otherwise
        """
        with self._lock:
            return str(id) in self._store
    
    def get_or_create(self, id: ConversationId) -> Conversation:
        """
        Get an existing conversation or create a new one.
        
        Args:
            id: The conversation ID
            
        Returns:
            The existing or newly created conversation
        """
        with self._lock:
            existing = self._store.get(str(id))
            if existing:
                return existing
            
            # Create new with the given ID
            conversation = Conversation(id=id)
            self._store[str(id)] = conversation
            return conversation
    
    def clear(self) -> None:
        """Clear all stored conversations."""
        with self._lock:
            self._store.clear()
    
    def count(self) -> int:
        """Get the number of stored conversations."""
        with self._lock:
            return len(self._store)
    
    def all(self) -> list:
        """Get all stored conversations."""
        with self._lock:
            return list(self._store.values())
