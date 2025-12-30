# ADR-005: Cohesive Provider Modules

## Status

Accepted

## Context

When integrating with external frameworks (Agno, LangChain, etc.), there are multiple types of code:

- Adapter classes implementing our ports
- Converters for tools, messages, events
- Type definitions and constants
- Framework-specific utilities

These pieces are highly cohesive—they all deal with the same framework and change together. Spreading them across the codebase by type (all converters in one place, all adapters in another) would:

- Make it harder to understand a single integration
- Increase coupling between unrelated framework integrations
- Make it harder to add or remove framework support
- Complicate testing of a single integration

## Decision

We organize code by **provider/framework** rather than by **technical concern**:

### Recommended Structure (by provider)

```
dcaf/core/adapters/outbound/
├── agno/
│   ├── __init__.py
│   ├── adapter.py           # AgnoAdapter
│   ├── tool_converter.py    # AgnoToolConverter
│   ├── message_converter.py # AgnoMessageConverter
│   └── types.py             # Agno-specific types
├── langchain/
│   ├── __init__.py
│   ├── adapter.py
│   ├── tool_converter.py
│   └── message_converter.py
└── bedrock/
    ├── __init__.py
    ├── adapter.py           # Wraps existing BedrockLLM
    └── message_converter.py
```

### NOT Recommended (by concern)

```
dcaf/core/adapters/
├── adapters/
│   ├── agno_adapter.py
│   ├── langchain_adapter.py
│   └── bedrock_adapter.py
├── converters/
│   ├── agno_tool_converter.py
│   ├── agno_message_converter.py
│   ├── langchain_tool_converter.py
│   └── ...
```

### Benefits of Cohesive Modules

1. **Single Point of Change**: Adding Strands support means creating one new folder
2. **Easy Removal**: Removing LangChain support means deleting one folder
3. **Clear Dependencies**: All Agno code imports from `agno/`, nothing else does
4. **Focused Testing**: Test the entire Agno integration in one test module
5. **Framework Isolation**: Agno and LangChain never share implementation code

### Module Interface

Each provider module exports a consistent interface:

```python
# dcaf/core/adapters/outbound/agno/__init__.py
from .adapter import AgnoAdapter
from .tool_converter import AgnoToolConverter
from .message_converter import AgnoMessageConverter

__all__ = ["AgnoAdapter", "AgnoToolConverter", "AgnoMessageConverter"]
```

## Consequences

### Positive Consequences

- High cohesion within provider modules
- Low coupling between provider modules
- Easy to understand what code relates to which framework
- Simple to add/remove framework support
- Natural testing boundaries

### Negative Consequences

- Some code patterns may be duplicated across providers
- Need to maintain similar structures in each provider folder
- Cannot easily share utilities between providers (by design)

## Related ADRs

- ADR-003: Adapter Pattern for Frameworks
- ADR-001: Clean Architecture

