# MCP Tool Approval Design

## Overview

**Feature**: Add tool blacklist and auto-approve support for MCP tools with Human-in-the-Loop (HITL) approval flow
**Priority**: Core functionality
**Status**: Design phase

---

## Background

### The Problem

MCP (Model Context Protocol) tools connect DCAF agents to external services. Some tools are safe to auto-execute (read operations), while others require user approval before execution (delete, update, terminate operations).

Currently, DCAF's MCPTool supports:
- `include_tools` - Whitelist of tool names to include
- `exclude_tools` - Blacklist of tool names to exclude

But there's no mechanism to:
1. Use **glob patterns** for filtering (e.g., `"*_delete*"`)
2. Mark certain tools as **auto-approved** vs **requiring approval**
3. **Pause execution** when a tool needs approval and **resume** after approval

### Example Configuration

From the target configuration format:

```yaml
mcp-duplo:
  url: https://mcp-duplo-ai-internal.test10-apps.duplocloud.net
  path: /mcp
  transport_type: http
  tool_blacklist:
    - "*_delete*"
    - "*_terminate*"
    - "*_shutdown*"
    - "admin_*"
    - "*_update*"
  auto_approved_tools:
    - "*_list*"
    - "*_find*"
    - "*_get*"
    - "*_search*"
    - "*_export*"
    - "*_logs*"
    - "*_pods*"
    - "*_info*"
    - "*_billing*"
    - "*_faults*"
    - "*_status*"
    - "*_config*"
    - "*_region*"
    - "*_describe*"
    - "*_show*"
    - "*_view*"
    - "jit_token"
    - "jit_gcp"
    - "jit_aws"
    - "jit_web"
    - "jit_k8s"
    - "jit_k8s_context"
    - "system_*"
```

### Tool Classification Logic

| Tool Pattern | Behavior |
|-------------|----------|
| Matches `exclude_tools` (blacklist) | Tool is completely blocked - not available to LLM |
| Matches `auto_approve_tools` | Tool executes automatically without user approval |
| Matches neither | Tool requires user approval before execution |

---

## Technical Discovery

### Agno Already Has HITL Infrastructure

Investigation revealed that Agno SDK already has Human-in-the-Loop support:

**ToolExecution dataclass** (`agno/models/response.py`):
```python
@dataclass
class ToolExecution:
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    result: Optional[str] = None

    # HITL fields
    requires_confirmation: Optional[bool] = None
    confirmed: Optional[bool] = None
    confirmation_note: Optional[str] = None

    @property
    def is_paused(self) -> bool:
        return bool(self.requires_confirmation or ...)
```

**Toolkit base class** (`agno/tools/toolkit.py`):
```python
class Toolkit:
    def __init__(
        self,
        ...
        requires_confirmation_tools: Optional[list[str]] = None,  # Tools needing approval
        ...
    ):
```

**Agent pause/resume flow** (`agno/agent/agent.py`):
- When a tool has `requires_confirmation=True`, Agno pauses execution
- Returns `RunOutput` with `status=RunStatus.paused`
- `continue_run()` / `acontinue_run()` methods resume execution after approval

### State Persistence Challenge

Agno's pause/resume requires persisting state between requests. Agno has its own DB abstraction, but DCAF doesn't use it.

**Solution**: Store Agno's paused `RunOutput` in DCAF's `Session`.

- `RunOutput` has `to_dict()` and `from_dict()` methods for serialization
- DCAF's `Session` travels with requests/responses via `data.session` field
- State is preserved across HTTP request boundaries

---

## Design

### Architecture Overview

