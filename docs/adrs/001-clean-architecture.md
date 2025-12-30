# ADR-001: Clean Architecture

## Status

Accepted

## Context

The DCAF agent framework needs to support multiple LLM provider frameworks (Agno, LangChain, Strands, etc.) while maintaining a stable core domain. The current implementation has tight coupling between agents and the Bedrock LLM provider, making it difficult to:

1. Switch between LLM frameworks without modifying business logic
2. Test business logic in isolation from infrastructure
3. Maintain consistent behavior across different adapters

We need an architecture that allows the core business logic to remain stable while external integrations can vary.

## Decision

We adopt Clean Architecture with the following layered structure:

```
┌─────────────────────────────────────────────────────────────┐
│                    External Frameworks                       │
│              (FastAPI, Agno SDK, LangChain, DB)             │
├─────────────────────────────────────────────────────────────┤
│                         Adapters                             │
│         (Controllers, Repositories, Framework Adapters)     │
├─────────────────────────────────────────────────────────────┤
│                       Application                            │
│                  (Use Cases, Ports/Interfaces)               │
├─────────────────────────────────────────────────────────────┤
│                         Domain                               │
│        (Entities, Value Objects, Domain Services)           │
└─────────────────────────────────────────────────────────────┘
```

**The Dependency Rule**: All dependencies point inward. Outer layers depend on inner layers, never the reverse.

- **Domain Layer**: Pure business logic with no external dependencies. Contains entities, value objects, domain services, and domain events.
- **Application Layer**: Use cases that orchestrate domain logic. Defines ports (interfaces) for external systems.
- **Adapter Layer**: Implementations of ports. Translates between our domain and external frameworks.
- **Infrastructure Layer**: Cross-cutting concerns like configuration and logging.

## Consequences

### Positive Consequences

- Domain logic is testable without any infrastructure
- Framework changes don't affect business rules
- Clear boundaries make the codebase navigable
- New adapters can be added without touching existing code
- The approval flow (human-in-the-loop) remains consistent across all frameworks

### Negative Consequences

- More files and directories to navigate initially
- Requires discipline to maintain layer boundaries
- Some ceremony in creating DTOs and converters
- Steeper learning curve for new team members

## Related ADRs

- ADR-002: DDD Tactical Patterns
- ADR-003: Adapter Pattern for Frameworks

