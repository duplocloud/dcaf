# Approval Type Feature Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an `approval_type` field (`"tool_call"` or `"command"`) that flows from tool definitions through to the event stream, so UIs can render different approval experiences for shell commands vs structured tool calls.

**Architecture:** The `approval_type` is set at the source (decorator, toolkit registry, or MCPTool), propagated through `ToolCallDTO` → `ToolCall` schema → `ToolCallsEvent`, and read in `server_adapter` to dual-emit into the correct legacy collection (`ToolCallsEvent` for `tool_call`, `CommandsEvent` for `command`) alongside a unified `ApprovalsEvent` containing all approvals with their types. The `AgnoResponseConverter` receives a registry dict so it can annotate tool calls with their type at event creation time.

**Tech Stack:** Python 3.11+, Pydantic v2, FastAPI, Agno SDK, pytest, mkdocs

---

## Data Flow Reference

```
@tool(approval_type="command")           → Tool.approval_type
_convert_tools_to_agno()                 → adapter._tool_approval_types["run_kubectl"] = "command"
TOOLKIT_TOOL_APPROVAL_TYPES              → {"run_shell_command": "command", ...}
MCPTool(approval_type="command")         → adapter._tool_approval_types["mcp_tool_name"] = "command"
                                                      ↓
AgnoResponseConverter(tool_approval_types)
  RunPausedEvent handler                 → ToolCallDTO(approval_type="command")
  ToolCallDTO.to_dict()                  → {"approval_type": "command", ...}
                                                      ↓
agent.py _convert_stream_event()         → SchemaToolCall(approval_type="command")
  → ToolCallsEvent(tool_calls=[...])
                                                      ↓
server_adapter.py Gap 1 translation:
  ApprovalsEvent([{type:"command"}, {type:"tool_call"}])   ← all approvals, mixed types OK
  CommandsEvent([...])                                      ← only "command" items
  ToolCallsEvent([...])                                     ← only "tool_call" items
```

---

### Task 1: Add `approval_type` to `Tool` class and `@tool` decorator

**Files:**
- Modify: `dcaf/core/tools.py:208-218` (Tool class fields)
- Modify: `dcaf/core/tools.py:303-419` (tool decorator)
- Test: `tests/core/test_tools.py`

**Step 1: Write failing tests**

Add to `tests/core/test_tools.py`:

```python
def test_tool_approval_type_defaults_to_tool_call():
    @tool(description="A test tool")
    def my_tool(x: str) -> str:
        return x
    assert my_tool.approval_type == "tool_call"

def test_tool_approval_type_can_be_set_to_command():
    @tool(description="Run a shell command", approval_type="command")
    def run_cmd(cmd: str) -> str:
        return cmd
    assert run_cmd.approval_type == "command"

def test_tool_approval_type_preserved_in_tool_object():
    @tool(description="kubectl", approval_type="command")
    def kubectl(args: str) -> str:
        return args
    assert isinstance(kubectl, Tool)
    assert kubectl.approval_type == "command"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/core/test_tools.py -k "approval_type" -v
```
Expected: `FAILED` — `Tool` has no `approval_type` attribute.

**Step 3: Implement**

In `dcaf/core/tools.py`, add field to `Tool` class after `requires_approval`:

```python
requires_approval: bool = False
approval_type: str = "tool_call"   # ← add this line
requires_platform_context: bool = False
```

In `tool()` decorator function signature (line ~308), add after `requires_approval`:

```python
def tool(
    func: Callable | None = None,
    *,
    description: str | None = None,
    name: str | None = None,
    requires_approval: bool = True,
    approval_type: str = "tool_call",   # ← add this
    schema: dict[str, Any] | type[BaseModel] | Any | None = None,
) -> Tool | Callable[[Callable], Tool]:
```

Update the docstring Args section to add:
```
        approval_type: UI hint for approval experience. "tool_call" shows a structured
                       tool approval dialog; "command" shows a terminal/command-line
                       approval dialog. Defaults to "tool_call".
```

In `decorator()` inner function where `Tool` is constructed (line ~404), add the field:

```python
return Tool(
    func=fn,
    name=name or func_name,
    description=tool_description,
    input_schema=tool_schema,
    requires_approval=requires_approval,
    approval_type=approval_type,          # ← add this
    requires_platform_context=requires_platform_context,
)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/core/test_tools.py -k "approval_type" -v
```
Expected: 3 PASSED.

**Step 5: Commit**

```bash
git add dcaf/core/tools.py tests/core/test_tools.py
git commit -m "feat(tools): add approval_type field to Tool class and @tool decorator"
```

