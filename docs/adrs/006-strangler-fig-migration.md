# ADR-006: Strangler Fig Migration

## Status

Accepted

## Context

DCAF has an existing codebase with:

- Working agents (`cmd_agent.py`, `aws_agent.py`, `k8s_agent.py`)
- Established `AgentProtocol` interface
- Production usage via `agent_server.py`
- Existing schemas and tools

We want to introduce a new Core abstraction layer without:

- Breaking existing functionality
- Requiring a big-bang migration
- Disrupting current users
- Losing the ability to rollback

## Decision

We apply the **Strangler Fig Pattern**:

1. Build the new Core system alongside the existing system
2. Route new functionality through Core
3. Gradually migrate existing agents
4. Eventually remove the old system

### Implementation Strategy

```
dcaf/
├── agents/              # EXISTING - Keep working
│   ├── cmd_agent.py
│   ├── aws_agent.py
│   └── k8s_agent.py
├── agent_server.py      # EXISTING - Still works with AgentProtocol
├── schemas/             # EXISTING - Reused by Core
├── tools.py             # EXISTING - Reused by Core
│
└── core/                # NEW - Built in parallel
    ├── domain/
    ├── application/
    └── adapters/
```

### Migration Phases

**Phase 1: Parallel Construction**
- Build Core in `dcaf/core/` without touching existing code
- Existing agents continue to work unchanged
- Core can import from existing `schemas/` and `tools.py`

**Phase 2: Facade Adapter**
- Create a `BedrockDirectAdapter` that wraps existing `BedrockLLM`
- Allows Core use cases to work with existing infrastructure
- Proves Core architecture without new framework dependencies

**Phase 3: New Agents on Core**
- New agents (e.g., using Agno) are built on Core
- Old and new agents coexist in `agent_server.py`
- Both implement `AgentProtocol` for compatibility

**Phase 4: Gradual Migration**
- Migrate existing agents one at a time
- Each migration is a separate, reversible change
- Old implementations kept until migration is verified

**Phase 5: Cleanup**
- Remove old agent implementations
- Core becomes the primary implementation
- Old `AgentProtocol` may remain for backwards compatibility

### Compatibility Bridge

```python
# dcaf/core/adapters/inbound/agent_protocol_bridge.py
class CoreAgentBridge:
    """Wraps a Core use case to implement legacy AgentProtocol."""
    
    def __init__(self, execute_agent_service: AgentService):
        self._service = execute_agent_service
    
    def invoke(self, messages: Dict) -> AgentMessage:
        # Convert legacy format to Core request
        request = self._convert_to_request(messages)
        response = self._service.execute(request)
        return self._convert_to_agent_message(response)
```

## Consequences

### Positive Consequences

- Zero downtime during migration
- Easy rollback if issues discovered
- Can migrate incrementally by agent
- New features can use Core immediately
- Team can learn Core patterns on new work

### Negative Consequences

- Temporary code duplication
- Two mental models during transition
- Need to maintain compatibility layer
- Longer overall timeline than big-bang

## Related ADRs

- ADR-001: Clean Architecture
- ADR-003: Adapter Pattern for Frameworks

