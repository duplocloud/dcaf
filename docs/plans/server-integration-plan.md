# DCAF Core Server Integration Plan

**Goal**: Enable new Core agents to be served via REST/streaming with zero friction.  
**Status**: Draft  
**Created**: 2024-12-22

---

## Executive Summary

Make it dead simple to spin up a DCAF Core agent as a server:

```python
from dcaf.core import Agent, serve

agent = Agent(
    tools=[...],
    system_prompt="You are a helpful assistant."
)

# One line to start the server
serve(agent, port=8000)
```

---

## Current State

### Existing Server (`dcaf/agent_server.py`)
- ✅ FastAPI with `/api/sendMessage` (sync) and `/api/sendMessageStream` (streaming)
- ✅ `AgentProtocol` interface for pluggable agents
- ✅ Rich schemas for tool calls, approvals, streaming events
- ✅ Slack/channel routing support
- ✅ Health check endpoint

### New Core (`dcaf/core/`)
- ✅ `Agent` class with `run(messages)` method
- ✅ `ChatMessage` for structured input
- ✅ `AgentResponse` with `needs_approval`, `pending_tools`
- ❌ Does NOT implement `AgentProtocol`
- ❌ No streaming support yet
- ❌ No server adapter

---

## Phases

### Phase 1: Protocol Adapter (Bridge)
**Goal**: Make Core agents work with the existing server immediately.

Create an adapter that wraps `dcaf.core.Agent` to implement `AgentProtocol`:

```python
# dcaf/core/adapters/inbound/server_adapter.py
from dcaf.core import Agent, AgentResponse
from dcaf.agent_server import AgentProtocol
from dcaf.schemas.messages import AgentMessage, ToolCall

class ServerAdapter(AgentProtocol):
    """Adapts a Core Agent to work with the existing FastAPI server."""
    
    def __init__(self, agent: Agent):
        self.agent = agent
    
    def invoke(self, messages: dict) -> AgentMessage:
        # Convert input format
        core_messages = self._convert_messages(messages)
        
        # Run the core agent
        response = self.agent.run(messages=core_messages)
        
        # Convert response to AgentMessage
        return self._to_agent_message(response)
    
    def _convert_messages(self, messages: dict) -> list[dict]:
        """Convert from server format to Core format."""
        return messages.get("messages", [])
    
    def _to_agent_message(self, response: AgentResponse) -> AgentMessage:
        """Convert AgentResponse to AgentMessage schema."""
        agent_msg = AgentMessage(content=response.text or "")
        
        # Add pending tool calls for approval
        if response.needs_approval:
            for pending in response.pending_tools:
                agent_msg.data.tool_calls.append(ToolCall(
                    id=pending.id,
                    name=pending.name,
                    input=pending.input,
                    tool_description=pending.description,
                    input_description={},
                ))
        
        return agent_msg
```

**Deliverables**:
- [x] `dcaf/core/adapters/inbound/server_adapter.py`
- [x] Update `dcaf/core/__init__.py` to export `ServerAdapter`
- [x] Example in `examples/core_server.py`

**Usage**:
```python
from dcaf.core import Agent
from dcaf.core.adapters.inbound import ServerAdapter
from dcaf.agent_server import create_chat_app

agent = Agent(tools=[...])
app = create_chat_app(ServerAdapter(agent))
```

---

### Phase 2: Convenience Function
**Goal**: One-liner server startup.

```python
# dcaf/core/server.py
def serve(
    agent: Agent,
    port: int = 8000,
    host: str = "0.0.0.0",
    reload: bool = False,
):
    """
    Start a REST server for the agent.
    
    Example:
        from dcaf.core import Agent, serve
        
        agent = Agent(tools=[...])
        serve(agent, port=8000)
    """
    from dcaf.agent_server import create_chat_app
    from .adapters.inbound import ServerAdapter
    import uvicorn
    
    adapter = ServerAdapter(agent)
    app = create_chat_app(adapter)
    
    uvicorn.run(app, host=host, port=int(port), reload=reload)
```

