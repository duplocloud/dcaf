# DCAF Engineering Handoff Guide

## Project Overview

**DCAF (DuploCloud Agent Framework)** is an agent framework designed to orchestrate AI-powered conversations that can execute tools requiring human approval. It's particularly focused on infrastructure operations (Kubernetes, AWS) where autonomous execution without oversight could be dangerous.

### What Problem Does It Solve?

1. **Safe Tool Execution**: Agents can propose actions, but dangerous operations require human approval before execution
2. **Framework Flexibility**: Swap between LLM frameworks (Agno, LangChain, Bedrock) without changing business logic
3. **Consistent Behavior**: Approval flows, streaming, and error handling work the same regardless of the underlying framework

---

## User-Facing API

Most users interact with DCAF through a simple API:

```python
from dcaf.core import Agent, serve

agent = Agent(tools=[list_pods, delete_pod])
serve(agent)
```

For custom logic, users write a function:

```python
from dcaf.core import Agent, AgentResult, serve

def my_agent(messages: list, context: dict) -> AgentResult:
    classifier = Agent(system="Classify intent")
    intent = classifier.run(messages)
    # ... custom logic
    return AgentResult(text=response.text)

serve(my_agent)
```

**The complexity below is hidden from users.** The `Agent` class is a facade over the Clean Architecture internals.

---

## Architecture Overview (Internal)

DCAF Core follows **Clean Architecture** with **Domain-Driven Design** tactical patterns. This section explains how all the pieces fit together.

### The Big Picture

```
┌─────────────────────────────────────────────────────────────────┐
│                        External World                            │
│          (HTTP, CLI, Agno SDK, LangChain, Databases)            │
├─────────────────────────────────────────────────────────────────┤
│                          ADAPTERS                                │
│   ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐   │
│   │  Inbound    │  │  Outbound   │  │    Persistence       │   │
│   │  (FastAPI)  │  │  (Agno)     │  │  (Repositories)      │   │
│   └─────────────┘  └─────────────┘  └──────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                        APPLICATION                               │
│   ┌─────────────────┐  ┌────────────────────────────────────┐  │
│   │    Services    │  │              Ports                  │  │
│   │  (ExecuteAgent) │  │  (AgentRuntime, ConversationRepo)   │  │
│   └─────────────────┘  └────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                          DOMAIN                                  │
│   ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐   │
│   │ Entities │  │Value Objects │  │   Domain Services      │   │
│   │(ToolCall)│  │ (ToolCallId) │  │  (ApprovalPolicy)      │   │
│   └──────────┘  └──────────────┘  └────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**The Dependency Rule**: Dependencies always point inward. Domain knows nothing about HTTP, Agno, or databases.

---

### Layer-by-Layer Breakdown

#### 1. Domain Layer (Core Business Logic)

The innermost layer contains pure business logic with **zero external dependencies**.

| Component | Purpose | Example |
|-----------|---------|---------|
| **Entities** | Objects with identity and lifecycle | `Conversation`, `ToolCall`, `Message` |
| **Value Objects** | Immutable data holders | `ToolCallId`, `ToolInput`, `MessageContent` |
| **Domain Services** | Logic that doesn't belong to a single entity | `ApprovalPolicy` |
| **Domain Events** | Notifications about what happened | `ToolCallApproved`, `MessageAdded` |

**Key Domain Entities:**

```
┌─────────────────────────────────────────────────────────────────┐
│                      Conversation (Aggregate Root)               │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Messages[]           - User and assistant messages      │   │
│   │  ToolCalls[]          - Pending and executed tool calls  │   │
│   │  PlatformContext      - Runtime environment (tenant, etc)│   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│   Methods:                                                       │
│   • add_user_message(content)                                   │
│   • add_assistant_message(content)                              │
│   • add_tool_call(name, input)                                  │
│   • approve_tool_call(id)                                       │
│   • reject_tool_call(id, reason)                                │
│   • execute_tool_call(id, result)                               │
└─────────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────┐
│                         ToolCall (Entity)                        │
│                                                                  │
│   State Machine:                                                 │
│                                                                  │
│      ┌──────────┐  approve()   ┌──────────┐  execute()  ┌──────┐│
│      │ PENDING  │ ───────────► │ APPROVED │ ──────────► │ DONE ││
│      └──────────┘              └──────────┘             └──────┘│
│           │                                                      │
│           │ reject()                                            │
│           ▼                                                      │
│      ┌──────────┐                                               │
│      │ REJECTED │                                               │
│      └──────────┘                                               │
│                                                                  │
│   Properties:                                                    │
│   • id: ToolCallId (UUID)                                       │
│   • name: str ("delete_pod", "list_services")                   │
│   • input: dict ({"name": "my-pod", "namespace": "prod"})       │
│   • status: ToolCallStatus                                      │
│   • result: Optional[str]                                       │
└─────────────────────────────────────────────────────────────────┘
```

#### 2. Application Layer (Use Case Orchestration)

This layer coordinates the domain to achieve use cases. It knows **what** to do but not **how** (that's for adapters).

| Component | Purpose | Example |
|-----------|---------|---------|
| **Services** | Orchestrate domain objects | `AgentService.execute()` |
| **Ports** | Interfaces for external dependencies | `AgentRuntime`, `ConversationRepository` |
| **DTOs** | Data transfer objects | `AgentRequest`, `AgentResponse` |

**Key Application Service:**

```python
# Simplified view of AgentService
class AgentService:
    def __init__(self, runtime: AgentRuntime, repo: ConversationRepository):
        self.runtime = runtime  # Port - implemented by adapters
        self.repo = repo        # Port - implemented by adapters
    
    def execute(self, request: AgentRequest) -> AgentResponse:
        # 1. Load or create conversation
        conversation = self.repo.get(request.conversation_id)
        
        # 2. Add user message to conversation
        conversation.add_user_message(request.message)
        
        # 3. Call the LLM via the runtime port
        llm_response = self.runtime.invoke(
            messages=conversation.messages,
            tools=request.tools,
        )
        
        # 4. Process tool calls with approval policy
        for tool_call in llm_response.tool_calls:
            if self.approval_policy.requires_approval(tool_call):
                conversation.add_pending_tool_call(tool_call)
            else:
                result = self._execute_tool(tool_call)
                conversation.add_executed_tool_call(tool_call, result)
        
        # 5. Return response
        return AgentResponse(
            text=llm_response.text,
            pending_tools=conversation.pending_tool_calls,
        )
