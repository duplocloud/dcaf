# Session Feature - Current State

This document summarizes the current implementation of the Session feature in DCAF for further discussion.

## Overview

Sessions provide persistent state across conversation turns, similar to ASP.NET session state. The session data travels with each request/response in the HelpDesk protocol.

## Current Implementation

### Location
- **Main class**: `dcaf/core/session.py` → `Session`
- **Documentation**: `docs/guides/session-management.md`

### Session Class API

```python
from dcaf.core import Session

session = Session()

# Core methods
session.set(key, value)           # Store value (auto-serializes Pydantic/dataclass)
session.get(key, default)         # Get value
session.get(key, as_type=Model)   # Get and deserialize to typed model
session.delete(key)               # Remove value
session.clear()                   # Clear all data
session.has(key)                  # Check existence

# Dict-like access
session["key"] = value
value = session["key"]

# Serialization
session.to_dict()                 # Convert to dict
Session.from_dict(data)           # Create from dict

# Properties
session.is_modified               # True if changed
session.is_empty                  # True if no data
```

### How Session is Used

**1. Tool Injection (Primary Use)**
```python
@tool
def my_tool(name: str, session: Session) -> str:
    """Session parameter is auto-injected by DCAF."""
    session.set("last_name", name)
    return f"Hello {name}"
```

**2. Response Access**
```python
response = agent.run(messages)
session_data = response.session  # Returns dict
```

**3. Protocol Flow**
```
Request:                              Response:
{                                     {
  "messages": [...],                    "content": "...",
  "data": {                             "data": {
    "session": {"key": "value"}           "session": {"key": "updated"}
  }                                     }
}                                     }
```

### Typed Storage

Session supports automatic serialization/deserialization:

| Type | Serialize | Deserialize |
|------|-----------|-------------|
| Pydantic model | `model_dump()` | `model_validate()` |
| Dataclass | `asdict()` | Constructor |
| Primitives/dicts | As-is | As-is |

```python
class Cart(BaseModel):
    items: list[str] = []

# Store (auto-serializes)
session.set("cart", Cart(items=["widget"]))

# Retrieve (auto-deserializes)
cart = session.get("cart", as_type=Cart)
```

## Where Session is NOT Currently Available

1. **`agent.run()` / `agent.chat()` parameters** - No `session` parameter exists
2. **Request interceptors** - Would need manual parsing from context
3. **Response interceptors** - Would need manual access

## Current Limitations / Questions

1. **Session injection only works in tools** - Not available in interceptors or other extension points
2. **Session must travel via protocol** - Client (HelpDesk) responsible for persisting and sending back
3. **No server-side session storage** - Session is purely client-side (travels in request/response)
4. **No session ID** - Session is anonymous, tied to conversation flow

## Files Involved

| File | Purpose |
|------|---------|
| `dcaf/core/session.py` | Session class implementation |
| `dcaf/core/__init__.py` | Exports `Session` |
| `dcaf/core/application/dto/responses.py` | `AgentResponse.session` property |
| `docs/guides/session-management.md` | Full documentation |

## Example: Multi-Step Workflow

```python
@tool(description="Start deployment wizard")
def start_deploy(session: Session) -> str:
    session.set("wizard_step", 1)
    return "Step 1: What service do you want to deploy?"

@tool(description="Set deployment service")
def set_service(name: str, session: Session) -> str:
    session.set("service_name", name)
    session.set("wizard_step", 2)
    return f"Service: {name}. Step 2: How many replicas?"

@tool(requires_approval=True, description="Execute deployment")
def execute_deploy(session: Session) -> str:
    service = session.get("service_name")
    replicas = session.get("replicas")
    session.clear()  # Reset wizard
    return f"Deployed {service} with {replicas} replicas!"
```

---

## Discussion Points

- Should `agent.run()` accept a `session` parameter?
- Should interceptors have access to session?
- Server-side session storage vs client-side?
- Session expiration/TTL?
- Session ID for tracking?
