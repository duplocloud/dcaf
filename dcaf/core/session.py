"""
Session management for DCAF agents.

Sessions provide a way to persist state between conversation turns,
similar to ASP.NET session state. The session travels with the request
and response in the HelpDesk protocol's `data.session` field.

Example:
    from dcaf.core import Agent, Session
    from dcaf.tools import tool
    
    @tool(description="Greet the user")
    def greet(name: str, session: Session) -> str:
        '''Greet the user, remembering if we've met before.'''
        if session.get("greeted"):
            return f"Welcome back, {name}!"
        
        session.set("greeted", True)
        session.set("user_name", name)
        return f"Hello {name}, nice to meet you!"
    
    agent = Agent(tools=[greet])
    
    # First request - session is empty
    response = agent.run(
        messages=[{"role": "user", "content": "Hi, I'm Alice"}],
        session={},  # Empty session
    )
    # response.session = {"greeted": True, "user_name": "Alice"}
    
    # Second request - pass previous session back
    response = agent.run(
        messages=[{"role": "user", "content": "Hi again"}],
        session=response.session,  # Pass session from last response
    )
    # Agent sees greeted=True, responds with "Welcome back!"

Protocol:
    Sessions travel in the HelpDesk protocol's data.session field:
    
    Request:
        {
            "messages": [...],
            "data": {
                "session": {"key": "value", ...}
            }
        }
    
    Response:
        {
            "content": "...",
            "data": {
                "session": {"key": "updated_value", ...},
                ...
            }
        }
"""

from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class Session:
    """
    Server-client session state that persists across conversation turns.
    
    Sessions are key-value stores that travel with each request/response.
    Use sessions to remember information across multiple conversation turns,
    like user preferences, accumulated context, or workflow state.
    
    Attributes:
        _data: Internal storage for session values
        _modified: Tracks whether the session has been modified
        
    Example:
        # In a tool function
        def my_tool(query: str, session: Session) -> str:
            # Read from session
            history = session.get("query_history", [])
            
            # Write to session
            history.append(query)
            session.set("query_history", history)
            
            # Increment a counter
            count = session.get("query_count", 0) + 1
            session.set("query_count", count)
            
            return f"Query #{count}: {query}"
    """
    
    _data: dict[str, Any] = field(default_factory=dict)
    _modified: bool = field(default=False, repr=False)
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a session value.
        
        Args:
            key: The key to look up
            default: Value to return if key doesn't exist
            
        Returns:
            The stored value, or default if not found
            
        Example:
            user_name = session.get("user_name", "Guest")
            visit_count = session.get("visits", 0)
        """
        return self._data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """
        Set a session value.
        
        Args:
            key: The key to store under
            value: The value to store (must be JSON-serializable)
            
        Example:
            session.set("authenticated", True)
            session.set("user_prefs", {"theme": "dark"})
        """
        self._data[key] = value
        self._modified = True
    
    def delete(self, key: str) -> None:
        """
        Remove a session value.
        
        Args:
            key: The key to remove
            
        Example:
            session.delete("temp_data")
        """
        if key in self._data:
            del self._data[key]
            self._modified = True
    
    def clear(self) -> None:
        """
        Clear all session data.
        
        Example:
            # Start fresh
            session.clear()
        """
        if self._data:
            self._data.clear()
            self._modified = True
    
    def has(self, key: str) -> bool:
        """
        Check if a key exists in the session.
        
        Args:
            key: The key to check
            
        Returns:
            True if the key exists, False otherwise
            
        Example:
            if session.has("user_id"):
                # User is logged in
                pass
        """
        return key in self._data
    
    def keys(self) -> list[str]:
        """
        Get all session keys.
        
        Returns:
            List of all keys in the session
            
        Example:
            for key in session.keys():
                print(f"{key}: {session.get(key)}")
        """
        return list(self._data.keys())
    
    def items(self) -> Iterator[tuple[str, Any]]:
        """
        Iterate over session key-value pairs.
        
        Yields:
            Tuples of (key, value)
            
        Example:
            for key, value in session.items():
                print(f"{key} = {value}")
        """
        return iter(self._data.items())
    
    def update(self, data: dict[str, Any]) -> None:
        """
        Update session with multiple values at once.
        
        Args:
            data: Dictionary of key-value pairs to add/update
            
        Example:
            session.update({
                "step": 2,
                "completed_steps": ["intro", "config"],
            })
        """
        if data:
            self._data.update(data)
            self._modified = True
    
    @property
    def is_modified(self) -> bool:
        """
        Check if the session has been modified.
        
        Useful for optimizing responses - only include session
        in response if it changed.
        
        Returns:
            True if any set/delete/clear/update was called
        """
        return self._modified
    
    @property
    def is_empty(self) -> bool:
        """
        Check if the session is empty.
        
        Returns:
            True if there are no values in the session
        """
        return len(self._data) == 0
    
    def to_dict(self) -> dict[str, Any]:
        """
        Serialize session for response.
        
        Returns:
            Dictionary representation of the session
            
        Note:
            All values must be JSON-serializable.
        """
        return dict(self._data)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Session":
        """
        Create a session from a dictionary.
        
        Args:
            data: Dictionary of session data (from request)
            
        Returns:
            New Session instance
            
        Example:
            # Parse from request
            session = Session.from_dict(request.data.get("session", {}))
        """
        return cls(_data=dict(data) if data else {})
    
    def __len__(self) -> int:
        """Return the number of items in the session."""
        return len(self._data)
    
    def __contains__(self, key: str) -> bool:
        """Support 'in' operator: if 'key' in session."""
        return key in self._data
    
    def __getitem__(self, key: str) -> Any:
        """Support bracket access: session['key']."""
        return self._data[key]
    
    def __setitem__(self, key: str, value: Any) -> None:
        """Support bracket assignment: session['key'] = value."""
        self.set(key, value)
    
    def __delitem__(self, key: str) -> None:
        """Support del: del session['key']."""
        self.delete(key)