```

**Ports (Interfaces):**

```
┌─────────────────────────────────────────────────────────────────┐
│                          PORTS                                   │
│           (Interfaces defined in Application layer)              │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  AgentRuntime (Port)                                     │   │
│   │  • invoke(messages, tools) → LLMResponse                 │   │
│   │  • invoke_stream(messages, tools) → Iterator[Event]      │   │
│   │                                                          │   │
│   │  Implemented by:                                         │   │
│   │  • AgnoAdapter (uses Agno SDK)                          │   │
│   │  • BedrockAdapter (direct AWS Bedrock)                  │   │
│   │  • LangChainAdapter (uses LangChain)                    │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  ConversationRepository (Port)                           │   │
│   │  • get(id) → Conversation                                │   │
│   │  • save(conversation)                                    │   │
│   │                                                          │   │
│   │  Implemented by:                                         │   │
│   │  • InMemoryConversationRepository                       │   │
│   │  • RedisConversationRepository                          │   │
│   │  • DynamoDBConversationRepository                       │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

#### 3. Adapters Layer (External World Translation)

Adapters translate between our domain and external systems. There are two types:

**Inbound Adapters** - Receive requests from the outside world:

```
┌─────────────────────────────────────────────────────────────────┐
│                      INBOUND ADAPTERS                            │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  ServerAdapter (FastAPI)                                 │   │
│   │                                                          │   │
│   │  HTTP Request                                            │   │
│   │      │                                                   │   │
│   │      ▼                                                   │   │
│   │  POST /api/chat                                          │   │
│   │  {"messages": [{"role": "user", "content": "..."}]}      │   │
│   │      │                                                   │   │
│   │      ▼                                                   │   │
│   │  Convert to AgentRequest                                 │   │
│   │      │                                                   │   │
│   │      ▼                                                   │   │
│   │  AgentService.execute(request)                           │   │
│   │      │                                                   │   │
│   │      ▼                                                   │   │
│   │  Convert AgentResponse to HTTP Response                  │   │
│   │      │                                                   │   │
│   │      ▼                                                   │   │
│   │  HTTP 200 {"content": "...", "tool_calls": [...]}        │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Outbound Adapters** - Call external systems:

```
┌─────────────────────────────────────────────────────────────────┐
│                      OUTBOUND ADAPTERS                           │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  AgnoAdapter (implements AgentRuntime)                   │   │
│   │                                                          │   │
│   │  Our Domain Format          Agno SDK Format              │   │
│   │  ─────────────────          ───────────────              │   │
│   │  Message                    agno.Message                 │   │
│   │  Tool                   →   agno.Tool                    │   │
│   │  ToolCall                   agno.ToolCall                │   │
│   │                                                          │   │
│   │  AgnoAdapter.invoke():                                   │   │
│   │  1. Convert our Messages → Agno Messages                 │   │
│   │  2. Convert our Tools → Agno Tools                       │   │
│   │  3. Call Agno SDK: agno_agent.run(messages, tools)       │   │
│   │  4. Convert Agno Response → our AgentResponse            │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  BedrockAdapter (implements AgentRuntime)                │   │
│   │                                                          │   │
│   │  1. Convert Messages → Bedrock API format                │   │
│   │  2. Convert Tools → Bedrock tool_config                  │   │
│   │  3. Call boto3: bedrock.invoke_model(...)                │   │
│   │  4. Parse Bedrock response → our AgentResponse           │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

