# Architecture Guide

This guide explains how DCAF works internally, so you can understand, extend, and troubleshoot it effectively.

---

## Table of Contents

1. [Overview](#overview)
2. [High-Level Flow](#high-level-flow)
3. [Core Components](#core-components)
4. [Request Lifecycle](#request-lifecycle)
5. [Tool Execution & Approval](#tool-execution--approval)
6. [Streaming](#streaming)
7. [Extending DCAF](#extending-dcaf)
8. [Key Design Decisions](#key-design-decisions)

---

## Overview

DCAF is structured in layers that separate concerns:

```
┌─────────────────────────────────────────────────────────────────┐
│                         YOUR CODE                                │
│                                                                  │
│   from dcaf.core import Agent, serve                            │
│   agent = Agent(tools=[...])                                    │
│   serve(agent)                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                     ┌─────────────────┐                         │
│                     │     Agent       │  ◄── Facade (simple API)│
│                     │   (agent.py)    │                         │
│                     └────────┬────────┘                         │
│                              │                                   │
│              ┌───────────────┼───────────────┐                  │
│              ▼               ▼               ▼                  │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│   │ Conversation │  │ AgentService │  │  LLM Adapter │         │
│   │   (Domain)   │  │ (Application)│  │  (Outbound)  │         │
│   └──────────────┘  └──────────────┘  └──────────────┘         │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                       SERVER LAYER                               │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  FastAPI  →  ServerAdapter  →  Agent  →  Response       │   │
│   │  /api/chat                                              │   │
│   │  /api/chat-stream                                       │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key insight**: The `Agent` class is a **facade** that hides internal complexity. Most users only interact with `Agent` and `@tool`.

---

## High-Level Flow

Here's what happens when a request comes in:

```
  HelpDesk UI                           DCAF                              AWS Bedrock
      │                                   │                                    │
      │  POST /api/chat                   │                                    │
      │  {"messages": [...]}              │                                    │
      │ ─────────────────────────────────►│                                    │
      │                                   │                                    │
      │                           ┌───────┴───────┐                           │
      │                           │ 1. Parse      │                           │
      │                           │    request    │                           │
      │                           └───────┬───────┘                           │
      │                                   │                                    │
      │                           ┌───────┴───────┐                           │
      │                           │ 2. Extract    │                           │
      │                           │    context    │                           │
      │                           │    & history  │                           │
      │                           └───────┬───────┘                           │
      │                                   │                                    │
      │                           ┌───────┴───────┐   invoke_model()          │
      │                           │ 3. Call LLM   │ ─────────────────────────►│
      │                           │    with tools │                           │
      │                           └───────┬───────┘                           │
      │                                   │                  tool_use          │
      │                                   │ ◄─────────────────────────────────│
      │                           ┌───────┴───────┐                           │
      │                           │ 4. Process    │                           │
      │                           │    tool calls │                           │
      │                           └───────┬───────┘                           │
      │                                   │                                    │
      │                       ┌───────────┴───────────┐                       │
      │                       │                       │                       │
      │               needs_approval?            auto_execute                 │
      │                       │                       │                       │
      │                       ▼                       ▼                       │
      │               ┌───────────────┐      ┌───────────────┐               │
      │               │ Return with   │      │ Execute tool  │               │
      │               │ pending tools │      │ Return result │               │
      │               └───────┬───────┘      └───────┬───────┘               │
      │                       │                       │                       │
      │                       └───────────┬───────────┘                       │
      │                                   │                                    │
      │  {"content": "...",              │                                    │
      │   "tool_calls": [...]}           │                                    │
      │ ◄─────────────────────────────────│                                    │
      │                                   │                                    │
```

---

## Core Components

### 1. Agent (Facade)

**File**: `dcaf/core/agent.py`

The main entry point. Hides all internal complexity.

```python
from dcaf.core import Agent

agent = Agent(
    tools=[list_pods, delete_pod],  # Tools available to the LLM
    system="You are a K8s assistant", # System prompt
    model="anthropic.claude-3-sonnet", # LLM model
)

response = agent.run(messages=[...])
```

**What it does internally**:

1. Creates a `Conversation` entity to track messages
2. Creates an `AgentService` to orchestrate the request
3. Creates an `LLM Adapter` to call AWS Bedrock
4. Wires everything together

### 2. Conversation (Domain Entity)

**File**: `dcaf/core/domain/entities/conversation.py`

Tracks the state of a conversation:

```
┌──────────────────────────────────────────────────────────────────┐
│                         Conversation                              │
│                                                                   │
│   messages: [Message, Message, ...]     ◄── Chat history         │
│   tool_calls: [ToolCall, ToolCall, ...] ◄── Pending & executed   │
│   platform_context: {...}               ◄── Runtime info         │
│                                                                   │
│   Methods:                                                        │
│   • add_user_message(content)                                    │
│   • add_assistant_message(content)                               │
│   • add_tool_call(name, input)                                   │
│   • approve_tool_call(id)                                        │
│   • execute_tool_call(id, result)                                │
└──────────────────────────────────────────────────────────────────┘
```

### 3. ToolCall (Domain Entity)

**File**: `dcaf/core/domain/entities/tool_call.py`

Represents a single tool invocation with a lifecycle:

```
                      ┌──────────┐
                      │ PENDING  │
                      └────┬─────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            │            ▼
       ┌──────────┐        │     ┌──────────┐
       │ APPROVED │        │     │ REJECTED │
       └────┬─────┘        │     └──────────┘
            │              │
            ▼              │
       ┌──────────┐        │
       │ EXECUTED │        │
       └──────────┘        │
                           │
                           ▼
                    (auto-execute if
                     requires_approval=False)
```

**Properties**:

| Property | Description |
|----------|-------------|
| `id` | Unique identifier (UUID) |
| `name` | Tool name (e.g., "delete_pod") |
| `input` | Arguments passed to the tool |
| `status` | PENDING, APPROVED, REJECTED, EXECUTED |
| `result` | Output after execution |

### 4. AgentService (Application Layer)

**File**: `dcaf/core/application/services/agent_service.py`

Orchestrates the agent logic:

```python
class AgentService:
    def execute(self, request: AgentRequest) -> AgentResponse:
        # 1. Get or create conversation
        conversation = self._get_conversation(request)
        
        # 2. Add user message
        conversation.add_user_message(request.message)
        
        # 3. Call LLM via adapter
        llm_response = self._runtime.invoke(
            messages=conversation.messages,
            tools=request.tools,
        )
        
        # 4. Process tool calls
        for tool_call in llm_response.tool_calls:
            if self._requires_approval(tool_call):
                # Mark as pending - user must approve
                conversation.add_pending_tool_call(tool_call)
            else:
                # Auto-execute
                result = self._execute_tool(tool_call)
                conversation.add_executed_tool_call(tool_call, result)
        
        # 5. Build response
        return AgentResponse(
            text=llm_response.text,
            pending_tools=conversation.pending_tool_calls,
            executed_tools=conversation.executed_tool_calls,
        )
```

### 5. LLM Adapter (Outbound)

**File**: `dcaf/core/adapters/outbound/agno/adapter.py`

Translates between DCAF and the LLM provider:

```
┌─────────────────────────────────────────────────────────────────┐
│                        LLM Adapter                               │
│                                                                  │
│   DCAF Format                         Provider Format            │
│   ───────────                         ───────────────            │
│                                                                  │
│   Message(role, content)      ─────►  {"role": "user", ...}     │
│   Tool(name, schema)          ─────►  {"name": "...", ...}      │
│                                                                  │
│   LLMResponse                 ◄─────  Bedrock API Response      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Why adapters matter**: You can swap LLM providers (Bedrock, OpenAI, local) without changing your agent code.

### 6. ServerAdapter (Inbound)

**File**: `dcaf/core/adapters/inbound/server_adapter.py`

Bridges FastAPI and your Agent:

```
HTTP Request                    ServerAdapter                    Agent
    │                               │                              │
    │  POST /api/chat               │                              │
    │  {"messages": [...]}          │                              │
    │ ─────────────────────────────►│                              │
    │                               │                              │
    │                        ┌──────┴──────┐                       │
    │                        │ Convert to  │                       │
    │                        │ DCAF format │                       │
    │                        └──────┬──────┘                       │
    │                               │                              │
    │                               │  agent.run(messages)         │
    │                               │ ────────────────────────────►│
    │                               │                              │
    │                               │  AgentResponse               │
    │                               │ ◄────────────────────────────│
    │                               │                              │
    │                        ┌──────┴──────┐                       │
    │                        │ Convert to  │                       │
    │                        │ HelpDesk    │                       │
    │                        │ protocol    │                       │
    │                        └──────┬──────┘                       │
    │                               │                              │
    │  AgentMessage (JSON)          │                              │
    │ ◄─────────────────────────────│                              │
```

---

## Request Lifecycle

### Step-by-Step

1. **HTTP Request arrives** at `/api/chat`
2. **ServerAdapter** extracts messages and platform_context
3. **Agent.run()** is called with the messages
4. **AgentService** creates/loads a Conversation
5. **LLM Adapter** sends request to AWS Bedrock
6. **Bedrock** returns text and/or tool_use blocks
7. **AgentService** checks each tool call:
   - `requires_approval=True` → add to pending
   - `requires_approval=False` → execute immediately
8. **AgentResponse** is built with text + pending/executed tools
9. **ServerAdapter** converts to HelpDesk protocol format
10. **HTTP Response** sent back

### Approval Loop

When tools require approval, the flow pauses:

```
Request 1: "Delete the broken pods"
    │
    ▼
Response: { tool_calls: [{name: "delete_pod", execute: false}] }
    │
    │  User sees approval UI in HelpDesk
    │  User clicks "Approve"
    │
    ▼
Request 2: { tool_calls: [{name: "delete_pod", execute: true}] }
    │
    ▼
Response: { executed_tool_calls: [{output: "pod deleted"}] }
```

---

## Tool Execution & Approval

### How Approval is Determined

```python
def requires_approval(tool, tool_call, context):
    # 1. Check tool configuration
    if tool.requires_approval:
        return True
    
    # 2. Check high-risk tools list
    if tool.name in agent.high_risk_tools:
        return True
    
    # 3. Check approval policy (custom logic)
    if approval_policy.is_risky(tool_call, context):
        return True
    
    return False
```

### Tool Execution Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                       Tool Execution                             │
│                                                                  │
│   1. Find tool by name                                          │
│      └── tools = {name: tool for tool in agent.tools}           │
│                                                                  │
│   2. Extract input parameters                                   │
│      └── input = {"pod_name": "nginx", "namespace": "prod"}     │
│                                                                  │
│   3. Call tool function                                         │
│      └── result = tool.execute(input, platform_context)         │
│                                                                  │
│   4. Capture result                                             │
│      └── "pod nginx deleted"                                    │
│                                                                  │
│   5. Add to conversation                                        │
│      └── conversation.add_executed_tool_call(tool_call, result) │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Streaming

For real-time responses, DCAF uses NDJSON (newline-delimited JSON):

```
POST /api/chat-stream

Response (line by line):
{"type": "text_delta", "text": "I'll "}
{"type": "text_delta", "text": "help "}
{"type": "text_delta", "text": "you "}
{"type": "text_delta", "text": "delete "}
{"type": "text_delta", "text": "that pod."}
{"type": "tool_calls", "tool_calls": [...]}
{"type": "done"}
```

### Stream Events

| Event Type | Description |
|------------|-------------|
| `text_delta` | Incremental text token |
| `tool_calls` | Tools needing approval |
| `executed_tool_calls` | Tools that were executed |
| `done` | Stream complete |
| `error` | Error occurred |

### Implementation

```python
for event in agent.run_stream(messages=[...]):
    if isinstance(event, TextDeltaEvent):
        print(event.text, end="", flush=True)
    elif isinstance(event, ToolCallsEvent):
        # Handle approval UI
        pass
    elif isinstance(event, DoneEvent):
        break
```

---

## Extending DCAF

### Adding a New LLM Provider

1. **Create an adapter** that implements `AgentRuntime`:

```python
# dcaf/core/adapters/outbound/openai/adapter.py

from dcaf.core.application.ports import AgentRuntime

class OpenAIAdapter(AgentRuntime):
    def __init__(self, model: str = "gpt-4"):
        self.client = OpenAI()
        self.model = model
    
    def invoke(self, messages, tools) -> AgentResponse:
        # Convert messages to OpenAI format
        openai_messages = self._convert_messages(messages)
        openai_tools = self._convert_tools(tools)
        
        # Call OpenAI
        response = self.client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            tools=openai_tools,
        )
        
        # Convert back to DCAF format
        return self._convert_response(response)
```

2. **Use it**:

```python
from dcaf.core import Agent
from dcaf.core.adapters.outbound.openai import OpenAIAdapter

agent = Agent(
    tools=[...],
    runtime=OpenAIAdapter("gpt-4"),
)
```

### Adding Custom Approval Logic

```python
from dcaf.core.domain.services import ApprovalPolicy

class StrictProductionPolicy(ApprovalPolicy):
    def requires_approval(self, tool_call, context):
        # Always require approval in production
        if context.get("tenant_name") == "production":
            return True
        
        # Require approval for destructive actions
        if any(word in tool_call.name for word in ["delete", "remove", "drop"]):
            return True
        
        return False

# Use custom policy
agent = Agent(
    tools=[...],
    approval_policy=StrictProductionPolicy(),
)
```

### Adding Custom Event Handlers

```python
def audit_logger(event):
    """Log all events to audit system."""
    log_to_audit_db({
        "event_type": event.event_type,
        "timestamp": event.timestamp,
        "data": event.data,
    })

def slack_notifier(event):
    """Notify Slack on approvals."""
    if event.event_type == "ApprovalRequested":
        post_to_slack(f"Approval needed: {event.tool_name}")

agent = Agent(
    tools=[...],
    on_event=[audit_logger, slack_notifier],
)
```

---

## Key Design Decisions

### Why Clean Architecture?

| Benefit | How It Helps |
|---------|--------------|
| **Testability** | Test business logic without LLM calls |
| **Flexibility** | Swap LLM providers without code changes |
| **Maintainability** | Changes isolated to specific layers |

### Why Facade Pattern?

Most users don't need to understand the internals. The `Agent` class provides a simple API:

```python
# User sees this (simple):
agent = Agent(tools=[...])
response = agent.run(messages)

# Internally it's this (complex):
conversation = Conversation()
service = AgentService(
    runtime=AgnoAdapter(),
    repository=InMemoryConversationRepository(),
    approval_policy=DefaultApprovalPolicy(),
)
response = service.execute(AgentRequest(...))
```

### Why Protocol-First?

DCAF is designed to work with the DuploCloud HelpDesk. The message format (`tool_calls`, `executed_tool_calls`, etc.) is defined by the HelpDesk protocol, and DCAF adapts to it.

---

## See Also

- [Message Protocol Guide](./guides/message-protocol.md) - Complete protocol reference
- [Core API](./core/index.md) - Agent class documentation
- [Server Documentation](./core/server.md) - Running as REST API
- [Custom Agents Guide](./guides/custom-agents.md) - Building complex agents