---

### Task 2: Add `approval_type` to `ToolCallDTO`

**Files:**
- Modify: `dcaf/core/application/dto/responses.py:89-165`
- Test: `tests/core/test_dtos.py` (or nearest DTO test file — check with `ls tests/core/`)

**Step 1: Write failing test**

Find or create a test for `ToolCallDTO`. Add:

```python
def test_tool_call_dto_approval_type_defaults_to_tool_call():
    dto = ToolCallDTO(id="1", name="foo", input={})
    assert dto.approval_type == "tool_call"

def test_tool_call_dto_approval_type_in_to_dict():
    dto = ToolCallDTO(id="1", name="foo", input={}, approval_type="command")
    d = dto.to_dict()
    assert d["approval_type"] == "command"

def test_tool_call_dto_from_dict_preserves_approval_type():
    d = {"id": "1", "name": "foo", "input": {}, "approval_type": "command"}
    dto = ToolCallDTO.from_dict(d)
    assert dto.approval_type == "command"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/core/ -k "tool_call_dto_approval_type" -v
```

**Step 3: Implement**

In `dcaf/core/application/dto/responses.py`, add field to `ToolCallDTO` dataclass after `rejection_reason`:

```python
rejection_reason: str | None = None
approval_type: str = "tool_call"   # ← add this
```

In `to_dict()`, add before the `return`:

```python
result["approval_type"] = self.approval_type
```

In `from_dict()`, add to constructor call:

```python
return cls(
    ...
    rejection_reason=data.get("rejection_reason"),
    approval_type=data.get("approval_type", "tool_call"),   # ← add this
)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/core/ -k "tool_call_dto_approval_type" -v
```

**Step 5: Commit**

```bash
git add dcaf/core/application/dto/responses.py
git commit -m "feat(dto): add approval_type to ToolCallDTO with to_dict/from_dict support"
```

---

### Task 3: Add `approval_type` to `ToolCall` schema

**Files:**
- Modify: `dcaf/schemas/messages.py:24-32`
- Test: `tests/core/test_unified_approvals.py` (existing file)

**Step 1: Write failing test**

Add to `tests/core/test_unified_approvals.py`:

```python
def test_tool_call_schema_approval_type_defaults_to_tool_call():
    from dcaf.schemas.messages import ToolCall
    tc = ToolCall(
        id="t1",
        name="my_tool",
        input={},
        tool_description="A tool",
        input_description={},
    )
    assert tc.approval_type == "tool_call"

def test_tool_call_schema_approval_type_can_be_command():
    from dcaf.schemas.messages import ToolCall
    tc = ToolCall(
        id="t1",
        name="run_kubectl",
        input={"args": "get pods"},
        tool_description="Run kubectl",
        input_description={},
        approval_type="command",
    )
    assert tc.approval_type == "command"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/core/test_unified_approvals.py -k "tool_call_schema_approval_type" -v
```

**Step 3: Implement**

In `dcaf/schemas/messages.py`, add field to `ToolCall` after `rejection_reason`:

```python
class ToolCall(BaseModel):
    id: str
    name: str
    input: dict[str, Any]
    execute: bool = False
    tool_description: str
    input_description: dict[str, Any]
    intent: str | None = None
    rejection_reason: str | None = None
    approval_type: str = "tool_call"   # ← add this
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/core/test_unified_approvals.py -k "tool_call_schema_approval_type" -v
```

**Step 5: Commit**

```bash
git add dcaf/schemas/messages.py tests/core/test_unified_approvals.py
git commit -m "feat(schemas): add approval_type field to ToolCall schema"
```

---

### Task 4: Build toolkit approval type registry in `AgnoAdapter`

**Files:**
- Modify: `dcaf/core/adapters/outbound/agno/adapter.py`
- Test: `tests/core/test_agno_adapter.py`

**Step 1: Write failing tests**

Add to `tests/core/test_agno_adapter.py`:

