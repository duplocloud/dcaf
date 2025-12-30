# ADR-003: Adapter Pattern for Frameworks

## Status

Accepted

## Context

DCAF needs to support multiple LLM agent frameworks:

- **Agno**: Primary framework for agent orchestration
- **LangChain**: Popular alternative with extensive ecosystem
- **Strands**: AWS-native agent framework
- **Direct Bedrock**: Existing implementation for backwards compatibility

Each framework has its own:
- Message format (different structures for user/assistant/tool messages)
- Tool definition format (different JSON schema conventions)
- Streaming protocol (different event types)
- Error handling patterns

Without proper isolation, framework-specific code would leak into business logic, causing:
- Tight coupling to specific frameworks
- Difficulty testing without framework dependencies
- Code duplication across agents
- Inconsistent behavior

## Decision

We use the Adapter Pattern with cohesive modules per framework:

```
dcaf/core/adapters/outbound/
├── agno/                          # ALL Agno-specific code
│   ├── __init__.py
│   ├── adapter.py                 # Implements AgentRuntime
│   ├── tool_converter.py          # dcaf Tool → Agno format
│   ├── message_converter.py       # dcaf Message ↔ Agno format
│   └── types.py                   # Agno-specific type definitions
├── langchain/                     # ALL LangChain-specific code
│   └── ...
└── strands/                       # ALL Strands-specific code
    └── ...
```

Each adapter folder contains:

1. **Adapter** (`adapter.py`): Implements the `AgentRuntime` port
2. **Tool Converter** (`tool_converter.py`): Converts dcaf `Tool` objects to framework format
3. **Message Converter** (`message_converter.py`): Converts messages bidirectionally

The domain and application layers never import from these adapter packages.

### AgentRuntime Port

```python
class AgentRuntime(Protocol):
    """Port that adapters implement."""
    
    def invoke(
        self, 
        messages: List[Message],
        tools: List[Tool],
    ) -> AgentResponse: ...
    
    def invoke_stream(
        self, 
        messages: List[Message],
        tools: List[Tool],
    ) -> Iterator[StreamEvent]: ...
```

### Adapter Implementation

```python
class AgnoAdapter(AgentRuntime):
    def invoke(self, messages: List[Message], tools: List[Tool]) -> AgentResponse:
        # 1. Convert to Agno format
        agno_messages = self._message_converter.to_agno(messages)
        agno_tools = [self._tool_converter.to_agno(t) for t in tools]
        
        # 2. Call Agno SDK
        response = self._agent.run(messages=agno_messages, tools=agno_tools)
        
        # 3. Convert back to our domain
        return self._message_converter.from_agno(response)
```

## Consequences

### Positive Consequences

- Framework-specific code is isolated and replaceable
- Adding a new framework means adding a new folder, not modifying existing code
- Testing can use fake adapters instead of real frameworks
- Consistent behavior regardless of underlying framework
- Human-in-the-loop approval flow works identically across frameworks

### Negative Consequences

- Conversion overhead at adapter boundaries
- Need to maintain converters as frameworks evolve
- Some framework features may not map cleanly to our abstractions
- Initial setup requires understanding each framework's model

## Related ADRs

- ADR-001: Clean Architecture
- ADR-005: Cohesive Provider Modules