```
Request 1: "Delete pod nginx-123"
│
├─► MCPTool has auto_approve_tools=["*_list*", "*_get*"]
│   delete_pod matches NEITHER, so requires_confirmation=True
│
├─► Agno runs, LLM calls delete_pod
│   Agno sees requires_confirmation=True, pauses
│   Returns RunOutput(status=paused, tools=[{requires_confirmation=True}])
│
├─► ResponseConverter sees is_paused=True
│   Sets paused_run_state = run_output.to_dict()
│
├─► Agent.run() sees paused_run_state
│   Stores: session.set("_agno_paused_run", paused_run_state)
│
└─► Returns AgentResponse(
        needs_approval=True,
        pending_tools=[delete_pod],
        session={...,"_agno_paused_run": {...}}
    )

─────────────────────────────────────────────────────

Request 2: User approves delete_pod
│
├─► Session arrives with _agno_paused_run
│
├─► Agent.run() sees paused_run in session
│   Extracts approved tool IDs from request
│
├─► Calls runtime.continue_run(paused_run, approved_ids)
│   Agno marks tool.confirmed=True, executes tool
│   Continues agentic loop
│
├─► session.delete("_agno_paused_run")
│
└─► Returns AgentResponse(text="Deleted pod nginx-123")
```

### Components to Modify

#### 0. Compression Utilities (`dcaf/core/utils/compression.py`)

**New module for session state compression:**

```python
"""
Compression utilities for storing large state objects in session.

Used primarily for Agno RunOutput which can contain full conversation
history and grow to several megabytes.
"""

import base64
import gzip
import json
from typing import Any


def compress_for_session(data: dict[str, Any]) -> str:
    """
    Compress a dictionary for storage in session.

    Args:
        data: Dictionary to compress (must be JSON-serializable)

    Returns:
        Base64-encoded gzip-compressed string

    Example:
        compressed = compress_for_session(run_output.to_dict())
        session.set("_agno_paused_run", compressed)
    """
    json_bytes = json.dumps(data, separators=(',', ':')).encode('utf-8')
    compressed = gzip.compress(json_bytes, compresslevel=6)
    return base64.b64encode(compressed).decode('ascii')


def decompress_from_session(compressed: str) -> dict[str, Any]:
    """
    Decompress a dictionary from session storage.

    Args:
        compressed: Base64-encoded gzip-compressed string

    Returns:
        Original dictionary

    Example:
        compressed = session.get("_agno_paused_run")
        data = decompress_from_session(compressed)
        run_output = RunOutput.from_dict(data)
    """
    compressed_bytes = base64.b64decode(compressed.encode('ascii'))
    json_bytes = gzip.decompress(compressed_bytes)
    return json.loads(json_bytes.decode('utf-8'))
```

#### 1. MCPTool (`dcaf/mcp/tools.py`)

**Add new parameters:**

```python
class MCPTool:
    def __init__(
        self,
        command: str | None = None,
        *,
        url: str | None = None,
        env: dict[str, str] | None = None,
        transport: Literal["stdio", "sse", "streamable-http"] = "stdio",
        timeout_seconds: int = 10,
        include_tools: list[str] | None = None,
        exclude_tools: list[str] | None = None,      # Supports glob patterns
        auto_approve_tools: list[str] | None = None,  # NEW: Supports glob patterns
        tool_name_prefix: str | None = None,
        refresh_connection: bool = False,
        pre_hook: PreHookFunc | None = None,
        post_hook: PostHookFunc | None = None,
    ):
        ...
        self._auto_approve_tools = auto_approve_tools
```

**Add pattern matching helper:**

```python
def _match_pattern(self, tool_name: str, patterns: list[str]) -> bool:
    """Check if tool_name matches any glob pattern."""
    import fnmatch
    return any(fnmatch.fnmatch(tool_name, pattern) for pattern in patterns)

def _build_confirmation_tools_list(self, all_tool_names: list[str]) -> list[str]:
    """
    Build list of tools that require confirmation.

    Logic:
    - Tools matching exclude_tools: already filtered out by Agno
    - Tools matching auto_approve_tools: don't need confirmation
    - Everything else: needs confirmation
    """
    confirmation_tools = []
    for name in all_tool_names:
        if self._auto_approve_tools and self._match_pattern(name, self._auto_approve_tools):
            continue  # Auto-approved, no confirmation needed
        confirmation_tools.append(name)
    return confirmation_tools
```

**After connecting, pass to Agno:**

```python
async def connect(self, force: bool = False) -> None:
    ...
    # After tools are loaded, build confirmation list
    if self._auto_approve_tools is not None:
        tool_names = list(self._agno_mcp_tools.functions.keys())
        confirmation_tools = self._build_confirmation_tools_list(tool_names)
        self._agno_mcp_tools.requires_confirmation_tools = confirmation_tools
        logger.info(f"MCPTool: {len(confirmation_tools)} tools require confirmation")
```