**Deliverables**:
- [x] `dcaf/core/server.py` with `serve()` and `create_app()` functions
- [x] Export from `dcaf/core/__init__.py`
- [ ] Update getting-started docs

**Usage**:
```python
from dcaf.core import Agent, serve

agent = Agent(tools=[my_tool])
serve(agent)  # That's it!
```

---

### Phase 3: Streaming Support
**Goal**: Real-time token streaming for better UX.

Add streaming to the Core agent:

```python
# In dcaf/core/agent.py
class Agent:
    def run_stream(
        self, 
        messages: list[ChatMessage | dict],
        context: dict | None = None,
    ) -> Iterator[StreamEvent]:
        """Stream agent response as events."""
        # Yield events as they happen
        yield TextDeltaEvent(text="Hello")
        yield TextDeltaEvent(text=" world")
        yield ToolCallsEvent(tool_calls=[...])  # If approval needed
        yield DoneEvent()
```

Update `ServerAdapter` to implement `invoke_stream()`:

```python
def invoke_stream(self, messages: dict) -> Iterator[StreamEvent]:
    core_messages = self._convert_messages(messages)
    for event in self.agent.run_stream(messages=core_messages):
        yield event
```

**Deliverables**:
- [x] `Agent.run_stream()` method
- [x] Agno adapter streaming support (already had it)
- [x] `ServerAdapter.invoke_stream()` implementation
- [x] Test with `/api/chat-stream` endpoint

---

### Phase 4: CLI Integration
**Status**: SKIPPED - `serve()` function is sufficient for current needs.

---

### Phase 5: Documentation & Examples
**Goal**: Make it obvious how to get started.

**Deliverables**:
- [x] `docs/core/server.md` - Server guide
- [x] `examples/core_server.py` - Server example
- [x] `examples/streaming_example.py` - Streaming example
- [x] Updated `docs/core/index.md` with streaming section
- [x] Updated `mkdocs.yml` navigation

---

## Design Decisions

### Q: Reuse existing server or build new?
**A: Reuse**. The existing `agent_server.py` is well-designed:
- Already handles streaming, health checks, channel routing
- Battle-tested with DuploCloud helpdesk
- Keeps compatibility with existing deployments

### Q: Where does the adapter live?
**A: `dcaf/core/adapters/inbound/`**. This follows Clean Architecture:
- Inbound adapters convert external formats to domain
- Keeps the Core agent pure and framework-agnostic

### Q: Should Core agents depend on the old schemas?
**A: No, use adapters**. The `ServerAdapter` does the translation:
- Core uses simple types (`AgentResponse`, `PendingToolCall`)
- Adapter converts to rich schemas (`AgentMessage`, `ToolCall`)
- This allows schemas to evolve independently

---

## Success Criteria

1. **Zero Config Start**: `serve(agent)` works out of the box
2. **Full Compatibility**: Works with existing helpdesk integrations
3. **Streaming Works**: Token-by-token streaming via NDJSON
4. **Approvals Work**: Tool approval flow functions end-to-end
5. **Documented**: Clear examples for common patterns

---

## Timeline Estimate

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| Phase 1: Protocol Adapter | 2-3 hours | None |
| Phase 2: Convenience Function | 1 hour | Phase 1 |
| Phase 3: Streaming Support | 4-6 hours | Phase 1, Agno work |
| Phase 4: CLI Integration | 2 hours | Phase 2 |
| Phase 5: Documentation | 2-3 hours | All phases |

**Total**: ~12-15 hours of development

---

## Open Questions

1. **MCP Support**: Should we also support FastMCP? (Model Context Protocol)
   - The old code mentions it but I don't see implementation
   - Could be a Phase 6 addition

2. **Authentication**: Does the server need auth middleware?
   - Currently relies on network-level security
   - May need API keys for public deployment

3. **Metrics/Observability**: Add Prometheus metrics endpoint?
   - Could track request latency, tool execution time, errors

---

## Next Actions

1. [ ] Review this plan with team
2. [ ] Start Phase 1: Create `ServerAdapter`
3. [ ] Test with existing helpdesk integration
4. [ ] Iterate based on feedback
