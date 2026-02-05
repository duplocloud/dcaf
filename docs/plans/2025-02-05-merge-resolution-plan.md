# Merge Resolution Plan: vnext ← main

**Date**: 2025-02-05
**Direction**: Merging `vnext` into `main` (release direction)
**Conflicts**: 3 files

---

## Executive Summary

The main branch has added **new features** while vnext has **refactored the architecture** for better async support and backwards compatibility. The resolution strategy is:

1. **Keep vnext's architecture** (async handlers, modern type hints, new endpoints)
2. **Add main's new features** (A2A agent card, cache metrics, new schema fields)
3. **Preserve all backwards compatibility** work done in vnext

---

## Conflict 1: `dcaf/agent_server.py`

### What Main Added
- `a2a_agent_card_path` parameter to `create_chat_app()`
- `/.well-known/agent.json` endpoint for Agent2Agent protocol support

### What vnext Changed
- Refactored sync handlers to async with `asyncio.to_thread()` for non-blocking health checks
- Added `/api/chat` and `/api/chat-stream` as preferred endpoints
- Added `/api/sendMessage` and `/api/sendMessageStream` as deprecated aliases (ADR-007)
- Added `/api/chat-ws` WebSocket endpoint
- Added `_has_invoke_stream()` fallback for v1 agents without streaming
- Added `_request_fields` forwarding for thread_id, tenant_id, etc.

### Resolution Strategy

**Keep vnext's architecture and ADD main's A2A feature.**

**Rationale**:
1. vnext's async architecture is essential for non-blocking health checks in production
2. vnext's legacy endpoint aliases are required for backwards compatibility (ADR-007)
3. vnext's WebSocket support is a new feature we want to keep
4. Main's A2A agent card feature is additive and non-breaking

**Specific Changes**:
```python
# Update function signature to include a2a_agent_card_path
def create_chat_app(
    agent: AgentProtocol,
    router: ChannelResponseRouter | None = None,
    a2a_agent_card_path: str | None = None,  # ADD from main
) -> FastAPI:
```

```python
# Add A2A endpoint after health check (from main)
if a2a_agent_card_path:
    card_path = Path(a2a_agent_card_path)

    @app.get("/.well-known/agent.json", tags=["system"])
    def get_agent_card() -> dict[str, Any]:
        """Serves the Agent2Agent agent card JSON."""
        # ... (copy from main, update type hints to modern style)
```

**Why This Choice**:
- Preserves vnext's async architecture (critical for production)
- Preserves all backwards compatibility work
- Adds A2A support without breaking anything
- A2A is an additive feature that doesn't conflict with our architecture

---

## Conflict 2: `dcaf/llm/bedrock.py`

### What Main Added
- `CACHE_MIN_TOKENS` class constant for model-specific caching thresholds
- `_get_cache_min_tokens()` method
- `_log_cache_metrics()` method for logging cache hits/misses
- `cache_system_prompt` parameter to `invoke_stream()` and `invoke()`
- `top_p` made optional with `None` default

### What vnext Changed
- Modernized type hints (`Dict` → `dict`, `List` → `list`, `Optional` → `| None`)
- Minor formatting/style improvements
- `**kwargs` → `**_kwargs: Any` for explicit unused parameter handling

### Resolution Strategy

**Keep vnext's modern type hints and ADD main's caching features.**

**Rationale**:
1. vnext's modern type hints are preferred (Python 3.10+ style)
2. Main's caching features are valuable for production performance
3. The features are orthogonal - no architectural conflict

**Specific Changes**:
```python
class BedrockLLM(LLM):
    # ADD from main (with modern type hints)
    CACHE_MIN_TOKENS: dict[str, int] = {
        "claude-haiku-4-5": 4096,
        "claude-sonnet-4-5": 1024,
        # ... etc
    }

    def _get_cache_min_tokens(self, model_id: str) -> int:
        # ADD from main
        ...

    def _log_cache_metrics(self, response: dict[str, Any], model_id: str) -> None:
        # ADD from main
        ...
```

