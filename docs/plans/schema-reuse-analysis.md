# Schema Reuse Analysis for Core Framework v2

**Date:** January 8, 2026  
**Status:** Draft  
**Author:** Engineering Team

## Executive Summary

This document analyzes the existing schema classes in `dcaf/schemas/messages.py` and identifies opportunities to reuse them in the new Core Framework (`dcaf/core/`). The goal is to reduce code duplication, establish a single source of truth for wire protocol types, and maintain consistency between the legacy and v2 implementations.

---

## Background

The DCAF framework currently has two parallel sets of data classes:

1. **Schema Classes** (`dcaf/schemas/messages.py`) - Pydantic BaseModels for the HelpDesk wire protocol
2. **Core DTOs** (`dcaf/core/application/dto/`) - Python dataclasses for the Clean Architecture implementation

Both define similar structures for commands, tool calls, platform context, and messages. This analysis identifies which schema classes can be directly reused, which need enhancement, and which should remain separate due to intentional design differences.

---

## Class-by-Class Comparison

### Schema Classes Inventory

| Schema Class | Location | Purpose |
|-------------|----------|---------|
| `FileObject` | `messages.py:7-9` | File path and content for command execution |
| `Command` | `messages.py:12-16` | Terminal command awaiting approval |
| `ExecutedCommand` | `messages.py:19-21` | Terminal command that was executed |
| `ToolCall` | `messages.py:24-32` | Tool call awaiting approval |
| `ExecutedToolCall` | `messages.py:35-39` | Tool call that was executed |
| `URLConfig` | `messages.py:42-44` | URL configuration |
| `PlatformContext` | `messages.py:47-73` | Runtime context (tenant, credentials, etc.) |
| `AmbientContext` | `messages.py:77-78` | User terminal commands (unused) |
| `Data` | `messages.py:81-86` | Container for all actionable data |
| `User` | `messages.py:89-91` | User identification |
| `Agent` | `messages.py:94-96` | Agent identification |
| `Message` | `messages.py:99-106` | Base message with role and content |
| `UserMessage` | `messages.py:109-112` | User message with platform context |
| `AgentMessage` | `messages.py:115-116` | Assistant message |
| `Messages` | `messages.py:119-120` | Container for message list |

### Core DTOs Inventory

| Core Class | Location | Purpose |
|-----------|----------|---------|
| `FileObject` | `responses.py:63-73` | File path and content (duplicate) |
| `CommandDTO` | `responses.py:76-116` | Terminal command awaiting approval |
| `ExecutedCommandDTO` | `responses.py:119-144` | Terminal command that was executed |
| `ToolCallDTO` | `responses.py:147-239` | Tool call with extended fields |
| `ExecutedToolCallDTO` | `responses.py:242-275` | Tool call that was executed |
| `DataDTO` | `responses.py:282-341` | Container with session support |
| `PlatformContext` | `value_objects/platform_context.py` | Immutable domain value object |
| `Message` | `entities/message.py` | Domain entity with rich content |

---

## Reuse Categories

### ✅ Category 1: Highly Reusable (Direct Replacement)

These schema classes are nearly identical to their core counterparts and can directly replace the core DTOs.

### ⚠️ Category 2: Partially Reusable (Needs Enhancement)

These schema classes have the right foundation but need additional fields or methods to fully support the core framework's requirements.

### ❌ Category 3: Not Recommended for Reuse (Intentional Design Difference)

These classes serve different architectural purposes and should remain separate, with converters between them.

---

## Category 1: Highly Reusable

### Checklist

- [ ] **FileObject** → Replace `dcaf/core/application/dto/responses.py:FileObject`
  - Schema: `file_path: str`, `file_content: str`
  - Core: Identical fields
  - Action: Import from `dcaf.schemas.messages` instead of defining locally
  - Effort: Low (simple import change)

- [ ] **ExecutedCommand** → Replace `ExecutedCommandDTO`
  - Schema: `command: str`, `output: str`
  - Core: Identical fields
  - Action: Replace `ExecutedCommandDTO` with `ExecutedCommand` alias or direct use
  - Effort: Low (rename references)

- [ ] **ExecutedToolCall** → Replace `ExecutedToolCallDTO`
  - Schema: `id: str`, `name: str`, `input: Dict[str, Any]`, `output: str`
  - Core: Identical fields
  - Action: Replace `ExecutedToolCallDTO` with `ExecutedToolCall`
  - Effort: Low (rename references)

- [ ] **Command** → Replace `CommandDTO`
  - Schema: `command: str`, `execute: bool`, `rejection_reason: Optional[str]`, `files: Optional[List[FileObject]]`
  - Core: Same fields
  - Action: Replace `CommandDTO` with `Command`
  - Note: Core's `to_dict()`/`from_dict()` methods can be added via extension or utility functions
  - Effort: Low-Medium (may need to add serialization helpers)

### Migration Steps for Category 1

1. **Update imports in `dcaf/core/application/dto/responses.py`:**
   ```python
   from dcaf.schemas.messages import (
       FileObject,
       Command,
       ExecutedCommand,
       ExecutedToolCall,
   )
   ```

