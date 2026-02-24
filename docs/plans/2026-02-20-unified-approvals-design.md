# Unified Approvals Design

## Problem

DCAF has two parallel approval paths that implement the same lifecycle with different data structures:

- `data.cmds[]` / `data.executed_cmds[]` — command-string based, used by legacy agents (K8sAgent, AwsAgent, CommandAgent)
- `data.tool_calls[]` / `data.executed_tool_calls[]` — tool-call based, used by modern agents (ToolCallingAgent variants)

Both follow the same pattern: LLM suggests an action, frontend shows approval UI, user approves or rejects, server executes and injects results into context. The only difference is the data shape. Adding a new approval experience (e.g., database query preview) would mean adding yet another pair of fields and duplicating the processing logic again.

## Design

Add a unified `data.approvals[]` field that supports both command and tool call approval through a `type` discriminator. The frontend uses `type` to decide which UI to render. The backend processing path is the same regardless of type.

### Data Models

```python
class Approval(BaseModel):
    id: str                                    # unique identifier
    type: str                                  # "command" | "tool_call" | future types
    name: str                                  # tool name, or "execute_terminal_cmd"
    input: Dict[str, Any]                      # tool args, or {"command": "...", "files": [...]}
    execute: bool = False                      # user approved
    rejection_reason: Optional[str] = None     # why user rejected
    description: str = ""                      # human-readable summary
    intent: Optional[str] = None               # LLM's stated reason

class ExecutedApproval(BaseModel):
    id: str
    type: str
    name: str
    input: Dict[str, Any]
    output: str
```

Added to `Data` alongside existing fields:

```python
class Data(BaseModel):
    # Legacy (kept for backward compat)
    cmds: List[Command] = Field(default_factory=list)
    executed_cmds: List[ExecutedCommand] = Field(default_factory=list)
    tool_calls: List[ToolCall] = Field(default_factory=list)
    executed_tool_calls: List[ExecutedToolCall] = Field(default_factory=list)

    # Unified
    approvals: List[Approval] = Field(default_factory=list)
    executed_approvals: List[ExecutedApproval] = Field(default_factory=list)
```

The `type` field is a plain string (not an enum) so new approval types don't require a schema change.

### Stream Events

```python
class ApprovalsEvent(StreamEvent):
    type: Literal["approvals"] = "approvals"
    approvals: list[Approval]

class ExecutedApprovalsEvent(StreamEvent):
    type: Literal["executed_approvals"] = "executed_approvals"
    executed_approvals: list[ExecutedApproval]
```

Legacy events (`CommandsEvent`, `ToolCallsEvent`, etc.) remain unchanged.

### ServerAdapter Processing

`ServerAdapter` gets a `_process_approvals()` method that reads `data.approvals[]` from the latest message, executes approved items via the existing `_execute_tool()` method, and returns `ExecutedApproval` results.

Both `invoke()` and `invoke_stream()` call it:
- `invoke()` attaches results to `agent_msg.data.executed_approvals`
- `invoke_stream()` yields `ExecutedApprovalsEvent` before resuming the LLM

Executed results and rejection reasons are injected into the LLM message context so the model can reason about what happened.

Each field (`approvals`, `tool_calls`, `cmds`) is processed independently. If an agent populates multiple fields, everything gets processed.

### Streaming Flow

```
Request with data.approvals[] (user decisions)
  -> ServerAdapter._process_approvals()
  -> yield ExecutedApprovalsEvent (results for frontend)
  -> inject results into core_messages (for LLM context)
  -> LLM streams response -> TextDeltaEvent
  -> if LLM requests tools with requires_approval=True -> yield ApprovalsEvent
  -> DoneEvent
```

## Migration

**Phase 1 (this PR):** Add models, events, and `_process_approvals()` to ServerAdapter. Legacy fields untouched.

**Phase 2 (agent teams at their pace):** Agents switch from `data.cmds[]` or `data.tool_calls[]` to `data.approvals[]`. Frontend adds support. Both old and new work simultaneously.

**Phase 3 (eventual):** Deprecate and remove legacy fields.

## What Stays the Same

- The `@tool(requires_approval=True)` decorator
- The `Tool.execute()` method
- The `_execute_tool()` lookup in ServerAdapter
- All existing agents (no changes required)
- The domain-level approval state machine (ToolCall entity, ApprovalService, domain events)
- The frontend's existing handling of `data.cmds` and `data.tool_calls`

## Phase 1 Status

Phase 1 complete. The following were added:
- `Approval` and `ExecutedApproval` models (both public and core schemas)
- `ApprovalsEvent` and `ExecutedApprovalsEvent` stream events (both public and core)
- `ServerAdapter._process_approvals()` wired into both `invoke()` and `invoke_stream()`
- Context injection for LLM to see approval results
- Full test coverage in `tests/core/test_unified_approvals.py` (24 tests)

Legacy `data.cmds` and `data.tool_calls` remain fully functional. Full test suite: 478 passed, 0 regressions.