#### 2. AgnoAdapter (`dcaf/core/adapters/outbound/agno/adapter.py`)

**Add `continue_run` method using RunRequirement API:**

```python
async def continue_run(
    self,
    paused_run_compressed: str,  # Compressed, serialized RunOutput
    confirmed_requirement_ids: list[str],
    rejected_requirement_ids: list[str] | None = None,
    tools: list[Any] | None = None,
    system_prompt: str | None = None,
    platform_context: dict[str, Any] | None = None,
) -> AgentResponse:
    """
    Continue a paused run after user approval.

    Args:
        paused_run_compressed: Compressed, serialized RunOutput from session
        confirmed_requirement_ids: List of requirement IDs that user approved
        rejected_requirement_ids: List of requirement IDs that user rejected
        tools: Tools to use (same as original request)
        system_prompt: System prompt (same as original request)
        platform_context: Platform context for tracing

    Returns:
        AgentResponse with continued execution result
    """
    from agno.run.agent import RunOutput

    # Decompress and deserialize the paused run
    paused_data = decompress_run_output(paused_run_compressed)
    run_output = RunOutput.from_dict(paused_data)

    # Use RunRequirement API to confirm/reject tools
    rejected_requirement_ids = rejected_requirement_ids or []
    for requirement in run_output.active_requirements:
        if requirement.id in confirmed_requirement_ids:
            requirement.confirm()
        elif requirement.id in rejected_requirement_ids:
            requirement.reject()

    # Create agent with same configuration
    agno_agent = await self._create_agent_async(
        tools or [],
        system_prompt,
        platform_context=platform_context
    )

    # Extract tracing parameters
    tracing_kwargs = self._extract_tracing_kwargs(platform_context)

    # Continue the paused run
    continued_output = await agno_agent.acontinue_run(
        run_response=run_output,
        **tracing_kwargs
    )

    # Convert to AgentResponse
    conversation_id = tracing_kwargs.get("run_id") or run_output.run_id or ""
    metrics = self._response_converter.extract_metrics(continued_output)

    return self._response_converter.convert_run_output(
        run_output=continued_output,
        conversation_id=conversation_id,
        metrics=metrics,
        tracing_context=tracing_kwargs,
    )
```

#### 3. AgentResponse (`dcaf/core/application/dto/responses.py`)

**Add fields for paused state and pending requirements:**

```python
@dataclass
class AgentResponse:
    conversation_id: str = ""
    text: str | None = None
    data: DataDTO | None = None
    has_pending_approvals: bool = False
    is_complete: bool = True
    metadata: dict[str, Any] | None = None
    # NEW: Compressed, serialized RunOutput when paused (base64 gzip string)
    paused_run_state: str | None = None
    # NEW: Pending requirements for UI display
    pending_requirements: list[dict] | None = None
```

The `pending_requirements` list contains info for the approval UI:
```python
[
    {
        "requirement_id": "req-abc123",  # Use this ID for approve/reject
        "tool_name": "delete_pod",
        "tool_args": {"name": "nginx-123", "namespace": "default"}
    },
    ...
]
```

#### 4. Response Converter (`dcaf/core/adapters/outbound/agno/response_converter.py`)

**Include compressed serialized state when paused:**