```python
def test_toolkit_approval_types_marks_shell_as_command():
    from dcaf.core.adapters.outbound.agno.adapter import TOOLKIT_TOOL_APPROVAL_TYPES
    assert TOOLKIT_TOOL_APPROVAL_TYPES.get("run_shell_command") == "command"

def test_toolkit_approval_types_marks_python_as_tool_call():
    from dcaf.core.adapters.outbound.agno.adapter import TOOLKIT_TOOL_APPROVAL_TYPES
    assert TOOLKIT_TOOL_APPROVAL_TYPES.get("run_python_code", "tool_call") == "tool_call"

def test_convert_tools_to_agno_registers_dcaf_tool_approval_type(make_agent):
    """@tool with approval_type="command" must be in _tool_approval_types."""
    from dcaf.core.tools import tool
    from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

    @tool(description="Run kubectl", approval_type="command", requires_approval=True)
    def run_kubectl(args: str) -> str:
        return args

    adapter = AgnoAdapter.__new__(AgnoAdapter)
    adapter._tool_approval_types = {}
    adapter._tool_converter = MagicMock()
    adapter._tool_converter.to_agno.return_value = {
        "name": "run_kubectl", "description": "Run kubectl"
    }
    adapter._is_dcaf_mcp_tools = lambda x: False

    adapter._convert_tools_to_agno([run_kubectl])
    assert adapter._tool_approval_types.get("run_kubectl") == "command"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/core/test_agno_adapter.py -k "toolkit_approval_types or registers_dcaf_tool" -v
```

**Step 3: Implement**

Near the top of `dcaf/core/adapters/outbound/agno/adapter.py`, after imports, add the module-level registry:

```python
# Approval type registry for native Agno toolkits.
# Tools not listed default to "tool_call".
TOOLKIT_TOOL_APPROVAL_TYPES: dict[str, str] = {
    "run_shell_command": "command",   # ShellTools — executes arbitrary shell commands
}
```

In `AgnoAdapter.__init__()` (or wherever `self._response_converter` is set up), initialize the instance registry:

```python
self._tool_approval_types: dict[str, str] = {}
```

In `_convert_tools_to_agno()`, in the DCAF tool branch (after `decorated_tool = agno_tool_decorator(...)`), register the tool's approval type:

```python
decorated_tool = agno_tool_decorator(
    name=tool_schema["name"],
    description=tool_schema["description"],
    requires_confirmation=tool_obj.requires_approval or None,
)(func_to_wrap)

# Register approval type for this tool
self._tool_approval_types[tool_schema["name"]] = tool_obj.approval_type   # ← add this

agno_tools.append(decorated_tool)
```

For the MCP branch, after appending the toolkit, register all known functions (handles pre-connected tools):

```python
if self._is_dcaf_mcp_tools(tool_obj):
    agno_toolkit = tool_obj._get_agno_toolkit(auto_create=True)
    agno_tools.append(agno_toolkit)

    # Register approval type for all known MCP tool functions
    mcp_approval_type = getattr(tool_obj, "_approval_type", "tool_call")
    if hasattr(agno_toolkit, "functions") and agno_toolkit.functions:
        for func_name in agno_toolkit.functions:
            self._tool_approval_types[func_name] = mcp_approval_type

    continue
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/core/test_agno_adapter.py -k "toolkit_approval_types or registers_dcaf_tool" -v
```

**Step 5: Commit**

```bash
git add dcaf/core/adapters/outbound/agno/adapter.py tests/core/test_agno_adapter.py
git commit -m "feat(agno): add TOOLKIT_TOOL_APPROVAL_TYPES registry and _tool_approval_types instance dict"
```

---

### Task 5: Pass registry to `AgnoResponseConverter` and annotate `ToolCallDTO`

**Files:**
- Modify: `dcaf/core/adapters/outbound/agno/response_converter.py`
- Modify: `dcaf/core/adapters/outbound/agno/adapter.py:227` (instantiation site)
- Test: `tests/core/test_agno_response_converter.py` (or nearest converter test)

**Step 1: Write failing tests**

```python
def test_response_converter_annotates_shell_tool_as_command():
    from dcaf.core.adapters.outbound.agno.response_converter import AgnoResponseConverter
    from dcaf.core.adapters.outbound.agno.adapter import TOOLKIT_TOOL_APPROVAL_TYPES

    converter = AgnoResponseConverter(tool_approval_types=TOOLKIT_TOOL_APPROVAL_TYPES)

    # Simulate RunPausedEvent with run_shell_command
    tool_exec = MagicMock()
    tool_exec.requires_confirmation = True
    tool_exec.tool_call_id = "tc-1"
    tool_exec.tool_name = "run_shell_command"
    tool_exec.tool_args = {"args": ["kubectl", "get", "pods"]}

    event = MagicMock()
    type(event).__name__ = "RunPausedEvent"
    event.tools = [tool_exec]

    result = converter.convert_stream_event(event)
    assert result is not None
    tool_calls = result.data["tool_calls"]
    assert tool_calls[0].approval_type == "command"

def test_response_converter_defaults_unknown_tool_to_tool_call():
    from dcaf.core.adapters.outbound.agno.response_converter import AgnoResponseConverter

    converter = AgnoResponseConverter(tool_approval_types={})
    tool_exec = MagicMock()
    tool_exec.requires_confirmation = True
    tool_exec.tool_call_id = "tc-2"
    tool_exec.tool_name = "my_custom_tool"
    tool_exec.tool_args = {}

    event = MagicMock()
    type(event).__name__ = "RunPausedEvent"
    event.tools = [tool_exec]

    result = converter.convert_stream_event(event)
    assert result.data["tool_calls"][0].approval_type == "tool_call"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/core/ -k "response_converter_annotates or defaults_unknown_tool" -v
```

