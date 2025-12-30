# Testing

The Core layer provides comprehensive testing support with fakes, builders, and fixtures that enable fast, isolated unit tests.

---

## Overview

The testing module includes:

- **Fakes**: Fake implementations of all ports
- **Builders**: Test data builders for creating domain objects
- **Fixtures**: pytest fixtures for common setup

---

## Fakes

Fakes are test implementations of ports that allow testing without real infrastructure.

### FakeAgentRuntime

Simulates the AgentRuntime port with configurable responses.

```python
from dcaf.core.testing import FakeAgentRuntime

fake = FakeAgentRuntime()

# Configure responses
fake.will_respond_with_text("Hello, world!")
fake.will_respond_with_tool_call(
    tool_name="kubectl",
    tool_input={"command": "get pods"},
    requires_approval=True,
)

# Use in tests
response = fake.invoke(messages, tools)

# Verify calls
assert fake.invoke_count == 1
assert fake.last_messages == messages
assert fake.last_tools == tools
```

**Methods:**
- `will_respond_with_text(text)` - Configure text response
- `will_respond_with_tool_call(...)` - Configure tool call response
- `will_respond_with(response)` - Configure custom response
- `will_stream_text(text)` - Configure streaming text
- `reset()` - Clear all configured responses and recorded calls

### FakeConversationRepository

In-memory repository with tracking.

```python
from dcaf.core.testing import FakeConversationRepository

fake = FakeConversationRepository()

# Seed with test data
conversation = ConversationBuilder.empty()
fake.seed(conversation)

# Use in tests
loaded = fake.get(conversation.id)
fake.save(conversation)

# Verify operations
assert fake.save_count == 1
assert fake.get_count == 1
assert fake.last_saved == conversation
```

### FakeApprovalCallback

Configurable approval behavior.

```python
from dcaf.core.testing import FakeApprovalCallback

fake = FakeApprovalCallback()

# Auto-approve all
fake.will_approve_all()
decisions = fake.request_approval(tool_calls)
assert all(d.is_approved for d in decisions)

# Auto-reject all
fake.will_reject_all("Test rejection")
decisions = fake.request_approval(tool_calls)
assert all(d.is_rejected for d in decisions)

# Custom decisions
from dcaf.core.application.ports.approval_callback import ApprovalDecision
fake.will_return_decisions([
    ApprovalDecision.approve("tc-1"),
    ApprovalDecision.reject("tc-2", "Too risky"),
])
```

### FakeEventPublisher

Captures published events for verification.

```python
from dcaf.core.testing import FakeEventPublisher
from dcaf.core.domain.events import ApprovalRequested

fake = FakeEventPublisher()

# Publish events
fake.publish(event)
fake.publish_all([event1, event2])

# Verify
assert fake.publish_count == 3
assert fake.has_event_of_type(ApprovalRequested)

# Get specific event types
approval_events = fake.get_events_of_type(ApprovalRequested)
```

---

## Builders

Builders create test data with sensible defaults and a fluent API.

### MessageBuilder

Build Message entities.

```python
from dcaf.core.testing import MessageBuilder

# Fluent API
message = (MessageBuilder()
    .as_user()
    .with_text("Hello, can you help me?")
    .build())

# Convenience methods
user_msg = MessageBuilder.user_message("Hello")
assistant_msg = MessageBuilder.assistant_message("Hi there!")
system_msg = MessageBuilder.system_message("You are helpful")
```

### ToolCallBuilder

Build ToolCall entities.

```python
from dcaf.core.testing import ToolCallBuilder

# Fluent API
tool_call = (ToolCallBuilder()
    .with_id("tc-123")
    .with_name("kubectl")
    .with_input({"command": "get pods"})
    .with_description("Execute kubectl commands")
    .requiring_approval()
    .build())

# Pre-configured states
approved = (ToolCallBuilder()
    .with_name("kubectl")
    .as_approved()
    .build())

completed = (ToolCallBuilder()
    .with_name("kubectl")
    .as_completed("Success!")
    .build())

# Convenience methods
kubectl_call = ToolCallBuilder.pending_kubectl_call()
```

### ConversationBuilder

Build Conversation aggregates.

```python
from dcaf.core.testing import ConversationBuilder

# Fluent API
conversation = (ConversationBuilder()
    .with_id("conv-123")
    .with_system_prompt("You are a helpful assistant")
    .with_user_message("Hello")
    .with_assistant_message("Hi there!")
    .with_tenant("my-tenant")
    .build())

# With pending approvals
blocked = (ConversationBuilder()
    .with_user_message("Delete the pod")
    .with_pending_tool_call(ToolCallBuilder.pending_kubectl_call())
    .build())

assert blocked.is_blocked

# Convenience methods
empty = ConversationBuilder.empty()
one_turn = ConversationBuilder.with_single_turn("Hello", "Hi!")
```

### ToolBuilder

Build mock Tool objects.

