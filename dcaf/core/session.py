"""
Session management for DCAF agents.

Sessions provide a way to persist state between conversation turns,
similar to ASP.NET session state. The session travels with the request
and response in the HelpDesk protocol's `data.session` field.

Example - Basic Usage:
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

Example - Typed Models:
    from pydantic import BaseModel, Field
    from dataclasses import dataclass
    
    class CartItem(BaseModel):
        name: str
        quantity: int
        price: float
    
    class ShoppingCart(BaseModel):
        items: list[CartItem] = Field(default_factory=list)
        discount_code: str | None = None
    
    @tool(description="Add item to cart")
    def add_to_cart(item_name: str, quantity: int, price: float, session: Session) -> str:
        # Get cart as a typed model (deserializes from JSON)
        cart = session.get("cart", as_type=ShoppingCart) or ShoppingCart()
        
        # Modify the model
        cart.items.append(CartItem(name=item_name, quantity=quantity, price=price))
        
        # Store it back (auto-serializes to JSON)
        session.set("cart", cart)
        
        return f"Added {quantity}x {item_name} to cart"

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

from dataclasses import dataclass, field, is_dataclass, asdict, fields as dataclass_fields
from typing import Any, Iterator, TypeVar, Type, get_type_hints, overload

# Type variable for typed get operations
T = TypeVar("T")


def _is_pydantic_model(obj: Any) -> bool:
    """Check if an object is a Pydantic model instance."""
    return hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump"))


def _is_pydantic_model_class(cls: Any) -> bool:
    """Check if a class is a Pydantic model class."""
    return hasattr(cls, "model_validate") and callable(getattr(cls, "model_validate"))


def _serialize_value(value: Any) -> Any:
    """
    Serialize a value for storage.
    
    Handles:
    - Pydantic models → dict via model_dump()
    - Dataclasses → dict via asdict()
    - Primitives/dicts/lists → stored as-is
    """
    # Pydantic model instance
    if _is_pydantic_model(value):
        return value.model_dump()
    
    # Dataclass instance (but not Pydantic, which is also a dataclass)
    if is_dataclass(value) and not _is_pydantic_model(value):
        return asdict(value)
    
    # Already JSON-serializable (dict, list, str, int, float, bool, None)
    return value


def _deserialize_value(data: Any, as_type: Type[T] | None) -> T | Any:
    """
    Deserialize a value to the specified type.
    
    Args:
        data: The raw data from storage
        as_type: The type to deserialize into (optional)
        
    Returns:
        Deserialized object if as_type provided, otherwise raw data
    """
    if as_type is None:
        return data
    
    if data is None:
        return None
    
    # Pydantic model class
    if _is_pydantic_model_class(as_type):
        return as_type.model_validate(data)
    
    # Dataclass
    if is_dataclass(as_type) and isinstance(as_type, type):
        # Get the dataclass fields and their types
        try:
            return as_type(**data)
        except TypeError:
            # If data doesn't match, return as-is
            return data
    
    # For basic types, just return the data
    # (int, str, float, bool, list, dict, etc.)
    return data


@dataclass
class Session:
    """
    Server-client session state that persists across conversation turns.
    
    Sessions are key-value stores that travel with each request/response.
    Use sessions to remember information across multiple conversation turns,
    like user preferences, accumulated context, or workflow state.
    
    Supports typed storage with automatic serialization/deserialization:
    - **Pydantic models**: Serialized via `model_dump()`, deserialized via `model_validate()`
    - **Dataclasses**: Serialized via `asdict()`, deserialized via constructor
    - **Primitives/dicts**: Stored and retrieved as-is
    
    Attributes:
        _data: Internal storage for session values
        _modified: Tracks whether the session has been modified
        
    Example - Basic usage:
        session.set("count", 5)
        session.set("items", ["a", "b", "c"])
        
        count = session.get("count")  # 5
        items = session.get("items")  # ["a", "b", "c"]
        
    Example - Typed models:
        from pydantic import BaseModel
        
        class UserPrefs(BaseModel):
            theme: str = "light"
            language: str = "en"
        
        # Store a model (auto-serializes to dict)
        session.set("prefs", UserPrefs(theme="dark"))
        
        # Retrieve as typed model (auto-deserializes)
        prefs = session.get("prefs", as_type=UserPrefs)
        print(prefs.theme)  # "dark"
        
        # Retrieve without type (returns raw dict)
        raw = session.get("prefs")
        print(raw)  # {"theme": "dark", "language": "en"}
    """
    
    _data: dict[str, Any] = field(default_factory=dict)
    _modified: bool = field(default=False, repr=False)
    
    @overload
    def get(self, key: str) -> Any: ...
    
    @overload
    def get(self, key: str, default: T) -> T: ...
    
    @overload
    def get(self, key: str, default: Any = None, *, as_type: Type[T]) -> T | None: ...
    
    def get(
        self, 
        key: str, 
        default: Any = None,
        *,
        as_type: Type[T] | None = None,
    ) -> T | Any:
        """
        Get a session value, optionally deserializing to a specific type.
        
        Args:
            key: The key to look up
            default: Value to return if key doesn't exist
            as_type: Optional type to deserialize the value into.
                    Supports Pydantic models and dataclasses.
            
        Returns:
            The stored value (deserialized if as_type provided),
            or default if not found
            
        Example - Basic:
            user_name = session.get("user_name", "Guest")
            visit_count = session.get("visits", 0)
            
        Example - Typed:
            from pydantic import BaseModel
            
            class Cart(BaseModel):
                items: list[str] = []
            
            # Returns Cart instance (or None if not found)
            cart = session.get("cart", as_type=Cart)
            
            # Returns Cart instance (or default Cart if not found)
            cart = session.get("cart", Cart(), as_type=Cart)
        """
        if key not in self._data:
            # If default is provided and as_type matches, return default as-is
            return default
        
        raw_value = self._data[key]
        return _deserialize_value(raw_value, as_type)
    
    def set(self, key: str, value: Any) -> None:
        """
        Set a session value.
        
        Automatically serializes Pydantic models and dataclasses to
        JSON-compatible dictionaries. Primitives and dicts are stored as-is.
        
        Args:
            key: The key to store under
            value: The value to store. Can be:
                   - Primitives (str, int, float, bool, None)
                   - Dicts and lists
                   - Pydantic models (serialized via model_dump())
                   - Dataclasses (serialized via asdict())
            
        Example - Basic:
            session.set("authenticated", True)
            session.set("user_prefs", {"theme": "dark"})
            
        Example - Pydantic model:
            from pydantic import BaseModel
            
            class User(BaseModel):
                name: str
                email: str
            
            user = User(name="Alice", email="alice@example.com")
            session.set("current_user", user)  # Auto-serializes to dict
            
        Example - Dataclass:
            from dataclasses import dataclass
            
            @dataclass
            class Config:
                debug: bool = False
                max_retries: int = 3
            
            session.set("config", Config(debug=True))  # Auto-serializes
        """
        serialized = _serialize_value(value)
        self._data[key] = serialized
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
        
        Note: Values are returned as raw (serialized) data.
        Use get() with as_type for typed access.
        
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
        
        Note: Values in the dict are serialized automatically
        (Pydantic models, dataclasses → dict).
        
        Args:
            data: Dictionary of key-value pairs to add/update
            
        Example:
            session.update({
                "step": 2,
                "completed_steps": ["intro", "config"],
            })
        """
        if data:
            for key, value in data.items():
                self._data[key] = _serialize_value(value)
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
            Dictionary representation of the session.
            All values are already serialized (JSON-compatible).
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
        """
        Support bracket access: session['key'].
        
        Note: Returns raw data. Use get(key, as_type=...) for typed access.
        """
        return self._data[key]
    
    def __setitem__(self, key: str, value: Any) -> None:
        """Support bracket assignment: session['key'] = value."""
        self.set(key, value)
    
    def __delitem__(self, key: str) -> None:
        """Support del: del session['key']."""
        self.delete(key)