**Step 3: Implement**

In `response_converter.py`, update the class constructor:

```python
class AgnoResponseConverter:
    def __init__(self, tool_approval_types: dict[str, str] | None = None) -> None:
        self._tool_approval_types = tool_approval_types or {}
```

In `convert_stream_event()`, update the `RunPausedEvent` handler:

```python
elif event_type in ("RunPausedEvent", "RunPaused"):
    paused_tools = getattr(agno_event, "tools", None) or []
    tool_calls = []
    for tool_exec in paused_tools:
        if getattr(tool_exec, "requires_confirmation", False):
            tool_name = getattr(tool_exec, "tool_name", "") or ""
            approval_type = self._tool_approval_types.get(tool_name, "tool_call")
            tool_calls.append(
                ToolCallDTO(
                    id=getattr(tool_exec, "tool_call_id", "") or "",
                    name=tool_name,
                    input=getattr(tool_exec, "tool_args", {}) or {},
                    requires_approval=True,
                    status="pending",
                    approval_type=approval_type,   # ← new
                )
            )
    if tool_calls:
        return StreamEvent.tool_calls_event(tool_calls)
    return None
```

In `adapter.py` at line 227, pass the registry:

```python
self._tool_approval_types: dict[str, str] = {}
self._response_converter = AgnoResponseConverter(
    tool_approval_types=self._tool_approval_types
)
```

**Important:** `self._tool_approval_types` must be initialized BEFORE `AgnoResponseConverter` is instantiated. The converter holds a reference to the same dict object, so entries added later by `_convert_tools_to_agno()` will be visible.

**Step 4: Run tests to verify they pass**

```bash
pytest tests/core/ -k "response_converter_annotates or defaults_unknown_tool" -v
```

**Step 5: Commit**

```bash
git add dcaf/core/adapters/outbound/agno/response_converter.py dcaf/core/adapters/outbound/agno/adapter.py
git commit -m "feat(agno): pass tool_approval_types registry to AgnoResponseConverter"
```

---

### Task 6: Propagate `approval_type` through `agent.py` when building `SchemaToolCall`

**Files:**
- Modify: `dcaf/core/agent.py:1256-1271`
- Test: (covered by integration — no isolated unit test needed here, the chain is tested end-to-end in Task 8)

**Step 1: Read the target code**

Open `dcaf/core/agent.py` around line 1256 and confirm you see `SchemaToolCall(...)` being constructed from `tc_data`.

**Step 2: Implement**

The `SchemaToolCall` is imported as an alias for `dcaf.schemas.messages.ToolCall`. Update the constructor call at line ~1260:

```python
schema_tool_calls = [
    SchemaToolCall(
        id=tc_data.get("id", ""),
        name=tc_data.get("name", ""),
        input=tc_data.get("input", {}),
        tool_description=tc_data.get("tool_description", ""),
        input_description=tc_data.get("input_description", {}),
        approval_type=tc_data.get("approval_type", "tool_call"),  # ← add this
    )
    for tc in tool_calls_data
    for tc_data in (tc if isinstance(tc, dict) else tc.to_dict(),)
]
```

**Step 3: Run all approval-related tests**

```bash
pytest tests/core/test_unified_approvals.py tests/core/test_agno_adapter.py -v
```
Expected: all pass.

**Step 4: Commit**

```bash
git add dcaf/core/agent.py
git commit -m "feat(agent): propagate approval_type through SchemaToolCall construction"
```

---

### Task 7: Update `server_adapter.py` dual-emit logic

This is the most visible change: instead of hardcoding `type="tool_call"` and always emitting `ToolCallsEvent`, we now:
1. Emit `ApprovalsEvent` with all approvals (each with their `type`)
2. Emit `ToolCallsEvent` only for `tool_call` items
3. Emit `CommandsEvent` only for `command` items

**Files:**
- Modify: `dcaf/core/adapters/inbound/server_adapter.py:244-278`
- Test: `tests/core/test_unified_approvals.py`

**Step 1: Write failing tests**