### How Components Connect

Here's how a complete request flows through all layers:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           COMPLETE REQUEST FLOW                           │
└──────────────────────────────────────────────────────────────────────────┘

  User (HelpDesk UI)
       │
       │  POST /api/chat {"messages": [...]}
       ▼
┌──────────────────┐
│  FastAPI Server  │  ◄── Infrastructure (routes, middleware)
│  (agent_server)  │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  ServerAdapter   │  ◄── Inbound Adapter
│  (or Callable-   │      Converts HTTP → Domain format
│   Adapter)       │
└────────┬─────────┘
         │
         │  AgentRequest(messages=[...], tools=[...])
         ▼
┌──────────────────┐
│  AgentService    │  ◄── Application Service
│  (orchestrates)  │      Coordinates domain objects
└────────┬─────────┘
         │
         │  Calls port interface
         ▼
┌──────────────────┐
│  AgentRuntime    │  ◄── Application Port (interface)
│  (port/interface)│      Defines what we need, not how
└────────┬─────────┘
         │
         │  Implemented by...
         ▼
┌──────────────────┐
│  AgnoAdapter     │  ◄── Outbound Adapter
│  (or Bedrock-    │      Implements the port
│   Adapter)       │      Knows how to call the LLM
└────────┬─────────┘
         │
         │  Agno SDK / boto3 calls
         ▼
┌──────────────────┐
│  AWS Bedrock     │  ◄── External System
│  (Claude, etc.)  │      The actual LLM
└──────────────────┘
```

---

### The Agent Facade

The `Agent` class is a **facade** that hides all this complexity:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                             USER CODE                                     │
│                                                                          │
│   agent = Agent(tools=[list_pods], system="You are helpful")             │
│   result = agent.run(messages)                                           │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │  Internally creates and coordinates:
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                          AGENT FACADE (agent.py)                          │
│                                                                          │
│   class Agent:                                                           │
│       def __init__(self, tools, system):                                 │
│           # Create internal components                                   │
│           self._conversation = Conversation()        ◄── Domain Entity  │
│           self._runtime = AgnoAdapter(model, tools)  ◄── Outbound Adapter│
│           self._service = AgentService(runtime)      ◄── App Service    │
│                                                                          │
│       def run(self, messages) -> AgentResponse:                          │
│           # Delegate to internal service                                 │
│           return self._service.execute(AgentRequest(messages))           │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

### Why This Architecture?

| Benefit | How It's Achieved |
|---------|-------------------|
| **Testability** | Domain has no dependencies → easy unit tests |
| **Flexibility** | Swap LLM providers by changing adapters |
| **Maintainability** | Changes isolated to specific layers |
| **Framework Independence** | Agno/LangChain details don't leak into business logic |

**Example: Swapping LLM Providers**

```python
# Before: Using Agno
agent = Agent(tools=[...], runtime=AgnoAdapter())

