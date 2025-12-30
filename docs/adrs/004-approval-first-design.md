# ADR-004: Approval-First Design

## Status

Accepted

## Context

DCAF manages infrastructure operations (Kubernetes, AWS, etc.) that can have significant consequences:

- Deleting pods or namespaces
- Modifying AWS resources
- Executing shell commands
- Changing configurations

Autonomous agents executing such operations without human oversight poses risks:

- Unintended destructive actions
- Compliance violations
- Security incidents
- Difficult-to-reverse mistakes

The existing implementation has a human-in-the-loop pattern using `requires_approval` on tools and an `execute` flag on tool calls, but this is implemented inconsistently across agents.

## Decision

We make human-in-the-loop approval a **first-class protocol concern**, not an afterthought.

### Approval Flow

```
User Request
     │
     ▼
┌─────────────────────┐
│   Agent Processes   │
│   Determines Tools  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐     requires_approval=False
│  Check Approval     │──────────────────────────────► Execute Immediately
│  Policy             │
└─────────┬───────────┘
          │ requires_approval=True
          ▼
┌─────────────────────┐
│  Return ToolCall    │
│  (status=PENDING)   │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Human Reviews      │
│  Approves/Rejects   │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Continue with      │
│  Approved Actions   │
└─────────────────────┘
```

### Key Design Decisions

1. **ToolCall as Entity**: Tool calls have identity and lifecycle (pending → approved → executed → completed)

2. **Approval Policy as Domain Service**: Business rules for what needs approval are explicit and testable

3. **Conversation Blocking**: The conversation aggregate enforces that you cannot proceed while approvals are pending

4. **ApprovalCallback as Port**: The mechanism for requesting approval is abstracted, allowing different UIs (CLI, web, Slack)

### Tool Configuration

```python
class Tool:
    requires_approval: bool = False  # Default: no approval needed
    is_read_only: bool = True        # Hint for approval policy
```

### Approval Policy

```python
class ApprovalPolicy:
    def requires_approval(self, tool: Tool, context: PlatformContext) -> bool:
        # Business rule: read-only operations don't need approval
        if tool.is_read_only:
            return False
        # Respect tool-level configuration
        return tool.requires_approval
```

## Consequences

### Positive Consequences

- Human oversight is guaranteed for dangerous operations
- Approval flow works consistently across all frameworks
- Easy to audit what was approved and by whom
- Policy changes don't require code changes in agents
- Supports different approval mechanisms (sync/async)

### Negative Consequences

- Additional latency for operations requiring approval
- More complex conversation state management
- Users may find approval prompts disruptive for routine operations
- Need to design timeout/expiry for pending approvals

## Related ADRs

- ADR-002: DDD Tactical Patterns
- ADR-003: Adapter Pattern for Frameworks

