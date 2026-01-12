# Message & Response Gap Analysis

**Date:** January 8, 2026  
**Purpose:** Analyze the gaps between schema's `AgentMessage` and core's response classes

---

## Overview

The schema and core have **intentionally different** message/response structures because they serve different architectural purposes:

| Layer | Classes | Purpose |
|-------|---------|---------|
| **Schema (Wire Format)** | `Message`, `UserMessage`, `AgentMessage` | HelpDesk protocol serialization |
| **Core (User API)** | `AgentResponse` (agent.py) | Simple API for `Agent.run()` |
| **Core (Application)** | `AgentResponse` (dto/responses.py) | Internal application DTO |
| **Core (Custom Functions)** | `AgentResult` (primitives.py) | Return type for custom agent functions |

---

## Side-by-Side Comparison

### Schema's AgentMessage (Wire Format)

```python
# dcaf/schemas/messages.py
class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = ""
    data: Data = Field(default_factory=Data)
    meta_data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[datetime] = None
    user: Optional[User] = None
    agent: Optional[Agent] = None

class AgentMessage(Message):
    role: Literal["assistant"] = "assistant"
```

**Purpose:** Serialization format for HelpDesk API  
**Type:** Pydantic BaseModel (validation, JSON schema)  
**Usage:** HTTP requests/responses, message history storage

---

### Core's AgentResponse (User-Facing API)

```python
# dcaf/core/agent.py
@dataclass
class AgentResponse:
    text: str | None = None
    needs_approval: bool = False
    pending_tools: list[PendingToolCall] = field(default_factory=list)
    conversation_id: str = ""
    is_complete: bool = True
    _agent: "Agent" = field(repr=False, default=None)
    
    def approve_all(self) -> "AgentResponse": ...
    def reject_all(self, reason: str) -> "AgentResponse": ...
```

**Purpose:** Simple, Pythonic API for end users  
**Type:** Python dataclass with behavior  
**Usage:** Return value from `Agent.run()`

**Example:**
```python
response = agent.run(messages)
if response.needs_approval:
    response = response.approve_all()
print(response.text)
```

---

### Core's AgentResponse (Application DTO)

```python
# dcaf/core/application/dto/responses.py
@dataclass
class AgentResponse:
    conversation_id: str
    text: Optional[str] = None
    data: DataDTO = field(default_factory=DataDTO)
    has_pending_approvals: bool = False
    is_complete: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]: ...
    def to_helpdesk_message(self, role: str = "assistant") -> Dict[str, Any]: ...
```

**Purpose:** Internal application layer DTO for Clean Architecture  
**Type:** Python dataclass with serialization  
**Usage:** Between application services and adapters

---

### Core's AgentResult (Custom Agent Functions)

```python
# dcaf/core/primitives.py
@dataclass
class AgentResult:
    text: str = ""
    pending_tools: list[ToolApproval] = field(default_factory=list)
    executed_tools: list[ToolResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @property
    def needs_approval(self) -> bool:
        return len(self.pending_tools) > 0
```

**Purpose:** Return type for custom multi-call agent functions  
**Type:** Python dataclass (simple)  
**Usage:** User-defined agent functions with `serve(my_agent)`

**Example:**
```python
def my_agent(messages: list, context: dict) -> AgentResult:
    classifier = Agent(system="Classify intent")
    executor = Agent(tools=[delete_pod])
    
    intent = classifier.run(messages)
    if "action" in intent.text:
        result = executor.run(messages)
        return from_agent_response(result)
    
    return AgentResult(text=intent.text)
```

---

## Key Gaps & Reasoning

### Gap 1: Message Metadata

| Field | Schema's AgentMessage | Core Responses | Reason for Gap |
|-------|----------------------|----------------|----------------|
| `timestamp` | ✅ Yes | ❌ No | Core generates fresh; schema stores for history |
| `user` | ✅ Yes (`User` object) | ❌ No | Not needed in response; part of request context |
| `agent` | ✅ Yes (`Agent` object) | ❌ No | Agent identity implicit; not needed in single-agent scenarios |

