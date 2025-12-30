# ADR-002: DDD Tactical Patterns

## Status

Accepted

## Context

The DCAF framework manages conversations, tool executions, and approval workflows. These concepts have:

- **Identity**: A tool call has a unique ID that persists across approval cycles
- **Lifecycle**: Tool calls transition through states (pending → approved → executed)
- **Invariants**: A conversation cannot proceed while approvals are pending
- **Business rules**: Approval policies determine what requires human review

We need patterns to model these concepts correctly and protect business invariants.

## Decision

We adopt Domain-Driven Design tactical patterns:

### Entities

Objects with identity and lifecycle. Equality based on identity, not attributes.

```python
class ToolCall:
    """Entity with identity and state transitions."""
    id: ToolCallId  # Identity
    status: ToolCallStatus  # Mutable state
    
    def approve(self) -> None: ...
    def reject(self, reason: str) -> None: ...
    def complete(self, result: str) -> None: ...
```

### Value Objects

Immutable objects without identity. Equality based on attributes.

```python
@dataclass(frozen=True)
class ToolCallId:
    value: str
    
@dataclass(frozen=True)
class ToolInput:
    parameters: Mapping[str, Any]
```

### Aggregates

Clusters of entities with a root that protects invariants.

```python
class Conversation:  # Aggregate Root
    """Protects invariant: can't add messages while approvals pending."""
    
    def add_user_message(self, content: MessageContent) -> None:
        if self._pending_approvals:
            raise ConversationBlocked("Resolve pending approvals first")
        ...
```

### Domain Services

Stateless operations that don't belong to a single entity.

```python
class ApprovalPolicy:
    """Determines what requires human approval."""
    
    def requires_approval(self, tool: Tool, context: PlatformContext) -> bool: ...
```

### Domain Events

Record of something significant that happened in the domain.

```python
@dataclass(frozen=True)
class ApprovalRequested:
    conversation_id: ConversationId
    tool_calls: List[ToolCall]
    timestamp: datetime
```

## Consequences

### Positive Consequences

- Business rules are explicit and testable
- State transitions are controlled and validated
- Invariants are protected at the aggregate boundary
- Events enable loose coupling and audit trails
- Code reads like the ubiquitous language

### Negative Consequences

- More classes than a simple data-centric approach
- Requires understanding of DDD concepts
- Aggregate boundaries need careful design
- May feel like overkill for simple CRUD operations

## Related ADRs

- ADR-001: Clean Architecture
- ADR-004: Approval-First Design