Add to `tests/core/test_unified_approvals.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from dcaf.schemas.events import ApprovalsEvent, ToolCallsEvent, CommandsEvent
from dcaf.schemas.messages import ToolCall

class TestServerAdapterDualEmit:

    def _make_tool_call(self, name: str, approval_type: str) -> ToolCall:
        return ToolCall(
            id=f"id-{name}",
            name=name,
            input={},
            tool_description="",
            input_description={},
            approval_type=approval_type,
        )

    @pytest.mark.asyncio
    async def test_tool_call_type_emits_approvals_and_tool_calls_event(self):
        """approval_type='tool_call' → ApprovalsEvent + ToolCallsEvent, no CommandsEvent."""
        from dcaf.core.adapters.inbound.server_adapter import ServerAdapter
        adapter = _make_server_adapter_with_events([
            ToolCallsEvent(tool_calls=[self._make_tool_call("my_tool", "tool_call")])
        ])
        events = [e async for e in adapter.run_stream(MagicMock())]
        event_types = [type(e).__name__ for e in events]
        assert "ApprovalsEvent" in event_types
        assert "ToolCallsEvent" in event_types
        assert "CommandsEvent" not in event_types

    @pytest.mark.asyncio
    async def test_command_type_emits_approvals_and_commands_event(self):
        """approval_type='command' → ApprovalsEvent + CommandsEvent, no ToolCallsEvent."""
        adapter = _make_server_adapter_with_events([
            ToolCallsEvent(tool_calls=[self._make_tool_call("run_shell_command", "command")])
        ])
        events = [e async for e in adapter.run_stream(MagicMock())]
        event_types = [type(e).__name__ for e in events]
        assert "ApprovalsEvent" in event_types
        assert "CommandsEvent" in event_types
        assert "ToolCallsEvent" not in event_types

    @pytest.mark.asyncio
    async def test_mixed_types_split_into_separate_legacy_events(self):
        """Mixed types → one ApprovalsEvent (all), split into CommandsEvent + ToolCallsEvent."""
        tool_calls = [
            self._make_tool_call("run_shell_command", "command"),
            self._make_tool_call("get_user", "tool_call"),
        ]
        adapter = _make_server_adapter_with_events([
            ToolCallsEvent(tool_calls=tool_calls)
        ])
        events = [e async for e in adapter.run_stream(MagicMock())]

        approvals_events = [e for e in events if isinstance(e, ApprovalsEvent)]
        cmd_events = [e for e in events if isinstance(e, CommandsEvent)]
        tc_events = [e for e in events if isinstance(e, ToolCallsEvent)]

        assert len(approvals_events) == 1
        assert len(approvals_events[0].approvals) == 2   # both in unified event
        assert len(cmd_events) == 1                       # command only
        assert len(tc_events) == 1                        # tool_call only

    @pytest.mark.asyncio
    async def test_approvals_event_carries_correct_types(self):
        tool_calls = [
            self._make_tool_call("run_shell_command", "command"),
            self._make_tool_call("get_user", "tool_call"),
        ]
        adapter = _make_server_adapter_with_events([
            ToolCallsEvent(tool_calls=tool_calls)
        ])
        events = [e async for e in adapter.run_stream(MagicMock())]
        approvals = next(e for e in events if isinstance(e, ApprovalsEvent)).approvals
        types = {a.name: a.type for a in approvals}
        assert types["run_shell_command"] == "command"
        assert types["get_user"] == "tool_call"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/core/test_unified_approvals.py -k "TestServerAdapterDualEmit" -v
```

**Step 3: Implement**

Replace the Gap 1 block in `server_adapter.py` (lines ~244-278):

```python
# Gap 1: translate ToolCallsEvent → ApprovalsEvent + split legacy events by approval_type
if isinstance(event, ToolCallsEvent) and event.tool_calls:
    # Unified event — all approvals with their types (future-facing clients)
    approvals = [
        Approval(
            id=tc.id,
            type=tc.approval_type,          # ← read from ToolCall, not hardcoded
            name=tc.name,
            input=tc.input,
            description=tc.tool_description,
            intent=tc.intent,
        )
        for tc in event.tool_calls
    ]
    yield ApprovalsEvent(approvals=approvals)

    # Legacy: split by type — emit ToolCallsEvent only for tool_call items
    tool_call_items = [tc for tc in event.tool_calls if tc.approval_type != "command"]
    if tool_call_items:
        yield ToolCallsEvent(tool_calls=tool_call_items)

    # Legacy: emit CommandsEvent only for command items
    command_items = [tc for tc in event.tool_calls if tc.approval_type == "command"]
    if command_items:
        from dcaf.schemas.messages import Command
        commands = [
            Command(
                command=tc.name,
                input=tc.input,
            )
            for tc in command_items
        ]
        yield CommandsEvent(commands=commands)

    continue   # don't fall through to the raw yield below
```