2. **Create aliases for backward compatibility (optional):**
   ```python
   # Aliases for backward compatibility during migration
   CommandDTO = Command
   ExecutedCommandDTO = ExecutedCommand
   ExecutedToolCallDTO = ExecutedToolCall
   ```

3. **Update all internal references to use schema classes**

4. **Remove duplicate class definitions from `responses.py`**

5. **Update tests to use schema classes**

---

## Category 2: Partially Reusable

### Checklist

- [ ] **ToolCall** → Enhance to replace `ToolCallDTO`
  - Schema fields:
    - `id: str`
    - `name: str`
    - `input: Dict[str, Any]`
    - `execute: bool = False`
    - `tool_description: str`
    - `input_description: Dict[str, Any]`
    - `intent: Optional[str] = None`
    - `rejection_reason: Optional[str] = None`
  - Core adds:
    - `requires_approval: bool = True`
    - `status: str = "pending"` (pending, approved, executed, rejected, failed)
    - `result: Optional[str] = None`
    - `error: Optional[str] = None`
  - Action: Add missing fields to schema's `ToolCall`
  - Effort: Medium

- [ ] **Data** → Enhance to replace `DataDTO`
  - Schema fields:
    - `cmds: List[Command]`
    - `executed_cmds: List[ExecutedCommand]`
    - `tool_calls: List[ToolCall]`
    - `executed_tool_calls: List[ExecutedToolCall]`
    - `url_configs: List[URLConfig]`
  - Core adds:
    - `session: Dict[str, Any] = Field(default_factory=dict)`
  - Core also adds helper properties:
    - `has_pending_items: bool`
    - `is_empty: bool`
  - Action: Add `session` field and helper properties to schema's `Data`
  - Effort: Medium

- [ ] **User** → Consider for inclusion in core
  - Schema: `name: str`, `id: str`
  - Core: Not currently used
  - Action: Evaluate if needed in core, import if yes
  - Effort: Low (optional)

- [ ] **Agent** (schema class) → Consider for inclusion in core
  - Schema: `name: str`, `id: str`
  - Core: Not currently used as data class
  - Action: Evaluate if needed in core, import if yes
  - Effort: Low (optional)

### Enhancement Plan for Category 2

#### ToolCall Enhancement

```python
# Proposed changes to dcaf/schemas/messages.py

class ToolCall(BaseModel):
    """Tool call for approval workflow."""
    id: str
    name: str
    input: Dict[str, Any]
    execute: bool = False
    tool_description: str = ""
    input_description: Dict[str, Any] = Field(default_factory=dict)
    intent: Optional[str] = None
    rejection_reason: Optional[str] = None
    # NEW: Fields for full protocol support
    requires_approval: bool = True
    status: str = "pending"  # pending, approved, rejected, executed, failed
    result: Optional[str] = None
    error: Optional[str] = None
    
    @property
    def description(self) -> str:
        """Alias for backward compatibility."""
        return self.tool_description
```

#### Data Enhancement

```python
# Proposed changes to dcaf/schemas/messages.py

class Data(BaseModel):
    """Container for all actionable data in a message."""
    cmds: List[Command] = Field(default_factory=list)
    executed_cmds: List[ExecutedCommand] = Field(default_factory=list)
    tool_calls: List[ToolCall] = Field(default_factory=list)
    executed_tool_calls: List[ExecutedToolCall] = Field(default_factory=list)
    url_configs: List[URLConfig] = Field(default_factory=list)
    # NEW: Session state for persistence across turns
    session: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def has_pending_items(self) -> bool:
        """Check if there are items awaiting approval."""
        pending_cmds = any(not c.execute for c in self.cmds)
        pending_tools = any(not t.execute for t in self.tool_calls)
        return pending_cmds or pending_tools
    
    @property
    def is_empty(self) -> bool:
        """Check if data container is empty."""
        return (
            not self.cmds and
            not self.executed_cmds and
            not self.tool_calls and
            not self.executed_tool_calls
        )
```

---

## Category 3: Not Recommended for Reuse

### Checklist

- [ ] **PlatformContext** → Keep separate implementations
  - Reason: Intentional design difference
  - Schema: Pydantic BaseModel (mutable, for serialization)
  - Core: Frozen dataclass (immutable value object for DDD)
  - Action: Create `from_schema()` converter method in core
  - Effort: Low (add factory method)

- [ ] **Message / UserMessage / AgentMessage** → Keep separate implementations
  - Reason: Different architectural purpose
  - Schema: Wire format for HelpDesk protocol (flat structure)
  - Core: Domain entity with rich content model (MessageContent, ContentBlock)
  - Action: Create converter utilities between wire format and domain entities
  - Effort: Medium (converters already partially exist)

- [ ] **Messages** → Keep separate
  - Reason: Simple container, core uses different patterns
  - Schema: `messages: List[Union[UserMessage, AgentMessage]]`
  - Core: Conversation aggregate with message collection
  - Action: No action needed

- [ ] **AmbientContext** → Evaluate for deprecation
  - Current status: Marked as "unused" in schema
  - Action: Confirm if needed, remove if not
  - Effort: Low