# After: Using LangChain (no business logic changes!)
agent = Agent(tools=[...], runtime=LangChainAdapter())
```

Only the adapter changes. Domain logic, approval flows, and conversation management stay the same.

---

## HelpDesk Protocol Integration

DCAF agents communicate with the DuploCloud HelpDesk using a specific message protocol. Understanding this protocol is essential for server integration.

### Message Format

**Incoming Request (from HelpDesk):**

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Delete the pod my-pod in production",
      "data": {
        "cmds": [],
        "executed_cmds": [],
        "tool_calls": [],
        "executed_tool_calls": []
      },
      "platform_context": {
        "tenant_name": "production",
        "k8s_namespace": "default",
        "duplo_token": "...",
        "aws_credentials": {...}
      }
    },
    {
      "role": "assistant",
      "content": "I'll delete that pod. This requires your approval.",
      "data": {
        "tool_calls": [
          {
            "id": "tc_123",
            "name": "delete_pod",
            "input": {"name": "my-pod", "namespace": "default"},
            "execute": false,
            "tool_description": "Delete a Kubernetes pod"
          }
        ]
      }
    },
    {
      "role": "user",
      "content": "",
      "data": {
        "tool_calls": [
          {
            "id": "tc_123",
            "name": "delete_pod",
            "input": {"name": "my-pod", "namespace": "default"},
            "execute": true  // ◄── User approved!
          }
        ]
      }
    }
  ]
}
```

**Outgoing Response (to HelpDesk):**

```json
{
  "role": "assistant",
  "content": "The pod my-pod has been deleted.",
  "data": {
    "tool_calls": [],
    "executed_tool_calls": [
      {
        "id": "tc_123",
        "name": "delete_pod",
        "input": {"name": "my-pod", "namespace": "default"},
        "output": "pod \"my-pod\" deleted"
      }
    ],
    "cmds": [],
    "executed_cmds": []
  }
}
```

### Protocol Fields Explained

| Field | Purpose |
|-------|---------|
| `tool_calls` | Tools that need approval (`execute: false`) or were approved (`execute: true`) |
| `executed_tool_calls` | Tools that were executed this turn, with their output |
| `cmds` | Terminal commands that need approval |
| `executed_cmds` | Terminal commands that were executed, with output |
| `platform_context` | Runtime environment (credentials, namespace, tenant) |

### Core DTOs (Recommended)

DCAF Core provides Python dataclasses that match this protocol exactly:

```python
from dcaf.core import (
    PlatformContext,    # platform_context
    DataDTO,            # data container
    CommandDTO,         # cmds entries
    ExecutedCommandDTO, # executed_cmds entries
    ToolCallDTO,        # tool_calls entries
    ExecutedToolCallDTO,# executed_tool_calls entries
    StreamEvent,        # streaming events
)

# Example: Create a response with pending tool call
from dcaf.core import AgentResponse, DataDTO, ToolCallDTO

response = AgentResponse(
    conversation_id="123",
    text="I need approval to delete the pod.",
    data=DataDTO(
        tool_calls=[
            ToolCallDTO(
                id="tc_123",
                name="delete_pod",
                input={"name": "my-pod"},
                execute=False,
                tool_description="Delete a Kubernetes pod",
            )
        ]
    ),
    has_pending_approvals=True,
)

# Convert to HelpDesk message format
helpdesk_msg = response.to_helpdesk_message()
```

See [HelpDesk Protocol Guide](./core/helpdesk-protocol.md) for full documentation.

### Approval Flow Sequence

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          TOOL APPROVAL SEQUENCE                              │
└─────────────────────────────────────────────────────────────────────────────┘

  HelpDesk                         DCAF Agent                        LLM
     │                                 │                              │
     │  1. User: "delete pod x"        │                              │
     │ ─────────────────────────────►  │                              │
     │                                 │  2. Call LLM                 │
     │                                 │ ────────────────────────────►│
     │                                 │                              │
     │                                 │  3. LLM: tool_use delete_pod │
     │                                 │ ◄────────────────────────────│
     │                                 │                              │
     │  4. Response with tool_calls    │                              │
     │     [execute: false]            │                              │
     │ ◄─────────────────────────────  │                              │
     │                                 │                              │
     │  ┌─────────────────────────┐    │                              │
     │  │  User sees approval UI  │    │                              │
     │  │  [Approve] [Reject]     │    │                              │
     │  └─────────────────────────┘    │                              │
     │                                 │                              │
     │  5. User clicks Approve         │                              │
     │     tool_calls[execute: true]   │                              │
     │ ─────────────────────────────►  │                              │
     │                                 │  6. Execute tool             │
     │                                 │     kubectl delete pod x     │
     │                                 │                              │
     │                                 │  7. Call LLM with result     │
     │                                 │ ────────────────────────────►│
     │                                 │                              │
     │                                 │  8. LLM: final response      │
     │                                 │ ◄────────────────────────────│
     │                                 │                              │
     │  9. Response with:              │                              │
     │     executed_tool_calls         │                              │
     │     content: "Pod deleted"      │                              │
     │ ◄─────────────────────────────  │                              │
     │                                 │                              │