**Note:** Check whether `Command` from `dcaf/schemas/messages.py` has the right fields. Read that class before implementing — adjust field names if needed. Also remove the existing `continue`-less `yield event` at the end of the block if it would double-emit `ToolCallsEvent`.

**Step 4: Run tests**

```bash
pytest tests/core/test_unified_approvals.py -v
```

**Step 5: Run full suite to check for regressions**

```bash
pytest tests/ -v --ignore=tests/test_channel_routing.py
```

**Step 6: Commit**

```bash
git add dcaf/core/adapters/inbound/server_adapter.py tests/core/test_unified_approvals.py
git commit -m "feat(server): dual-emit ApprovalsEvent + type-split legacy events based on approval_type"
```

---

### Task 8: Add `approval_type` to `MCPTool`

**Files:**
- Modify: `dcaf/mcp/tools.py:145-239`
- Test: `tests/core/test_mcp_approval_flow.py`

**Step 1: Write failing test**

Add to `tests/core/test_mcp_approval_flow.py`:

```python
def test_mcp_tool_approval_type_defaults_to_tool_call():
    mcp = MCPTool(url="http://localhost:8000", transport="streamable-http")
    assert mcp._approval_type == "tool_call"

def test_mcp_tool_approval_type_can_be_command():
    mcp = MCPTool(
        url="http://localhost:8000",
        transport="streamable-http",
        approval_type="command",
    )
    assert mcp._approval_type == "command"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/core/test_mcp_approval_flow.py -k "mcp_tool_approval_type" -v
```

**Step 3: Implement**

In `DCaF/mcp/tools.py`, add `approval_type` parameter to `__init__()` after `auto_approve_tools`:

```python
def __init__(
    self,
    command: str | None = None,
    *,
    url: str | None = None,
    ...
    auto_approve_tools: list[str] | None = None,
    approval_type: str = "tool_call",   # ← add this
    pre_hook: PreHookFunc | None = None,
    ...
):
```

Add to docstring Args:
```
            approval_type: UI hint for approval experience when this server's tools
                          require approval. "tool_call" shows structured tool dialog;
                          "command" shows terminal-style approval. Defaults to "tool_call".
```

Store in `__init__()` body alongside other assignments:

```python
self._approval_type = approval_type
```

**Step 4: Run tests**

```bash
pytest tests/core/test_mcp_approval_flow.py -v
```

**Step 5: Commit**

```bash
git add dcaf/mcp/tools.py tests/core/test_mcp_approval_flow.py
git commit -m "feat(mcp): add approval_type parameter to MCPTool"
```

---

### Task 9: End-to-end integration test

Verify the whole pipeline works together with a test that goes from `@tool` to emitted events.

**Files:**
- Test: `tests/core/test_approval_type_e2e.py` (new file)

**Step 1: Write the test**

```python
"""End-to-end test: approval_type flows from @tool through to ApprovalsEvent."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dcaf.core.tools import tool
from dcaf.schemas.events import ApprovalsEvent, CommandsEvent, ToolCallsEvent


@pytest.fixture
def kubectl_tool():
    @tool(description="Run kubectl", approval_type="command", requires_approval=True)
    def run_kubectl(args: str) -> str:
        return args
    return run_kubectl


@pytest.fixture
def regular_tool():
    @tool(description="Get user", approval_type="tool_call", requires_approval=True)
    def get_user(user_id: str) -> str:
        return user_id
    return regular_tool


def test_tool_approval_type_set_correctly(kubectl_tool, regular_tool):
    assert kubectl_tool.approval_type == "command"
    assert regular_tool.approval_type == "tool_call"


def test_tool_call_dto_carries_approval_type(kubectl_tool):
    from dcaf.core.application.dto.responses import ToolCallDTO
    dto = ToolCallDTO(id="1", name="run_kubectl", input={}, approval_type="command")
    d = dto.to_dict()
    assert d["approval_type"] == "command"


def test_schema_tool_call_carries_approval_type():
    from dcaf.schemas.messages import ToolCall
    tc = ToolCall(
        id="1", name="run_kubectl", input={},
        tool_description="Run kubectl", input_description={},
        approval_type="command",
    )
    assert tc.approval_type == "command"
```

**Step 2: Run**

```bash
pytest tests/core/test_approval_type_e2e.py -v
```
Expected: all pass (these validate the pieces work together, not the live stream).