- [ ] **URLConfig** → Evaluate for inclusion
  - Current status: In schema, not in core
  - Action: Determine if needed in core framework
  - Effort: Low (optional)

### Converter Implementation Plan

#### PlatformContext Converter

Add to `dcaf/core/domain/value_objects/platform_context.py`:

```python
@classmethod
def from_schema(cls, schema_ctx: "PlatformContext") -> "PlatformContext":
    """
    Convert schema PlatformContext to domain value object.
    
    This converts the mutable Pydantic model used in the API layer
    to an immutable value object for domain logic.
    """
    from dcaf.schemas.messages import PlatformContext as SchemaPlatformContext
    
    if not isinstance(schema_ctx, SchemaPlatformContext):
        raise TypeError(f"Expected SchemaPlatformContext, got {type(schema_ctx)}")
    
    return cls.from_dict(schema_ctx.model_dump())

def to_schema(self) -> "PlatformContext":
    """Convert domain value object to schema PlatformContext."""
    from dcaf.schemas.messages import PlatformContext as SchemaPlatformContext
    return SchemaPlatformContext(**self.to_dict())
```

#### Message Converters

Consider adding to `dcaf/core/adapters/` a message converter:

```python
# dcaf/core/adapters/message_converter.py

from dcaf.schemas.messages import UserMessage, AgentMessage, Message as SchemaMessage
from dcaf.core.domain.entities import Message as DomainMessage

def schema_to_domain(msg: SchemaMessage) -> DomainMessage:
    """Convert schema message to domain entity."""
    if msg.role == "user":
        return DomainMessage.user(msg.content)
    elif msg.role == "assistant":
        return DomainMessage.assistant(msg.content)
    else:
        raise ValueError(f"Unknown role: {msg.role}")

def domain_to_schema(msg: DomainMessage, include_data: bool = False) -> SchemaMessage:
    """Convert domain entity to schema message."""
    if msg.is_user_message:
        return UserMessage(content=msg.text or "")
    else:
        return AgentMessage(content=msg.text or "")
```

---

## Implementation Priority

### Phase 1: Quick Wins (Week 1)
1. [ ] Import `FileObject` from schemas
2. [ ] Import `ExecutedCommand` from schemas  
3. [ ] Import `ExecutedToolCall` from schemas
4. [ ] Create backward-compatible aliases
5. [ ] Update tests

### Phase 2: Schema Enhancement (Week 2)
1. [ ] Add missing fields to `ToolCall` in schemas
2. [ ] Add `session` field to `Data` in schemas
3. [ ] Add helper properties to `Data`
4. [ ] Replace `ToolCallDTO` with enhanced `ToolCall`
5. [ ] Replace `DataDTO` with enhanced `Data`
6. [ ] Update tests

### Phase 3: Converters (Week 3)
1. [ ] Add `from_schema()` to core `PlatformContext`
2. [ ] Add `to_schema()` to core `PlatformContext`
3. [ ] Create message converter utilities
4. [ ] Document the schema/core boundary
5. [ ] Update engineering handoff doc

### Phase 4: Cleanup (Week 4)
1. [ ] Remove duplicate class definitions
2. [ ] Deprecate old DTO classes
3. [ ] Update all imports across codebase
4. [ ] Final testing and validation
5. [ ] Update documentation

---

## Breaking Changes

### API Compatibility

The following changes may affect external consumers:

| Change | Impact | Mitigation |
|--------|--------|------------|
| `CommandDTO` → `Command` | Low | Provide alias |
| `ExecutedCommandDTO` → `ExecutedCommand` | Low | Provide alias |
| `ExecutedToolCallDTO` → `ExecutedToolCall` | Low | Provide alias |
| `ToolCallDTO` → `ToolCall` | Medium | Fields are additive |
| `DataDTO` → `Data` | Medium | Fields are additive |

### Internal Compatibility

- Core framework consumers using `from dcaf.core import *` should be unaffected
- Direct imports of DTO classes will need updates
- Type hints referencing DTO classes will need updates

---

## Testing Strategy

1. **Unit Tests**: Verify schema classes pass existing DTO tests
2. **Integration Tests**: Verify serialization/deserialization round-trips
3. **Protocol Tests**: Verify HelpDesk protocol compatibility
4. **Regression Tests**: Run full test suite after each phase

---

## Open Questions

1. Should we keep `URLConfig` in core? (Currently schema-only)
2. Should we deprecate `AmbientContext`? (Marked unused)
3. Should `User` and `Agent` schema classes be used in core?
4. Do we need versioning for schema changes?

---

## Appendix: File Locations

### Schema Files
- `dcaf/schemas/__init__.py`
- `dcaf/schemas/messages.py`
- `dcaf/schemas/events.py`

### Core DTO Files
- `dcaf/core/application/dto/__init__.py`
- `dcaf/core/application/dto/requests.py`
- `dcaf/core/application/dto/responses.py`

### Core Domain Files
- `dcaf/core/domain/entities/message.py`
- `dcaf/core/domain/entities/tool_call.py`
- `dcaf/core/domain/value_objects/platform_context.py`

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-08 | Engineering | Initial analysis |