```

### Streaming Protocol

For `/api/chat-stream`, responses are NDJSON (newline-delimited JSON):

```
{"type": "text_delta", "text": "I'll "}
{"type": "text_delta", "text": "delete "}
{"type": "text_delta", "text": "that pod."}
{"type": "tool_calls", "tool_calls": [...]}
{"type": "done"}
```

| Event Type | Purpose |
|------------|---------|
| `text_delta` | Incremental text tokens |
| `tool_calls` | Tools that need approval |
| `executed_tool_calls` | Tools that were just executed |
| `commands` | Terminal commands that need approval |
| `executed_commands` | Terminal commands that were executed |
| `done` | Stream complete |
| `error` | Error occurred |

---

## Key Concepts & Ubiquitous Language

| Term | Definition |
|------|------------|
| **Conversation** | A sequence of messages between user and agent; the aggregate root |
| **Turn** | One user message followed by one agent response |
| **Message** | A single communication unit with role (user/assistant) and content |
| **Tool** | A capability the agent can invoke (e.g., kubectl, AWS CLI) |
| **Tool Call** | A request to execute a tool with specific inputs; has lifecycle (pending→approved→executed) |
| **Approval Gate** | A checkpoint requiring human authorization before tool execution |
| **Platform Context** | Runtime environment data (tenant, namespace, credentials) |
| **Session** | Key-value store for persisting state across conversation turns |
| **Agent Runtime** | The port/interface that framework adapters implement |
| **Adapter** | Translates between our domain and a specific framework |

---

## How a Request Flows

### Simple Flow (No Approval Needed)

```
1. HTTP POST /chat
      │
      ▼
2. FastAPI Controller
      │ Converts HTTP → AgentRequest
      ▼
3. AgentService.execute()
      │ Loads conversation, adds message
      ▼
4. AgentRuntime.invoke() [via adapter]
      │ Calls LLM, gets tool calls
      ▼
5. Tool has requires_approval=False
      │ Execute immediately
      ▼
6. Return AgentResponse
      │
      ▼
7. HTTP 200 with response
```

### Flow with Approval Required

```
1. HTTP POST /chat
      │
      ▼
2-4. Same as above...
      │
      ▼
5. Tool has requires_approval=True
      │
      ▼
6. Return response with pending ToolCalls
      │ status=PENDING
      ▼
7. HTTP 200 with tool_calls requiring approval
      │
      ▼
8. User reviews in UI, clicks Approve
      │
      ▼
9. HTTP POST /chat with execute=true on ToolCall
      │
      ▼
10. Use case sees approved tool, executes it
      │
      ▼
11. Continue with execution result
```

---

## Human-in-the-Loop Explained

### Why Approvals Exist

Autonomous agents executing infrastructure operations is risky:

- **Destructive actions**: `kubectl delete pod` or `aws ec2 terminate-instances`
- **Irreversible changes**: Data deletion, resource destruction
- **Compliance**: Some environments require human sign-off
- **Cost**: Expensive operations should be reviewed

### How Approvals Work

1. **Tool Configuration**: Each `Tool` has `requires_approval: bool`

2. **Approval Policy**: Domain service that determines if a specific call needs approval based on tool config and context

3. **ToolCall Lifecycle**:
   ```
   PENDING ──approve()──► APPROVED ──execute()──► COMPLETED
      │                                               
      └──reject(reason)──► REJECTED
   ```

4. **Conversation Blocking**: The `Conversation` aggregate won't accept new messages while tool calls are pending

### Implementation Points

- `ToolCall` entity in `domain/entities/tool_call.py`
- `ApprovalPolicy` service in `domain/services/approval_policy.py`
- `ApprovalCallback` port in `application/ports/approval_callback.py`

---

## Session Management

Sessions provide a mechanism for persisting state across conversation turns. This is essential for multi-step workflows where tools need to share data.

### Session Class

The `Session` class (`dcaf/core/session.py`) is a key-value store with typed serialization support:

```python
from dcaf.core import Session

session = Session()

# Basic operations
session.set("user_id", "12345")
user_id = session.get("user_id")
session.delete("user_id")

# With defaults
count = session.get("count", 0)

# Dict-like access
session["key"] = "value"
value = session["key"]

# Bulk operations
session.update({"a": 1, "b": 2})
session.clear()
```

### Typed Storage

Session supports automatic serialization/deserialization of Pydantic models and dataclasses:

```python
from pydantic import BaseModel
from dcaf.core import Session

class UserPrefs(BaseModel):
    theme: str = "light"
    language: str = "en"