```python
def convert_run_output(
    self,
    run_output: Any,
    conversation_id: str,
    metrics: AgnoMetrics | None = None,
    tracing_context: dict[str, Any] | None = None,
) -> AgentResponse:
    text = self._extract_text_content(run_output)
    tool_calls, has_pending = self._extract_tool_calls(run_output)

    # Check if run is paused
    is_paused = getattr(run_output, "status", None) == RunStatus.paused
    if is_paused:
        has_pending = True

    # Compress and serialize paused state for session storage
    paused_state_compressed = None
    pending_requirements = []
    if is_paused:
        paused_state_compressed = compress_run_output(run_output.to_dict())
        # Extract pending requirements for UI
        pending_requirements = [
            {
                "requirement_id": req.id,
                "tool_name": req.tool_execution.tool_name,
                "tool_args": req.tool_execution.tool_args,
            }
            for req in run_output.active_requirements
        ]

    is_complete = getattr(run_output, "status", None) == RunStatus.completed and not has_pending
    data = DataDTO(tool_calls=tool_calls)
    response_metadata = self._build_response_metadata(tracing_context)

    return AgentResponse(
        conversation_id=conversation_id,
        text=text,
        data=data,
        has_pending_approvals=has_pending,
        is_complete=is_complete,
        metadata=response_metadata,
        paused_run_state=paused_state_compressed,  # Compressed string
        pending_requirements=pending_requirements,  # For UI display
    )
```

#### 5. Agent (`dcaf/core/agent.py`)

**Store/retrieve compressed paused state in Session:**

```python
async def _execute_with_session(
    self,
    messages: list,
    context: dict,
    session: Session
) -> AgentResponse:
    """Execute agent, handling paused run resumption."""

    # Check if we're resuming a paused run (stored as compressed string)
    paused_run_compressed = session.get("_agno_paused_run")

    if paused_run_compressed:
        # We're resuming - get approved/rejected requirement IDs from the request
        approved_ids = self._extract_approved_requirement_ids(messages, context)
        rejected_ids = self._extract_rejected_requirement_ids(messages, context)

        response = await self._runtime.continue_run(
            paused_run_compressed=paused_run_compressed,
            confirmed_requirement_ids=approved_ids,
            rejected_requirement_ids=rejected_ids,
            tools=self._tools,
            system_prompt=self._system_prompt,
            platform_context=context.get("platform_context"),
        )

        # Clear the paused state after resumption
        session.delete("_agno_paused_run")
    else:
        # Normal execution
        response = await self._agent_service.execute(...)

    # If execution paused, store compressed state in session for next request
    if response.paused_run_state:
        session.set("_agno_paused_run", response.paused_run_state)

    return response

def _extract_approved_requirement_ids(self, messages: list, context: dict) -> list[str]:
    """Extract requirement IDs that user approved from the request."""
    # Look in the latest message's data.tool_calls for approvals
    # Tool calls with execute=True are approved
    approved_ids = []

    for msg in reversed(messages):
        data = msg.get("data", {})
        tool_calls = data.get("tool_calls", [])
        for tc in tool_calls:
            if tc.get("execute", False):
                # Map tool_call.id to requirement_id
                # (These should match the requirement_id we returned)
                approved_ids.append(tc.get("id"))
        if approved_ids:
            break

    return approved_ids

def _extract_rejected_requirement_ids(self, messages: list, context: dict) -> list[str]:
    """Extract requirement IDs that user rejected from the request."""
    rejected_ids = []

    for msg in reversed(messages):
        data = msg.get("data", {})
        tool_calls = data.get("tool_calls", [])
        for tc in tool_calls:
            if not tc.get("execute", False) and tc.get("rejection_reason"):
                rejected_ids.append(tc.get("id"))
        if rejected_ids:
            break

    return rejected_ids
```

---

## Implementation Tasks

### Phase 1: MCPTool Pattern Matching

1. Add `auto_approve_tools` parameter to MCPTool
2. Implement `_match_pattern()` using `fnmatch`
3. Implement `_build_confirmation_tools_list()`
4. Pass `requires_confirmation_tools` to underlying Agno MCPTools after connect
5. Add unit tests for pattern matching

### Phase 2: Response Handling

1. Add `paused_run_state` field to `AgentResponse`
2. Update `AgnoResponseConverter.convert_run_output()` to serialize paused state
3. Add unit tests for paused state serialization

### Phase 3: Adapter Continue Method

1. Add `continue_run()` method to `AgnoAdapter`
2. Handle tool confirmation marking
3. Add integration tests with mock Agno agent

### Phase 4: Agent Session Integration

1. Update Agent to check session for paused runs
2. Implement extraction of approved/rejected tool IDs
3. Store paused state in session when execution pauses
4. Clear paused state after successful continuation
5. Add end-to-end tests

### Phase 5: Documentation

