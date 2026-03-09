# dcaf/core/ — Clean Architecture Core

All new development goes here. This is the recommended API surface.

## Layer Structure

```
core/
├── agent.py, server.py, config.py   # Public API (facade layer)
├── application/                      # Business logic
│   ├── services/                     # AgentService, ApprovalService
│   ├── dto/                          # AgentRequest, AgentResponse
│   └── ports/                        # Interface boundaries (abstract)
├── domain/                           # Pure domain logic (no framework deps)
│   ├── entities/                     # Conversation, Message, ToolCall
│   ├── value_objects/                # PlatformContext, SkillDefinition, IDs
│   ├── services/                     # ApprovalPolicy
│   └── events/                       # Domain events
├── adapters/                         # Infrastructure adapters
│   ├── inbound/                      # ServerAdapter (FastAPI → Agent)
│   └── outbound/                     # LLM adapters (Agno), persistence
├── infrastructure/                   # Config, logging
├── services/                         # SkillManager, SkillTranslator
└── testing/                          # Builders, fakes, fixtures
```

## Conventions

- **Type annotations required** — MyPy enforces `disallow_untyped_defs = true` for all `dcaf.core.*`
- **Domain layer is pure** — no imports from adapters, infrastructure, or external frameworks
- **Ports define boundaries** — application layer uses abstract ports; adapters implement them
- **Entities have behavior** — Conversation, ToolCall have state machines (e.g., PENDING → APPROVED → EXECUTED)
- **Value objects are immutable** — PlatformContext, IDs, SkillDefinition

## Key Classes

| Class | File | Purpose |
|-------|------|---------|
| `Agent` | `agent.py` | Main facade — `run()`, `run_stream()`, tool registration |
| `serve()` | `server.py` | One-liner FastAPI server creation |
| `AgentService` | `application/services/agent_service.py` | Core orchestration logic |
| `Conversation` | `domain/entities/conversation.py` | State machine for message flow |
| `ToolCall` | `domain/entities/tool_call.py` | Tool invocation lifecycle |
| `ApprovalPolicy` | `domain/services/approval_policy.py` | Approval business rules |

## Import Rules

- `dcaf.core` must **never** import from `dcaf.agents` (enforced by import-linter)
- Domain layer should not import from adapters or infrastructure
- Use ports (interfaces) for cross-layer communication

## Testing Utilities

`dcaf/core/testing/` provides test helpers:
- `builders.py` — Test object factories (ConversationBuilder, etc.)
- `fakes.py` — Fake implementations (FakeAgentRuntime, FakeRepository)
- `fixtures.py` — Shared pytest fixtures