session = Session()

# Store Pydantic model (auto-serializes via model_dump())
session.set("prefs", UserPrefs(theme="dark"))

# Retrieve as typed model (auto-deserializes via model_validate())
prefs = session.get("prefs", as_type=UserPrefs)
print(prefs.theme)  # "dark"

# Without type - returns raw dict
raw = session.get("prefs")  # {"theme": "dark", "language": "en"}
```

**Serialization/Deserialization:**

| Type | Serialization | Deserialization |
|------|---------------|-----------------|
| Pydantic model | `model_dump()` | `model_validate()` |
| Dataclass | `asdict()` | Constructor `cls(**data)` |
| Primitives/dicts | Stored as-is | Returned as-is |

### Using Session in Tools

Tools can declare a `Session` parameter that DCAF automatically injects:

```python
from pydantic import BaseModel, Field
from dcaf.core import Session
from dcaf.tools import tool

class ShoppingCart(BaseModel):
    items: list[dict] = Field(default_factory=list)

@tool(description="Add item to cart")
def add_to_cart(item: str, quantity: int, session: Session) -> str:
    # Get as typed model
    cart = session.get("cart", as_type=ShoppingCart) or ShoppingCart()
    cart.items.append({"item": item, "quantity": quantity})
    session.set("cart", cart)
    return f"Added {quantity}x {item}"
```

### Protocol Integration

Session data travels with the HelpDesk protocol in the `data.session` field:

**Response (agent → HelpDesk):**

```json
{
  "role": "assistant",
  "content": "Added item to cart.",
  "data": {
    "session": {
      "cart": [{"item": "Widget", "quantity": 2}]
    }
  }
}
```

**Subsequent Request (HelpDesk → agent):**

```json
{
  "messages": [{
    "role": "user",
    "content": "What's in my cart?",
    "data": {
      "session": {
        "cart": [{"item": "Widget", "quantity": 2}]
      }
    }
  }]
}
```

### Implementation Points

- `Session` class in `dcaf/core/session.py`
- Session injection in tool execution pipeline
- Serialization in `AgentResponse.to_helpdesk_message()`

---

## Tool Schema Options

DCAF supports three ways to define tool schemas, providing flexibility from simple auto-generation to full type-safe Pydantic models:

### Option 1: Auto-Generate from Function Signature

```python
@tool(description="List pods")
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")
```

Schema is automatically generated from type hints.

### Option 2: Explicit Dict Schema

```python
@tool(
    description="Delete a pod",
    schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Pod name"},
            "namespace": {"type": "string", "default": "default"}
        },
        "required": ["name"]
    }
)
def delete_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"delete pod {name} -n {namespace}")
```

### Option 3: Pydantic Model

```python
from pydantic import BaseModel, Field

class DeletePodInput(BaseModel):
    name: str = Field(..., description="Pod name")
    namespace: str = Field(default="default")

@tool(description="Delete a pod", schema=DeletePodInput)
def delete_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"delete pod {name} -n {namespace}")
```

DCAF automatically converts Pydantic models to JSON schema via `model_json_schema()`.

### Accessing Tool Schema

The `Tool` class provides access to the schema:

```python
tool = create_tool(delete_pod)
print(tool.name)         # "delete_pod"
print(tool.description)  # "Delete a pod"
print(tool.schema)       # Full schema dict including input_schema
```

---

## Adding a New Framework Adapter

Example: Adding a LangChain adapter

### Step 1: Create the Adapter Folder

```
dcaf/core/adapters/outbound/langchain/
├── __init__.py
├── adapter.py
├── tool_converter.py
├── message_converter.py
└── types.py
```

### Step 2: Implement the Tool Converter

```python
# tool_converter.py
from dcaf.tools import Tool

class LangChainToolConverter:
    def to_langchain(self, tool: Tool) -> dict:
        """Convert dcaf Tool to LangChain tool format."""
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.schema["input_schema"],
        }
```

### Step 3: Implement the Message Converter

```python
# message_converter.py
from dcaf.core.domain.entities import Message
from dcaf.core.application.dto import AgentResponse

class LangChainMessageConverter:
    def to_langchain(self, messages: List[Message]) -> List[dict]:
        """Convert dcaf Messages to LangChain format."""
        ...
    
    def from_langchain(self, response) -> AgentResponse:
        """Convert LangChain response to our domain."""
        ...
```

### Step 4: Implement the Adapter

```python
# adapter.py
from dcaf.core.application.ports import AgentRuntime