1. Update mkdocs with MCP tool approval documentation
2. Add usage examples
3. Document configuration options
4. Add troubleshooting guide

---

## Usage Example

```python
from dcaf import Agent
from dcaf.mcp import MCPTool

# Create MCP tool with approval configuration
mcp_tool = MCPTool(
    url="https://mcp-server.example.com/mcp",
    transport="streamable-http",

    # Block dangerous tools entirely
    exclude_tools=[
        "*_delete*",
        "*_terminate*",
        "admin_*",
    ],

    # Auto-approve read-only tools
    auto_approve_tools=[
        "*_list*",
        "*_get*",
        "*_describe*",
        "*_status*",
    ],

    # Everything else requires user approval
)

# Create agent with MCP tool
agent = Agent(
    name="k8s-assistant",
    tools=[mcp_tool],
    instructions="You help users manage Kubernetes clusters.",
)

# When user asks to delete something:
# 1. Agent will pause with pending_tools
# 2. Client shows approval UI
# 3. Client sends approval with session
# 4. Agent continues execution
```

---

## Design Decisions

### 1. Session Size and Compression

**Decision**: Use gzip compression for serialized `RunOutput` before storing in session.

**Rationale**:
- `RunOutput` contains full conversation history and can grow large (observed up to 14MB in production)
- Session travels in HTTP body (not headers), so size is limited by server config
- Gzip typically achieves 5-10x compression on JSON text

**Implementation**:
```python
import gzip
import base64
import json

def compress_run_output(run_output: dict) -> str:
    """Compress RunOutput for session storage."""
    json_bytes = json.dumps(run_output).encode('utf-8')
    compressed = gzip.compress(json_bytes)
    return base64.b64encode(compressed).decode('ascii')

def decompress_run_output(compressed: str) -> dict:
    """Decompress RunOutput from session storage."""
    compressed_bytes = base64.b64decode(compressed.encode('ascii'))
    json_bytes = gzip.decompress(compressed_bytes)
    return json.loads(json_bytes.decode('utf-8'))
```

Session storage:
```python
# Store compressed
session.set("_agno_paused_run", compress_run_output(run_output.to_dict()))

# Retrieve and decompress
paused_data = decompress_run_output(session.get("_agno_paused_run"))
run_output = RunOutput.from_dict(paused_data)
```

### 2. No Timeout (TTL)

**Decision**: Paused runs have no expiration. Users can respond days or weeks later.

**Rationale**:
- DCAF is not holding Agno connections open
- State is fully serialized and can be reconstructed at any time
- Business workflows may have long approval cycles (manager OOO, weekends, etc.)
- Session expiration is handled at the application/infrastructure level, not DCAF

**Behavior**:
- Paused state persists as long as the session persists
- If session expires (server-side), user must start a new conversation
- No artificial TTL imposed by DCAF

### 3. Multiple Pending Tools (Batch Approval)

**Decision**: Support batch approval with per-tool confirm/reject decisions.

**Rationale**:
- Agno already supports multiple `RunRequirement` objects in `active_requirements`
- DCAF's existing tool approval UI supports showing multiple pending tools
- Users should be able to approve some tools and reject others in a single request

**Implementation using RunRequirement API**:
```python
# When resuming, use Agno's RunRequirement API
for req in paused_run.active_requirements:
    if req.id in approved_requirement_ids:
        req.confirm()  # Sets tool_execution.confirmed = True
    elif req.id in rejected_requirement_ids:
        req.reject()   # Sets tool_execution.confirmed = False

# Continue execution - Agno handles partial execution
continued = await agent.acontinue_run(run_response=paused_run)
```

**Mixed tools behavior** (from Agno docs):
- Auto-approved tools execute immediately without pausing
- Only tools requiring confirmation cause a pause
- If user asks "list pods then delete pod X":
  - `list_pods` executes immediately (auto-approved)
  - Agent pauses at `delete_pod` (needs confirmation)
  - User approves → execution continues

### 4. Rejection Handling

**Decision**: Rejected tools are marked as failed, and the LLM continues with that information.