**Step 3: Run full suite**

```bash
pytest tests/ -v --ignore=tests/test_channel_routing.py
```
Expected: all pass (2 pre-existing failures in `test_channel_routing.py` are acceptable).

**Step 4: Commit**

```bash
git add tests/core/test_approval_type_e2e.py
git commit -m "test(approval): end-to-end integration tests for approval_type pipeline"
```

---

### Task 10: Documentation — `docs/guides/tool-approval-types.md`

Create a comprehensive guide explaining the entire approval type system.

**Files:**
- Create: `docs/guides/tool-approval-types.md`
- Modify: `mkdocs.yml` (add to nav under Guides)

**Step 1: Create the doc file**

Write `docs/guides/tool-approval-types.md` with the following structure:

```markdown
# Tool Approval Types

DCAF supports two distinct approval experiences for tools that require human confirmation
before execution. The `approval_type` field controls which UI experience is presented
to the user.

## Overview

When a tool requires approval (via `requires_approval=True`), the agent pauses and emits
approval events. The `approval_type` field tells the UI *how* to render the approval dialog:

| Type | UI Experience | Use When |
|------|--------------|----------|
| `tool_call` | Structured approval dialog showing tool name, inputs, and description | The LLM is calling a structured function (default) |
| `command` | Terminal-style command-line approval showing the command to be executed | The agent is about to run a shell command |

## How It Works

### The Approval Event Pipeline

```
Tool definition (approval_type="command")
         ↓
AgnoAdapter builds tool registry
         ↓
Agno pauses → RunPausedEvent
         ↓
AgnoResponseConverter looks up tool name in registry
         → ToolCallDTO(approval_type="command")
         ↓
agent.py converts to ToolCall schema
         → ToolCall(approval_type="command")
         ↓
ToolCallsEvent emitted
         ↓
ServerAdapter Gap 1 translation:
   → ApprovalsEvent([{type:"command", ...}])  ← all approvals (unified)
   → CommandsEvent([...])                      ← only command items (legacy)
   OR
   → ToolCallsEvent([...])                     ← only tool_call items (legacy)
```

### Emitted Events

For every approval, the server emits **three events** in order:

1. **`ApprovalsEvent`** — unified event containing ALL pending approvals, each with
   a `type` field set to `"command"` or `"tool_call"`. This is the future-facing
   event that clients should adopt.

2. **`ToolCallsEvent`** *(legacy)* — contains only the `tool_call`-type items.
   Emitted for backward compatibility with clients that handle `data.tool_calls`.

3. **`CommandsEvent`** *(legacy)* — contains only the `command`-type items.
   Emitted for backward compatibility with clients that handle `data.cmds`.

!!! warning "Never handle both unified and legacy events"
    If your client handles `approvals`, do not also handle `tool_calls` or `commands`
    — you will show duplicate approval dialogs. Choose one strategy and stick to it.

## Setting `approval_type` on `@tool`

For DCAF-defined tools, set `approval_type` directly on the decorator:

```python
from dcaf.core import tool

# Default: structured tool approval
@tool(description="Fetch user from database", requires_approval=True)
def get_user(user_id: str) -> str:
    return fetch_user(user_id)

# Command-line approval: shows terminal UI
@tool(description="Run kubectl command", requires_approval=True, approval_type="command")
def run_kubectl(args: str) -> str:
    import subprocess
    return subprocess.check_output(["kubectl"] + args.split()).decode()
```

The `approval_type` defaults to `"tool_call"` — you only need to set it explicitly
for command-line tools.

## Built-in Toolkit Approval Types

When using the default toolkit (`DEFAULT_TOOLKIT=true`), DCAF automatically assigns
approval types to native Agno tools:

| Tool | Toolkit | approval_type |
|------|---------|--------------|
| `run_shell_command` | `ShellTools` | `"command"` |
| `run_python_code` | `PythonTools` | `"tool_call"` |
| `read_file`, `write_file`, etc. | `FileTools` / `LocalFileSystemTools` | `"tool_call"` |

These mappings are defined in `TOOLKIT_TOOL_APPROVAL_TYPES` in
`dcaf/core/adapters/outbound/agno/adapter.py` and can be extended if needed.

## MCP Tools

For MCP servers, set `approval_type` at the `MCPTool` level. All tools exposed by
that server inherit the same type:

```python
from dcaf.mcp import MCPTool

# Most MCP servers expose structured tools — use the default
files_mcp = MCPTool(url="http://localhost:3001/mcp")