**Reasoning:**
- **Schema needs these for wire format** - when storing/retrieving conversation history, timestamps and identity matter
- **Core doesn't need them in-memory** - the response is generated "now" by "this agent" - adding fields would be redundant
- **Clean separation of concerns** - request context (who's asking) vs response (what to do)

---

### Gap 2: Role Field

| Class | Has `role` field? | Value | Reason |
|-------|------------------|-------|--------|
| Schema's `AgentMessage` | ✅ Yes | `"assistant"` | HelpDesk protocol requirement |
| Core's `AgentResponse` (agent.py) | ❌ No | N/A | Not needed - always from agent |
| Core's `AgentResponse` (dto) | ❌ No | N/A | Added in `to_helpdesk_message()` |
| Core's `AgentResult` | ❌ No | N/A | Not needed - always from agent |

**Reasoning:**
- **Schema is neutral wire format** - needs explicit role because messages can be user or assistant
- **Core responses are type-safe** - `AgentResponse` is inherently from the agent, so `role` would be redundant
- **Added at serialization boundary** - `to_helpdesk_message()` adds `role="assistant"` when converting to wire format

---

### Gap 3: Data Structure

| Class | Data Container | Contents |
|-------|---------------|----------|
| Schema's `AgentMessage` | `Data` (Pydantic) | `cmds`, `executed_cmds`, `tool_calls`, `executed_tool_calls`, `url_configs` |
| Core's `AgentResponse` (agent.py) | N/A (flat) | `text`, `pending_tools` list directly |
| Core's `AgentResponse` (dto) | `DataDTO` (dataclass) | `cmds`, `executed_cmds`, `tool_calls`, `executed_tool_calls`, `session` |
| Core's `AgentResult` | N/A (flat) | `pending_tools`, `executed_tools` lists directly |

**Reasoning:**

**Schema's nested structure:**
```json
{
  "role": "assistant",
  "content": "I'll delete that pod.",
  "data": {
    "tool_calls": [{"id": "tc_123", "name": "delete_pod", ...}],
    "executed_tool_calls": []
  }
}
```

**Core's flat structure (user-facing):**
```python
AgentResponse(
    text="I'll delete that pod.",
    pending_tools=[PendingToolCall(id="tc_123", name="delete_pod", ...)]
)
```

**Why the difference?**
1. **User API simplicity** - Users don't need to know about the nested `data` structure
2. **Protocol compliance at boundary** - The application DTO has `DataDTO` and serializes to schema format
3. **Progressive disclosure** - Simple cases don't see complexity

---

### Gap 4: Behavioral Methods

| Method | Schema's AgentMessage | Core's AgentResponse (agent.py) | Core's AgentResponse (dto) |
|--------|----------------------|-------------------------------|---------------------------|
| `approve_all()` | ❌ No | ✅ Yes | ❌ No |
| `reject_all()` | ❌ No | ✅ Yes | ❌ No |
| `to_dict()` | ✅ Yes (Pydantic) | ❌ No | ✅ Yes |
| `to_helpdesk_message()` | ❌ No | ❌ No | ✅ Yes |

**Reasoning:**

**Schema = Pure Data (Pydantic validation)**
```python
msg = AgentMessage(content="Hello")
data = msg.model_dump()  # Pydantic's serialization
```

**User-Facing = Data + Behavior**
```python
response = agent.run(messages)
if response.needs_approval:
    response = response.approve_all()  # Behavior!
```

**Application DTO = Data + Serialization**
```python
response = AgentResponse(conversation_id="123", text="Hello", ...)
helpdesk_msg = response.to_helpdesk_message()  # Convert to wire format
```

---

### Gap 5: Multiple Response Types in Core

The core has **3 different response types** for different use cases:

```
┌─────────────────────────────────────────────────────────────┐
│                    User-Facing Layer                         │
│                                                              │
│  AgentResponse (agent.py)                                   │
│  - Simple API                                                │
│  - Has approve_all(), reject_all()                          │
│  - Used by: agent.run()                                     │
│                                                              │
│  AgentResult (primitives.py)                                │
│  - For custom functions                                      │
│  - Simple return type                                        │
│  - Used by: serve(my_custom_agent)                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Converted by server/facade
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  Application Layer (Internal)                │
│                                                              │
│  AgentResponse (dto/responses.py)                           │
│  - Full HelpDesk protocol                                   │
│  - Has to_dict(), to_helpdesk_message()                    │
│  - Used by: AgentService, adapters                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Serialized to
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Wire Format (Schema)                      │
│                                                              │
│  AgentMessage (schemas/messages.py)                         │
│  - Pydantic model                                           │
│  - JSON schema for API                                       │
│  - Used by: HTTP endpoints, storage                          │
└─────────────────────────────────────────────────────────────┘
```

**Schema has 1 type** - it's the wire format  
**Core has 3 types** - they serve different architectural layers

---

## Conversion Flow

Here's how a response flows from core to schema:

```python
# 1. User calls Agent.run()
response = agent.run(messages)
# → Returns: AgentResponse (agent.py) - simple user API

# 2. Internally, AgentService returns application DTO
internal_response = agent_service.execute(request)
# → Returns: AgentResponse (dto/responses.py) - full protocol

# 3. Application DTO is converted to user-facing
user_response = agent._convert_response(internal_response)
# → Returns: AgentResponse (agent.py) - hides complexity

# 4. For HTTP API, server converts to schema
helpdesk_msg = internal_response.to_helpdesk_message()
# → Returns: Dict matching AgentMessage schema

# 5. Schema validates and serializes
validated = AgentMessage(**helpdesk_msg)
json_response = validated.model_dump()
# → Returns: JSON for HTTP response
```

---

## Should We Unify Them?

### ❌ NO - Keep Them Separate

**Reasons:**

1. **Different Concerns**
   - Schema: Wire format (HTTP, storage)
   - Core: Business logic (behavior, domain)

2. **Different Technologies**
   - Schema: Pydantic (validation, JSON schema)
   - Core: Dataclasses (simple, fast, Pythonic)

3. **API Simplicity**
   - User-facing API should be minimal
   - Wire format needs full protocol compliance

4. **Flexibility**
   - Can change internal structure without breaking API
   - Can support multiple protocols

5. **Clean Architecture**
   - Keeps domain logic pure
   - Adapters handle serialization

---

## What We Could Improve

### Option 1: Add Factory Methods to Schema

Add convenience methods to create schema messages from core responses:

```python
# In dcaf/schemas/messages.py
class AgentMessage(Message):
    role: Literal["assistant"] = "assistant"
    
    @classmethod
    def from_agent_response(cls, response: AgentResponse) -> "AgentMessage":
        """Create AgentMessage from core AgentResponse."""
        return cls(
            content=response.text or "",
            data=Data(
                tool_calls=[tc.to_dict() for tc in response.tool_calls],
                executed_tool_calls=[etc.to_dict() for etc in response.executed_tool_calls],
            ),
            timestamp=datetime.now(timezone.utc),
        )
```

### Option 2: Add Timestamp to Application DTO

If we want to track response times:

```python
# In dcaf/core/application/dto/responses.py
@dataclass
class AgentResponse:
    conversation_id: str
    text: Optional[str] = None
    data: DataDTO = field(default_factory=DataDTO)
    has_pending_approvals: bool = False
    is_complete: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))  # NEW
```

### Option 3: Add User/Agent Identity Fields (Optional)

For multi-agent scenarios:

```python
@dataclass
class AgentResponse:
    conversation_id: str
    text: Optional[str] = None
    data: DataDTO = field(default_factory=DataDTO)
    # ... existing fields ...
    agent_name: Optional[str] = None  # NEW: Which agent generated this
    agent_id: Optional[str] = None    # NEW: Agent instance ID
```

---

## Recommendations

### Keep Current Structure ✅

The separation is **intentional and beneficial**:

| Layer | Use | Keep As |
|-------|-----|---------|
| Schema (`AgentMessage`) | Wire format, API contracts | Pydantic models |
| User API (`AgentResponse` in agent.py) | Simple `.run()` API | Dataclass with behavior |
| Application (`AgentResponse` in dto/) | Internal protocol handling | Dataclass with serialization |
| Custom functions (`AgentResult`) | User-defined agents | Simple dataclass |

### Minor Enhancements (Optional)

1. ✅ **Add factory method** to `AgentMessage.from_agent_response()`
2. ⚠️ **Consider timestamp** in application DTO if timing metrics needed
3. ⚠️ **Consider agent identity** fields for multi-agent orchestration

### Don't Change

1. ❌ Don't merge schema and core responses
2. ❌ Don't add `role` field to core responses
3. ❌ Don't add behavior to schema classes
4. ❌ Don't expose full DataDTO in user-facing API

---

## Summary Table

| Feature | Schema AgentMessage | Core AgentResponse (User) | Core AgentResponse (DTO) | Core AgentResult |
|---------|-------------------|-------------------------|--------------------------|------------------|
| **Purpose** | Wire format | Simple API | Internal DTO | Custom functions |
| **Type** | Pydantic | Dataclass | Dataclass | Dataclass |
| **Has role** | ✅ Yes | ❌ No | ❌ No (added in to_dict) | ❌ No |
| **Has timestamp** | ✅ Yes | ❌ No | ❌ No | ❌ No |
| **Has user/agent** | ✅ Yes | ❌ No | ❌ No | ❌ No |
| **Has data container** | ✅ Yes (Data) | ❌ No (flat) | ✅ Yes (DataDTO) | ❌ No (flat) |
| **Has approve_all()** | ❌ No | ✅ Yes | ❌ No | ❌ No |
| **Has to_dict()** | ✅ Yes (Pydantic) | ❌ No | ✅ Yes | ❌ No |
| **Used by** | HTTP API, storage | `Agent.run()` | `AgentService` | `serve(fn)` |

---

## Conclusion

The gaps are **intentional design choices**, not mistakes:

1. **Schema is universal wire format** - needs all metadata
2. **Core responses are specialized** - optimized for their use case
3. **Separation enables evolution** - can change internals without breaking API
4. **Converters bridge the gap** - `to_helpdesk_message()` does the translation

**Recommendation:** Keep the current separation. It follows Clean Architecture principles and provides a better developer experience.
