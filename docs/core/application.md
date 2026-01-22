# Application Layer

The application layer orchestrates domain logic with infrastructure through use cases and ports. It contains no business logic itself—that belongs in the domain.

---

## Overview

The application layer includes:

- **Ports**: Interfaces (protocols) for external systems
- **Services**: Application services that orchestrate operations
- **DTOs**: Data transfer objects for communication

---

## Ports

Ports define how the application interacts with external systems. They are implemented by adapters.

### AgentRuntime

The primary port for LLM framework integration.

```python
from dcaf.core.application.ports import AgentRuntime
from typing import Protocol, List, Iterator

class AgentRuntime(Protocol):
    """Port that adapters implement."""
    
    def invoke(
        self, 
        messages: List[Message],
        tools: List[Tool],
        system_prompt: Optional[str] = None,
    ) -> AgentResponse:
        """Synchronous agent invocation."""
        ...
    
    def invoke_stream(
        self, 
        messages: List[Message],
        tools: List[Tool],
        system_prompt: Optional[str] = None,
    ) -> Iterator[StreamEvent]:
        """Streaming agent invocation."""
        ...
```

**Implementations:**
- `AgnoAdapter` - Agno framework
- `LangChainAdapter` - LangChain framework (future)
- `BedrockDirectAdapter` - Direct Bedrock access (future)

### ConversationRepository

Persistence port for conversations.

```python
from dcaf.core.application.ports import ConversationRepository

class ConversationRepository(Protocol):
    def get(self, id: ConversationId) -> Optional[Conversation]: ...
    def save(self, conversation: Conversation) -> None: ...
    def delete(self, id: ConversationId) -> bool: ...
    def exists(self, id: ConversationId) -> bool: ...
    def get_or_create(self, id: ConversationId) -> Conversation: ...
```

**Implementations:**
- `InMemoryConversationRepository` - For testing and simple use cases

### ApprovalCallback

Port for requesting human approval.

```python
from dcaf.core.application.ports import ApprovalCallback, ApprovalDecision

class ApprovalCallback(Protocol):
    def request_approval(
        self, 
        tool_calls: List[ToolCall],
    ) -> List[ApprovalDecision]:
        """Request approval for tool calls."""
        ...
    
    def notify_execution_result(
        self,
        tool_call_id: str,
        result: str,
        success: bool,
    ) -> None:
        """Notify of execution results."""
        ...
```

### EventPublisher

Port for publishing domain events.

```python
from dcaf.core.application.ports import EventPublisher

class EventPublisher(Protocol):
    def publish(self, event: DomainEvent) -> None: ...
    def publish_all(self, events: List[DomainEvent]) -> None: ...
```

---

## Services

Use cases orchestrate the execution of business operations.

### AgentService

The main use case for agent execution.

```python
from dcaf.core.application.services import AgentService
from dcaf.core.application.dto import AgentRequest

# Setup
service = AgentService(
    runtime=agno_adapter,
    conversations=conversation_repo,
    events=event_publisher,
    approval_policy=ApprovalPolicy(),
)

# Execute synchronously
response = service.execute(AgentRequest(
    content="What pods are running?",
    tools=[kubectl_tool],
    conversation_id="conv-123",  # Optional, creates new if not provided
    context={"tenant_name": "my-tenant"},
))

# Handle response
if response.has_pending_approvals:
    # Tool calls need approval
    for tc in response.pending_tool_calls:
        print(f"Approve {tc.name}? {tc.input}")
else:
    # Response is complete
    print(response.text)
```

**Streaming:**

```python
# Execute with streaming
for event in service.execute_stream(request):
    if event.event_type == StreamEventType.TEXT_DELTA:
        print(event.data["text"], end="")
    elif event.event_type == StreamEventType.MESSAGE_END:
        final_response = event.data["response"]
```

**Resume After Approval:**

```python
# After user approves tool calls
response = service.resume(
    conversation_id="conv-123",
    tools=[kubectl_tool],
)
```

### ApprovalService

Handles approval decisions for pending tool calls.

```python
from dcaf.core.application.services import ApprovalService
from dcaf.core.application.dto import ApprovalRequest, ToolCallApproval

service = ApprovalService(
    conversations=conversation_repo,
    events=event_publisher,
)

# Approve specific tool calls
response = service.execute(ApprovalRequest(
    conversation_id="conv-123",
    approvals=[
        ToolCallApproval(tool_call_id="tc-1", approved=True),
        ToolCallApproval(tool_call_id="tc-2", approved=False, rejection_reason="Too risky"),
    ],
))

# Convenience methods
response = service.approve_single("conv-123", "tc-1")
response = service.reject_single("conv-123", "tc-2", "Not needed")
response = service.approve_all("conv-123")
response = service.reject_all("conv-123", "User cancelled")
```