class LangChainAdapter(AgentRuntime):
    def __init__(self, model: str):
        self._tool_converter = LangChainToolConverter()
        self._message_converter = LangChainMessageConverter()
        # Initialize LangChain components
    
    def invoke(self, messages, tools) -> AgentResponse:
        lc_messages = self._message_converter.to_langchain(messages)
        lc_tools = [self._tool_converter.to_langchain(t) for t in tools]
        
        response = self._chain.invoke(lc_messages, tools=lc_tools)
        
        return self._message_converter.from_langchain(response)
```

### Step 5: Export from `__init__.py`

```python
from .adapter import LangChainAdapter
__all__ = ["LangChainAdapter"]
```

---

## Testing Philosophy

### Test Against Abstractions

We test business logic using fake implementations of ports, not real frameworks:

```python
# tests/test_execute_agent.py
def test_execute_agent_with_approval():
    fake_runtime = FakeAgentRuntime()
    fake_runtime.will_return_tool_call("kubectl_delete", requires_approval=True)
    
    service = AgentService(runtime=fake_runtime, ...)
    response = service.execute(request)
    
    assert response.pending_approvals == 1
```

### Testing Layers

| Layer | What to Test | How to Test |
|-------|--------------|-------------|
| Domain | Entities, VOs, Services | Unit tests, no mocks needed |
| Application | Use cases | Fake implementations of ports |
| Adapters | Converters, integration | Real framework, integration tests |

---

## Where to Find Things

```
dcaf/core/
├── domain/                    # Pure business logic
│   ├── entities/              # ToolCall, Message, Conversation
│   ├── value_objects/         # ToolCallId, ToolInput, etc.
│   ├── services/              # ApprovalPolicy
│   ├── events/                # Domain events
│   └── exceptions.py          # Domain exceptions
│
├── application/               # Use case orchestration
│   ├── services/             # ExecuteAgent, ApproveToolCall
│   ├── ports/                 # AgentRuntime, ConversationRepository
│   └── dto/                   # Request/Response objects
│
├── adapters/                  # External integrations
│   ├── inbound/               # HTTP controllers
│   └── outbound/              # Framework adapters
│       ├── agno/              # Agno-specific code
│       └── langchain/         # LangChain-specific code
│
├── infrastructure/            # Cross-cutting concerns
│   ├── config.py
│   └── logging.py
│
└── testing/                   # Test support
    ├── fakes.py               # Fake implementations
    ├── builders.py            # Test data builders
    └── fixtures.py            # pytest fixtures
```

---

## A2A (Agent-to-Agent) Protocol

DCAF supports the A2A (Agent-to-Agent) protocol developed by Google, enabling agents to discover and communicate with each other using standardized HTTP/JSON-RPC interfaces.

### What is A2A?

A2A is an open protocol for agent-to-agent communication that enables:

- **Agent Discovery**: Agents expose a card describing their capabilities
- **Task Execution**: Agents can send tasks to other agents
- **Async Support**: Long-running tasks can execute asynchronously
- **Standard Protocol**: Uses HTTP, JSON-RPC, and SSE (Server-Sent Events)

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         A2A ARCHITECTURE                         │
└─────────────────────────────────────────────────────────────────┘

  ┌──────────────┐                          ┌──────────────┐
  │ Orchestrator │                          │ K8s Agent    │
  │   Agent      │                          │ (Specialist) │
  └──────┬───────┘                          └──────▲───────┘
         │                                         │
         │  1. Fetch Agent Card                   │
         │  GET /.well-known/agent.json           │
         │─────────────────────────────────────────│
         │                                         │
         │  2. Send Task                           │
         │  POST /a2a/tasks/send                   │
         │  {"message": "List failing pods"}       │
         │─────────────────────────────────────────│
         │                                         │
         │  3. TaskResult                          │
         │  {"text": "Found 3 failing pods..."}    │
         │◄─────────────────────────────────────────│
         │                                         │
```

### Code Structure

```
dcaf/core/a2a/
├── __init__.py          # Public exports: RemoteAgent, AgentCard, etc.
├── models.py            # AgentCard, Task, TaskResult, Artifact
├── client.py            # RemoteAgent (user-facing client)
├── server.py            # A2A server routes/utilities
├── protocols.py         # Abstract interfaces (for swapping implementations)
└── adapters/
    ├── __init__.py
    └── agno.py          # Agno A2A implementation (hidden from users)
```

### User-Facing API

**Server Side (Exposing an Agent):**