```python
# Update invoke_stream signature to include cache_system_prompt
def invoke_stream(
    self,
    messages: list[dict[str, Any]],
    model_id: str,
    system_prompt: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 1000,
    temperature: float = 0.0,
    additional_params: dict[str, Any] | None = None,
    cache_system_prompt: bool = False,  # ADD from main
):
```

**Why This Choice**:
- Caching is a production performance feature - valuable to keep
- Type hints are cosmetic but preferred modern style
- No behavioral conflict between the changes

---

## Conflict 3: `dcaf/schemas/messages.py`

### What Main Added
- `FileObject.refers_persistent_file: Optional[str] = None` - reference to persistent file storage
- `Data.user_file_uploads: List[FileObject] = Field(default_factory=list)` - user uploaded files

### What vnext Changed
- `PlatformContext.tenant_id: str | None = None` - tenant identification
- `PlatformContext.user_roles: list[str] = Field(default_factory=list)` - access control
- `PlatformContext.aws_region: str | None = None` - AWS region for credentials
- `PlatformContext.model_config = ConfigDict(extra="allow")` - allow additional fields
- `Data.session: dict[str, Any]` - session state persistence
- `AgentMessage.from_agent_response()` class method - conversion helper
- Modernized type hints throughout

### Resolution Strategy

**COMBINE both sets of changes - they are complementary.**

**Rationale**:
1. Main's `user_file_uploads` and `refers_persistent_file` are new features for file handling
2. vnext's `PlatformContext` enhancements are for multi-tenant access control
3. vnext's `Data.session` is for state persistence
4. All changes are additive - no conflicts in meaning or behavior

**Specific Changes**:
```python
class FileObject(BaseModel):
    file_path: str
    file_content: str
    refers_persistent_file: str | None = None  # ADD from main


class PlatformContext(BaseModel):
    # Keep ALL vnext fields
    tenant_id: str | None = None
    tenant_name: str | None = None
    user_roles: list[str] = Field(default_factory=list)
    k8s_namespace: str | None = None
    kubeconfig: str | None = None
    duplo_base_url: str | None = None
    duplo_token: str | None = None
    aws_credentials: dict[str, Any] | None = None
    aws_region: str | None = None

    model_config = ConfigDict(extra="allow")


class Data(BaseModel):
    cmds: list[Command] = Field(default_factory=list)
    executed_cmds: list[ExecutedCommand] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    executed_tool_calls: list[ExecutedToolCall] = Field(default_factory=list)
    url_configs: list[URLConfig] = Field(default_factory=list)
    user_file_uploads: list[FileObject] = Field(default_factory=list)  # ADD from main
    session: dict[str, Any] = Field(default_factory=dict)  # Keep from vnext
```

**Why This Choice**:
- Both branches added useful features to different parts of the schema
- No semantic conflict - file uploads and platform context are independent concerns
- All fields have defaults, so existing code won't break

---

## Test Plan

After resolving conflicts:

1. **Run v1 compatibility tests**: `pytest tests/test_v1_compatibility.py -v`
2. **Run full test suite**: `pytest --tb=short`
3. **Verify new features work**:
   - A2A agent card endpoint responds correctly
   - Cache metrics logging works
   - File upload fields serialize/deserialize correctly
4. **Verify legacy endpoints still work**:
   - `/api/sendMessage` returns 200
   - `/api/sendMessageStream` streams correctly

---

## Summary Table

| File | Main's Addition | vnext's Change | Resolution |
|------|-----------------|----------------|------------|
| `agent_server.py` | A2A agent card endpoint | Async architecture, legacy aliases, WebSocket | Keep vnext architecture, ADD A2A |
| `bedrock.py` | System prompt caching | Modern type hints | Keep vnext types, ADD caching |
| `messages.py` | File upload fields | Platform context fields, session | COMBINE both |

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| A2A endpoint breaks existing routes | Low | A2A uses `/.well-known/` path (standard, non-conflicting) |
| Caching changes performance characteristics | Low | Caching is opt-in (`cache_system_prompt=False` default) |
| New schema fields break serialization | Low | All new fields have defaults |

---

## Approval

- [ ] Plan reviewed and approved
- [ ] Ready to proceed with merge resolution