```python
from dcaf.core.testing import ToolBuilder

# Fluent API
tool = (ToolBuilder()
    .with_name("kubectl")
    .with_description("Execute kubectl commands")
    .with_input_schema({
        "type": "object",
        "properties": {"command": {"type": "string"}},
    })
    .requiring_approval()
    .requiring_platform_context()
    .build())

# Execute and track
result = tool.execute({"command": "get pods"}, platform_context)
assert tool.execute_count == 1

# Convenience methods
kubectl = ToolBuilder.kubectl_tool()
```

---

## Fixtures

pytest fixtures for common test setup.

### Basic Fixtures

```python
import pytest
from dcaf.core.testing.fixtures import *

def test_with_fake_runtime(fake_runtime):
    fake_runtime.will_respond_with_text("Hello!")
    response = fake_runtime.invoke([], [])
    assert response.text == "Hello!"

def test_with_fake_conversations(fake_conversations):
    conversation = ConversationBuilder.empty()
    fake_conversations.save(conversation)
    assert fake_conversations.exists(conversation.id)

def test_with_fake_events(fake_events):
    fake_events.publish(some_event)
    assert fake_events.publish_count == 1
```

### Service Fixtures

```python
def test_execute_agent(execute_agent_service, fake_runtime):
    fake_runtime.will_respond_with_text("Hello!")
    
    response = execute_agent_service.execute(AgentRequest(
        content="Hi",
        tools=[],
    ))
    
    assert response.text == "Hello!"

def test_approve_tool_call(
    approve_tool_call_service, 
    fake_conversations
):
    # Setup conversation with pending approval
    conversation = (ConversationBuilder()
        .with_pending_tool_call(ToolCallBuilder.pending_kubectl_call())
        .build())
    fake_conversations.seed(conversation)
    
    # Approve
    response = approve_tool_call_service.approve_all(
        str(conversation.id)
    )
    
    assert not response.has_pending_approvals
```

### Builder Fixtures

```python
def test_with_builders(
    message_builder,
    tool_call_builder,
    conversation_builder,
):
    msg = message_builder.as_user().with_text("Test").build()
    tc = tool_call_builder.with_name("test").build()
    conv = conversation_builder.with_message(msg).build()
```

### Sample Data Fixtures

```python
def test_with_sample_data(
    sample_conversation,
    sample_kubectl_tool,
    sample_user_message,
    sample_pending_tool_call,
):
    # Ready-to-use test data
    assert sample_conversation.message_count == 2
    assert sample_kubectl_tool.requires_approval
```

### Integration Test Fixtures

```python
def test_approval_flow(
    approval_required_runtime,
    auto_approve_callback,
):
    # Runtime configured to return tool calls needing approval
    response = approval_required_runtime.invoke([], [])
    assert response.has_pending_approvals
    
    # Callback configured to auto-approve
    decisions = auto_approve_callback.request_approval(
        response.pending_tool_calls
    )
    assert all(d.is_approved for d in decisions)
```

---

## Testing Patterns

### Testing Services

```python
def test_execute_agent_with_approval_required():
    # Arrange
    fake_runtime = FakeAgentRuntime()
    fake_runtime.will_respond_with_tool_call(
        tool_name="kubectl",
        tool_input={"command": "delete pod"},
        requires_approval=True,
    )
    fake_conversations = FakeConversationRepository()
    
    service = AgentService(
        runtime=fake_runtime,
        conversations=fake_conversations,
    )
    
    tool = ToolBuilder().with_name("kubectl").requiring_approval().build()
    
    # Act
    response = service.execute(AgentRequest(
        content="Delete the pod",
        tools=[tool],
    ))
    
    # Assert
    assert response.has_pending_approvals
    assert len(response.pending_tool_calls) == 1
    assert response.pending_tool_calls[0].name == "kubectl"
```

### Testing Domain Logic

```python
def test_conversation_blocks_on_pending_approval():
    # Arrange
    conversation = ConversationBuilder.empty()
    tool_call = ToolCallBuilder.pending_kubectl_call()
    
    # Act
    conversation.request_tool_approval([tool_call])
    
    # Assert
    assert conversation.is_blocked
    
    with pytest.raises(ConversationBlocked):
        conversation.add_user_message(
            MessageContent.from_text("Another message")
        )
```

### Testing State Transitions

```python
def test_tool_call_lifecycle():
    tool_call = ToolCallBuilder().requiring_approval().build()
    
    # Initial state
    assert tool_call.is_pending
    
    # Approve
    tool_call.approve()
    assert tool_call.is_approved
    
    # Execute
    tool_call.start_execution()
    tool_call.complete("Success!")
    assert tool_call.is_completed
    assert tool_call.result == "Success!"
```

---

## Best Practices

1. **Use fakes, not mocks**: Fakes provide real behavior, mocks just verify calls
2. **Use builders for test data**: Builders make tests readable and maintainable
3. **Test at the right level**: Unit test domain logic, integration test use cases
4. **Verify side effects**: Check that events were published, conversations were saved
5. **Test edge cases**: Invalid state transitions, empty inputs, error conditions
6. **Keep tests fast**: Fakes enable millisecond-fast tests