**Rationale**:
- Agno's `requirement.reject()` sets `tool_execution.confirmed = False`
- Agno creates a tool result message: "Function call was rejected by the user"
- LLM sees the rejection and can respond appropriately (apologize, offer alternative, etc.)
- This allows partial success in batch scenarios

**Behavior**:
```
User: "Delete pod A, pod B, and pod C"
Agent: [Requests approval for delete_pod(A), delete_pod(B), delete_pod(C)]
User: Approves A and C, rejects B
Agent:
  - Executes delete_pod(A) ✓
  - Sees rejection for delete_pod(B) - "Rejected by user"
  - Executes delete_pod(C) ✓
  - Responds: "I deleted pods A and C. Pod B was not deleted as you rejected that operation."
```

---

## Updated Architecture with RunRequirement

Agno provides a clean `RunRequirement` abstraction for HITL flows. Updated design:

### Key Agno HITL Components

**RunRequirement** (`agno/run/requirement.py`):
```python
@dataclass
class RunRequirement:
    tool_execution: Optional[ToolExecution] = None
    confirmation: Optional[bool] = None
    confirmation_note: Optional[str] = None

    @property
    def needs_confirmation(self) -> bool: ...

    def confirm(self):
        """Approve this requirement."""
        self.confirmation = True
        self.tool_execution.confirmed = True

    def reject(self):
        """Reject this requirement."""
        self.confirmation = False
        self.tool_execution.confirmed = False

    def is_resolved(self) -> bool:
        """Return True if requirement has been handled."""
```

**RunOutput properties**:
```python
run_output.is_paused           # True if waiting for user input
run_output.active_requirements  # List of unresolved RunRequirement objects
```

### Updated Flow

```
Request 1: "List pods then delete nginx-123"
│
├─► MCPTool: list_pods is auto-approved, delete_pod needs confirmation
│
├─► Agno runs:
│   ├─► list_pods executes immediately (auto-approved)
│   └─► delete_pod triggers pause (needs confirmation)
│
├─► RunOutput returned:
│   ├─► status = RunStatus.paused
│   ├─► is_paused = True
│   └─► active_requirements = [RunRequirement(tool=delete_pod)]
│
├─► DCAF compresses and stores:
│   session.set("_agno_paused_run", compress(run_output.to_dict()))
│
└─► Returns to user:
    {
      "has_pending_approvals": true,
      "pending_tools": [{
        "requirement_id": "req-123",
        "tool_name": "delete_pod",
        "tool_args": {"name": "nginx-123"}
      }]
    }

─────────────────────────────────────────────────────

Request 2: User approves delete_pod
│
├─► Session contains compressed _agno_paused_run
│
├─► DCAF decompresses and reconstructs:
│   run_output = RunOutput.from_dict(decompress(session.get(...)))
│
├─► Apply user decisions via RunRequirement API:
│   for req in run_output.active_requirements:
│       if req.id in approved_ids:
│           req.confirm()
│       elif req.id in rejected_ids:
│           req.reject()
│
├─► Continue execution:
│   continued = await agent.acontinue_run(run_response=run_output)
│
├─► Clear session state:
│   session.delete("_agno_paused_run")
│
└─► Returns: "Listed pods. Deleted nginx-123 successfully."
```

---

## References

### External Documentation
- [Agno SDK GitHub](https://github.com/agno-agi/agno)
- [Agno HITL Overview](https://docs.agno.com/execution-control/hitl/overview)
- [Agno Mixed Tools with Confirmation](https://docs.agno.com/execution-control/hitl/usage/confirmation-required-mixed-tools)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)

### DCAF Internal
- DCAF Session: `dcaf/core/session.py`
- DCAF Tool Approval: `dcaf/schemas/messages.py` (ToolCall with execute flag)

### Agno Internal (from installed package)
- Agno Toolkit: `agno/tools/toolkit.py` - `requires_confirmation_tools` parameter
- Agno RunOutput: `agno/run/agent.py` - `is_paused`, `active_requirements`, `to_dict()`, `from_dict()`
- Agno RunRequirement: `agno/run/requirement.py` - `confirm()`, `reject()`, `is_resolved()`
- Agno ToolExecution: `agno/models/response.py` - `requires_confirmation`, `confirmed`