```python
from dcaf.core import Agent, serve

agent = Agent(
    name="k8s-assistant",              # A2A identity
    description="Kubernetes helper",   # A2A description
    tools=[list_pods, delete_pod],
)

# Enable A2A alongside REST API
serve(agent, port=8000, a2a=True)
```

**Client Side (Calling Remote Agents):**

```python
from dcaf.core.a2a import RemoteAgent

# Connect to remote agent
k8s = RemoteAgent(url="http://k8s-agent:8000")

# Direct call
result = k8s.send("What pods are failing in production?")
print(result.text)

# Use as a tool for another agent
orchestrator = Agent(
    tools=[k8s.as_tool()],
    system="Route requests to specialist agents"
)
```

### Internal Implementation

The A2A implementation follows DCAF's adapter pattern to remain framework-agnostic:

1. **Protocols** (`protocols.py`): Abstract interfaces for A2A client and server
2. **Models** (`models.py`): Framework-agnostic data structures (AgentCard, Task, etc.)
3. **Adapters** (`adapters/agno.py`): Concrete implementation using Agno's A2A support
4. **Facades** (`client.py`, `server.py`): User-facing APIs that hide implementation details

This allows swapping A2A implementations (e.g., from Agno to a custom implementation) without changing user code.

### A2A Protocol Endpoints

When `serve(agent, a2a=True)` is called, these endpoints are added:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/.well-known/agent.json` | GET | Agent card (discovery) |
| `/a2a/tasks/send` | POST | Receive tasks from other agents |
| `/a2a/tasks/{id}` | GET | Task status (for async tasks) |

### AgentCard Generation

Agent cards are automatically generated from DCAF Agent configuration:

```python
{
  "name": "k8s-assistant",                    # From agent.name
  "description": "Manages Kubernetes...",     # From agent.description
  "url": "http://k8s-agent:8000",            # From server URL
  "skills": ["list_pods", "delete_pod"],     # From agent.tools
  "version": "1.0",                          # A2A protocol version
  "metadata": {
    "framework": "dcaf",
    "model": "anthropic.claude-3-sonnet...",
    "provider": "bedrock"
  }
}
```

### Multi-Agent Patterns

**Peer-to-Peer:**

```python
# Agent 1
k8s = Agent(name="k8s", tools=[...])
serve(k8s, port=8001, a2a=True)

# Agent 2
aws = Agent(name="aws", tools=[...])
serve(aws, port=8002, a2a=True)

# Each can call the other
k8s_remote = RemoteAgent(url="http://localhost:8001")
aws_remote = RemoteAgent(url="http://localhost:8002")
```

**Orchestration:**

```python
# Specialist agents
k8s = RemoteAgent(url="http://k8s-agent:8000")
aws = RemoteAgent(url="http://aws-agent:8000")

# Orchestrator routes to specialists
orchestrator = Agent(
    name="orchestrator",
    tools=[k8s.as_tool(), aws.as_tool()],
    system="Route to the appropriate specialist agent"
)
```

### Testing A2A Agents

Use the `RemoteAgent` client to test A2A-enabled agents:

```python
from dcaf.core.a2a import RemoteAgent

# Start agent with A2A
agent = Agent(name="test", tools=[...])
serve(agent, port=8000, a2a=True)

# Test from another process/terminal
remote = RemoteAgent(url="http://localhost:8000")

# Check agent card
print(remote.card.name)       # "test"
print(remote.card.skills)     # Tool names

# Send task
result = remote.send("List pods")
assert result.status == "completed"
```

### Future Enhancements

- **Dynamic Discovery**: Agent registry/service mesh integration
- **Streaming Tasks**: Real-time task updates via SSE
- **Hierarchical Teams**: Agents managing sub-agents
- **Workflow Orchestration**: Complex multi-agent workflows

---

## Related ADRs

- [ADR-001: Clean Architecture](adrs/001-clean-architecture.md)
- [ADR-002: DDD Tactical Patterns](adrs/002-ddd-tactical-patterns.md)
- [ADR-003: Adapter Pattern for Frameworks](adrs/003-adapter-pattern-for-frameworks.md)
- [ADR-004: Approval-First Design](adrs/004-approval-first-design.md)
- [ADR-005: Cohesive Provider Modules](adrs/005-cohesive-provider-modules.md)
- [ADR-006: Strangler Fig Migration](adrs/006-strangler-fig-migration.md)
- [ADR-007: Lowercase Chat Endpoints](adrs/007-lowercase-chat-endpoints.md)