---

## DTOs

Data Transfer Objects for communication between layers.

### AgentRequest

Request DTO for agent execution.

```python
from dcaf.core.application.dto import AgentRequest

request = AgentRequest(
    content="What pods are running?",
    conversation_id="conv-123",
    context={"tenant_name": "my-tenant", "k8s_namespace": "default"},
    tools=[kubectl_tool, aws_tool],
    system_prompt="You are a helpful DevOps assistant.",
    stream=False,
    # Tracing fields (optional)
    user_id="user-123",
    session_id="session-abc",
    run_id="run-xyz",
    request_id="req-456",
)

# Access helpers
conv_id = request.get_conversation_id()  # ConversationId value object
context = request.get_platform_context()  # PlatformContext with tracing merged in
```

**Tracing Fields:**

| Field | Description |
|-------|-------------|
| `user_id` | User identifier for tracking and analytics |
| `session_id` | Groups related runs into a session |
| `run_id` | Unique identifier for this execution |
| `request_id` | HTTP request correlation ID |

See [Tracing and Observability Guide](../guides/tracing-observability.md) for details.

### AgentResponse

Response DTO from agent execution.

```python
from dcaf.core.application.dto import AgentResponse

# Properties
response.conversation_id  # str
response.text             # Optional[str]
response.tool_calls       # List[ToolCallDTO]
response.has_pending_approvals  # bool
response.is_complete      # bool

# Helpers
response.pending_tool_calls   # Tool calls awaiting approval
response.approved_tool_calls  # Tool calls that were approved
response.executed_tool_calls  # Tool calls that completed

# Serialization
response.to_dict()
```

### ToolCallDTO

DTO representing a tool call.

```python
from dcaf.core.application.dto import ToolCallDTO

tc = ToolCallDTO(
    id="tc-123",
    name="kubectl",
    input={"command": "get pods"},
    description="Execute kubectl commands",
    intent="List running pods",
    requires_approval=True,
    status="pending",  # pending, approved, completed, rejected, failed
    result=None,
    error=None,
)

# From domain entity
tc = ToolCallDTO.from_tool_call(tool_call_entity)
```

### StreamEvent

Streaming event for real-time responses.

```python
from dcaf.core.application.dto import StreamEvent, StreamEventType

# Event types
StreamEventType.TEXT_DELTA       # Text chunk
StreamEventType.TOOL_USE_START   # Tool call starting
StreamEventType.TOOL_USE_DELTA   # Tool call input chunk
StreamEventType.TOOL_USE_END     # Tool call complete
StreamEventType.MESSAGE_START    # Message starting
StreamEventType.MESSAGE_END      # Message complete with response
StreamEventType.ERROR            # Error occurred

# Factory methods
event = StreamEvent.text_delta("Hello")
event = StreamEvent.tool_use_start("tc-123", "kubectl")
event = StreamEvent.error("Connection failed", code="TIMEOUT")
```

---

## Wiring It Together

Here's a complete example of setting up the application layer:

```python
from dcaf.core.adapters.outbound.agno import AgnoAdapter
from dcaf.core.adapters.outbound.persistence import InMemoryConversationRepository
from dcaf.core.application.services import AgentService, ApprovalService
from dcaf.core.domain.services import ApprovalPolicy
from dcaf.core.testing import FakeEventPublisher

# Create adapters
runtime = AgnoAdapter(
    model_id="anthropic.claude-3-sonnet-20240229-v1:0",
    provider="bedrock",
)
conversations = InMemoryConversationRepository()
events = FakeEventPublisher()  # Or a real implementation

# Create policy
policy = ApprovalPolicy()

# Create use cases
execute_agent = AgentService(
    runtime=runtime,
    conversations=conversations,
    events=events,
    approval_policy=policy,
)

approve_tool_call = ApprovalService(
    conversations=conversations,
    events=events,
)
```

---

## Best Practices

1. **Use DTOs at boundaries**: Don't pass domain entities directly to external layers
2. **Keep use cases thin**: They orchestrate, they don't contain business logic
3. **Inject dependencies**: Use constructor injection for all ports
4. **Handle events**: Publish domain events for audit trails and side effects
5. **Validate inputs**: DTOs should validate their inputs