# A kubectl MCP server wraps shell commands — use "command"
kubectl_mcp = MCPTool(
    url="http://localhost:3002/mcp",
    approval_type="command",
)
```

Note: `approval_type` on `MCPTool` applies to all tools from that server. If a server
mixes command-like and structured tools, prefer leaving it as `"tool_call"` (default)
or splitting into two `MCPTool` instances.

For tools that should never require approval, use `auto_approve_tools`:

```python
mcp = MCPTool(
    url="http://my-server/mcp",
    auto_approve_tools=["*_list*", "*_get*"],  # read-only tools auto-approve
    approval_type="command",                   # remaining tools use terminal UI
)
```

## Client Implementation Guide

### Unified Clients (recommended)

Listen for `approvals` events. Each item has a `type` field:

```javascript
if (event.type === "approvals") {
    for (const approval of event.approvals) {
        if (approval.type === "command") {
            showTerminalApprovalDialog(approval);
        } else {
            showToolCallApprovalDialog(approval);
        }
    }
}
```

When the user approves or rejects, send back a follow-up request with `data.approvals`:

```json
{
  "messages": [...previous messages...],
  "data": {
    "approvals": [
      {
        "id": "abc123",
        "type": "command",
        "name": "run_shell_command",
        "input": {"args": ["kubectl", "get", "pods"]},
        "execute": true
      }
    ]
  }
}
```

### Legacy Clients

Legacy clients use `data.tool_calls` for structured tools and `data.cmds` for
command-line tools. These continue to work but receive events based on `approval_type`:

- `tool_calls` collection → populated when `approval_type == "tool_call"`
- `cmds` collection → populated when `approval_type == "command"`

See [Message Protocol](../guides/message-protocol.md) and [Streaming Responses](../guides/streaming.md)
for full schema details.

## Why Two Types?

The distinction matters for user experience:

- **`tool_call`** — the user sees what function is being called with what inputs.
  They understand the agent is making a structured API call. The UI can show
  parameter names, types, and descriptions.

- **`command`** — the user sees an actual shell command string. They understand
  the agent is about to execute something on their infrastructure. The UI typically
  shows a terminal-style preview with the full command and a clear warning.

Shell commands have higher blast radius (they can do anything the process can do),
which is why the terminal approval UI sets a clearer expectation than a generic
"Tool X wants to execute" dialog.
```

**Step 2: Add to mkdocs.yml nav**

In `mkdocs.yml`, under `Guides:`, add after `Building Tools`:

```yaml
    - Tool Approval Types: guides/tool-approval-types.md
```

**Step 3: Build docs to verify**

```bash
mkdocs build --strict
```
Expected: builds without errors.

**Step 4: Commit**

```bash
git add docs/guides/tool-approval-types.md mkdocs.yml
git commit -m "docs: add comprehensive tool-approval-types guide to mkdocs"
```

---

### Task 11: Final verification

**Step 1: Run full test suite**

```bash
pytest tests/ -v --ignore=tests/test_channel_routing.py
```

**Step 2: Run linting and type checking**

```bash
ruff check .
ruff format --check .
mypy dcaf/
```

**Step 3: Build docs**

```bash
mkdocs build --strict
```

**Step 4: Check import linter**

```bash
lint-imports
```

**Step 5: If all pass, create PR**

```bash
git push origin feature/llm-layer-local
gh pr create --title "feat: add approval_type to distinguish command vs tool_call approvals" \
  --body "..."
```

---

## Summary of Files Changed

| File | Change |
|------|--------|
| `dcaf/core/tools.py` | Add `approval_type: str = "tool_call"` to `Tool` + `@tool` |
| `dcaf/core/application/dto/responses.py` | Add `approval_type` to `ToolCallDTO` + `to_dict()`/`from_dict()` |
| `dcaf/schemas/messages.py` | Add `approval_type` to `ToolCall` schema |
| `dcaf/core/adapters/outbound/agno/adapter.py` | `TOOLKIT_TOOL_APPROVAL_TYPES` constant + `_tool_approval_types` instance dict |
| `dcaf/core/adapters/outbound/agno/response_converter.py` | Accept registry in constructor, use in `RunPausedEvent` handler |
| `dcaf/core/agent.py` | Pass `approval_type` when building `SchemaToolCall` |
| `dcaf/core/adapters/inbound/server_adapter.py` | Read `tc.approval_type`, split legacy events by type |
| `dcaf/mcp/tools.py` | Add `approval_type` param to `MCPTool.__init__()` |
| `docs/guides/tool-approval-types.md` | New comprehensive guide |
| `mkdocs.yml` | Add new doc to nav |
