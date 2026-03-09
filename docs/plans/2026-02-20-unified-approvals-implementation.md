# Unified Approvals Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add unified `data.approvals[]` / `data.executed_approvals[]` fields and processing to DCAF, enabling a single approval lifecycle path with a `type` discriminator for UI rendering.

**Architecture:** New `Approval` and `ExecutedApproval` Pydantic models added to both public and core schemas. Two new stream events (`ApprovalsEvent`, `ExecutedApprovalsEvent`) added to both event schemas. `ServerAdapter` gets a `_process_approvals()` method that reuses the existing `_execute_tool()` path. All changes are additive — legacy `cmds` and `tool_calls` fields remain untouched.

**Tech Stack:** Python 3.11+, Pydantic, FastAPI, pytest

**Design doc:** `docs/plans/2026-02-20-unified-approvals-design.md`

---

### Task 1: Add Approval and ExecutedApproval models to public schemas

**Files:**
- Modify: `dcaf/schemas/messages.py` (after `ExecutedToolCall` at line 40, and in `Data` at line 63)
- Test: `tests/core/test_unified_approvals.py` (create)

**Step 1: Write the failing test**

Create `tests/core/test_unified_approvals.py`:

```python
"""Tests for the unified approvals data models and processing."""

import pytest
from dcaf.schemas.messages import Approval, ExecutedApproval, Data


class TestApprovalModel:
    def test_approval_with_all_fields(self):
        approval = Approval(
            id="ap-1",
            type="command",
            name="execute_terminal_cmd",
            input={"command": "kubectl get pods"},
            execute=True,
            description="List all pods",
            intent="User asked to see running pods",
        )
        assert approval.id == "ap-1"
        assert approval.type == "command"
        assert approval.execute is True

    def test_approval_defaults(self):
        approval = Approval(
            id="ap-2",
            type="tool_call",
            name="delete_pod",
            input={"pod": "nginx"},
        )
        assert approval.execute is False
        assert approval.rejection_reason is None
        assert approval.description == ""
        assert approval.intent is None

    def test_approval_rejection(self):
        approval = Approval(
            id="ap-3",
            type="command",
            name="execute_terminal_cmd",
            input={"command": "kubectl delete pod nginx"},
            execute=False,
            rejection_reason="Don't delete that pod",
        )
        assert approval.execute is False
        assert approval.rejection_reason == "Don't delete that pod"


class TestExecutedApprovalModel:
    def test_executed_approval(self):
        executed = ExecutedApproval(
            id="ap-1",
            type="command",
            name="execute_terminal_cmd",
            input={"command": "kubectl get pods"},
            output="NAME  READY  STATUS\nnginx  1/1  Running",
        )
        assert executed.output == "NAME  READY  STATUS\nnginx  1/1  Running"

    def test_executed_approval_rejection_output(self):
        executed = ExecutedApproval(
            id="ap-2",
            type="tool_call",
            name="delete_pod",
            input={"pod": "nginx"},
            output="Rejected: Don't delete that pod",
        )
        assert "Rejected" in executed.output


class TestDataApprovalFields:
    def test_data_has_approvals_field(self):
        data = Data()
        assert data.approvals == []
        assert data.executed_approvals == []

    def test_data_with_approvals(self):
        data = Data(
            approvals=[
                Approval(
                    id="ap-1",
                    type="command",
                    name="execute_terminal_cmd",
                    input={"command": "ls"},
                )
            ],
            executed_approvals=[
                ExecutedApproval(
                    id="ap-0",
                    type="tool_call",
                    name="list_pods",
                    input={"namespace": "default"},
                    output="pod1\npod2",
                )
            ],
        )
        assert len(data.approvals) == 1
        assert len(data.executed_approvals) == 1

    def test_data_legacy_fields_still_work(self):
        """Legacy cmds and tool_calls fields are unaffected."""
        data = Data()
        assert data.cmds == []
        assert data.tool_calls == []
        assert data.executed_cmds == []
        assert data.executed_tool_calls == []
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_unified_approvals.py -v`
Expected: FAIL with `ImportError: cannot import name 'Approval'`

**Step 3: Write minimal implementation**

Add to `dcaf/schemas/messages.py` after `ExecutedToolCall` (after line 40):

```python
class Approval(BaseModel):
    id: str
    type: str
    name: str
    input: Dict[str, Any]
    execute: bool = False
    rejection_reason: Optional[str] = None
    description: str = ""
    intent: Optional[str] = None


class ExecutedApproval(BaseModel):
    id: str
    type: str
    name: str
    input: Dict[str, Any]
    output: str
```

Add to `Data` class (after `executed_tool_calls`):

```python
    approvals: List[Approval] = Field(default_factory=list)
    executed_approvals: List[ExecutedApproval] = Field(default_factory=list)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_unified_approvals.py -v`
Expected: PASS (all 7 tests)

**Step 5: Commit**

```bash
git add dcaf/schemas/messages.py tests/core/test_unified_approvals.py
git commit -m "feat: add Approval and ExecutedApproval models to public schemas"
```

---

### Task 2: Add Approval and ExecutedApproval models to core schemas

**Files:**
- Modify: `dcaf/core/schemas/messages.py` (after `ExecutedToolCall` at line 40, and in `Data` at line 86)

**Step 1: Write the failing test**

Add to `tests/core/test_unified_approvals.py`:

```python
from dcaf.core.schemas.messages import (
    Approval as CoreApproval,
    ExecutedApproval as CoreExecutedApproval,
    Data as CoreData,
)


class TestCoreApprovalModel:
    def test_core_approval_matches_public(self):
        approval = CoreApproval(
            id="ap-1",
            type="command",
            name="execute_terminal_cmd",
            input={"command": "kubectl get pods"},
        )
        assert approval.id == "ap-1"
        assert approval.type == "command"

    def test_core_data_has_approvals(self):
        data = CoreData()
        assert data.approvals == []
        assert data.executed_approvals == []

    def test_core_data_session_field_still_works(self):
        """Core Data has session field that public Data doesn't."""
        data = CoreData(session={"wizard_step": 2})
        assert data.session == {"wizard_step": 2}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_unified_approvals.py::TestCoreApprovalModel -v`
Expected: FAIL with `ImportError: cannot import name 'Approval'`

**Step 3: Write minimal implementation**

Add the same `Approval` and `ExecutedApproval` classes to `dcaf/core/schemas/messages.py` after `ExecutedToolCall` (after line 40). Add the same two fields to the core `Data` class (after `executed_tool_calls`).

**Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_unified_approvals.py -v`
Expected: PASS (all 10 tests)

**Step 5: Commit**

```bash
git add dcaf/core/schemas/messages.py tests/core/test_unified_approvals.py
git commit -m "feat: add Approval and ExecutedApproval models to core schemas"
```

---

### Task 3: Add ApprovalsEvent and ExecutedApprovalsEvent to public events

**Files:**
- Modify: `dcaf/schemas/events.py` (after `CommandsEvent` at line 48, before `DoneEvent`)

**Step 1: Write the failing test**

Add to `tests/core/test_unified_approvals.py`:

```python
from dcaf.schemas.events import ApprovalsEvent, ExecutedApprovalsEvent


class TestApprovalEvents:
    def test_approvals_event(self):
        event = ApprovalsEvent(
            approvals=[
                Approval(
                    id="ap-1",
                    type="command",
                    name="execute_terminal_cmd",
                    input={"command": "kubectl get pods"},
                )
            ]
        )
        assert event.type == "approvals"
        assert len(event.approvals) == 1

    def test_executed_approvals_event(self):
        event = ExecutedApprovalsEvent(
            executed_approvals=[
                ExecutedApproval(
                    id="ap-1",
                    type="command",
                    name="execute_terminal_cmd",
                    input={"command": "kubectl get pods"},
                    output="pod1\npod2",
                )
            ]
        )
        assert event.type == "executed_approvals"
        assert len(event.executed_approvals) == 1

    def test_approvals_event_serialization(self):
        event = ApprovalsEvent(
            approvals=[
                Approval(
                    id="ap-1",
                    type="tool_call",
                    name="delete_pod",
                    input={"pod": "nginx"},
                    description="Delete the nginx pod",
                )
            ]
        )
        data = event.model_dump()
        assert data["type"] == "approvals"
        assert data["approvals"][0]["type"] == "tool_call"
        assert data["approvals"][0]["name"] == "delete_pod"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_unified_approvals.py::TestApprovalEvents -v`
Expected: FAIL with `ImportError: cannot import name 'ApprovalsEvent'`

**Step 3: Write minimal implementation**

Add to `dcaf/schemas/events.py` after `CommandsEvent` (after line 48), and add `Approval`, `ExecutedApproval` to the import from `.messages`:

```python
class ApprovalsEvent(StreamEvent):
    """Unified approval requests for frontend UI (commands, tool calls, etc.)"""

    type: Literal["approvals"] = "approvals"
    approvals: list[Approval]


class ExecutedApprovalsEvent(StreamEvent):
    """Results of executed approvals (before LLM call)"""

    type: Literal["executed_approvals"] = "executed_approvals"
    executed_approvals: list[ExecutedApproval]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_unified_approvals.py -v`
Expected: PASS (all 13 tests)

**Step 5: Commit**

```bash
git add dcaf/schemas/events.py tests/core/test_unified_approvals.py
git commit -m "feat: add ApprovalsEvent and ExecutedApprovalsEvent to public events"
```

---

### Task 4: Add ApprovalsEvent and ExecutedApprovalsEvent to core events

**Files:**
- Modify: `dcaf/core/schemas/events.py` (after `CommandsEvent` at line 48)

**Step 1: Write the failing test**

Add to `tests/core/test_unified_approvals.py`:

```python
from dcaf.core.schemas.events import (
    ApprovalsEvent as CoreApprovalsEvent,
    ExecutedApprovalsEvent as CoreExecutedApprovalsEvent,
)


class TestCoreApprovalEvents:
    def test_core_approvals_event(self):
        event = CoreApprovalsEvent(
            approvals=[
                CoreApproval(
                    id="ap-1",
                    type="command",
                    name="execute_terminal_cmd",
                    input={"command": "ls"},
                )
            ]
        )
        assert event.type == "approvals"

    def test_core_executed_approvals_event(self):
        event = CoreExecutedApprovalsEvent(
            executed_approvals=[
                CoreExecutedApproval(
                    id="ap-1",
                    type="tool_call",
                    name="list_pods",
                    input={},
                    output="pod1",
                )
            ]
        )
        assert event.type == "executed_approvals"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_unified_approvals.py::TestCoreApprovalEvents -v`
Expected: FAIL with `ImportError: cannot import name 'ApprovalsEvent'`

**Step 3: Write minimal implementation**

Add the same two event classes to `dcaf/core/schemas/events.py` after `CommandsEvent` (after line 48). Update the import line to include `Approval` and `ExecutedApproval`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_unified_approvals.py -v`
Expected: PASS (all 15 tests)

**Step 5: Commit**

```bash
git add dcaf/core/schemas/events.py tests/core/test_unified_approvals.py
git commit -m "feat: add ApprovalsEvent and ExecutedApprovalsEvent to core events"
```

---

### Task 5: Add `_process_approvals()` to ServerAdapter

**Files:**
- Modify: `dcaf/core/adapters/inbound/server_adapter.py` (add method after `_execute_tool` at line 321)

**Step 1: Write the failing test**

Add to `tests/core/test_unified_approvals.py`:

```python
from dcaf.core.adapters.inbound.server_adapter import ServerAdapter
from dcaf.core.schemas.messages import ExecutedApproval as CoreExecutedApproval
from unittest.mock import MagicMock


def _make_mock_agent_with_tool(tool_name: str, tool_result: str):
    """Create a mock Agent with a single tool that returns a fixed result."""
    mock_tool = MagicMock()
    mock_tool.name = tool_name
    mock_tool.execute = MagicMock(return_value=tool_result)

    mock_agent = MagicMock()
    mock_agent.tools = [mock_tool]
    return mock_agent, mock_tool


class TestProcessApprovals:
    def test_approved_approval_executes_tool(self):
        agent, tool = _make_mock_agent_with_tool("list_pods", "pod1\npod2")
        adapter = ServerAdapter(agent)

        messages_list = [
            {
                "role": "user",
                "content": "approve",
                "data": {
                    "approvals": [
                        {
                            "id": "ap-1",
                            "type": "tool_call",
                            "name": "list_pods",
                            "input": {"namespace": "default"},
                            "execute": True,
                        }
                    ]
                },
            }
        ]

        result = adapter._process_approvals(messages_list, {})

        assert len(result) == 1
        assert result[0].id == "ap-1"
        assert result[0].type == "tool_call"
        assert result[0].name == "list_pods"
        assert result[0].output == "pod1\npod2"
        tool.execute.assert_called_once_with({"namespace": "default"}, {})

    def test_rejected_approval_does_not_execute(self):
        agent, tool = _make_mock_agent_with_tool("delete_pod", "deleted")
        adapter = ServerAdapter(agent)

        messages_list = [
            {
                "role": "user",
                "content": "reject",
                "data": {
                    "approvals": [
                        {
                            "id": "ap-2",
                            "type": "tool_call",
                            "name": "delete_pod",
                            "input": {"pod": "nginx"},
                            "execute": False,
                            "rejection_reason": "Too dangerous",
                        }
                    ]
                },
            }
        ]

        result = adapter._process_approvals(messages_list, {})

        assert len(result) == 1
        assert result[0].id == "ap-2"
        assert "Rejected" in result[0].output
        assert "Too dangerous" in result[0].output
        tool.execute.assert_not_called()

    def test_empty_approvals_returns_empty(self):
        agent, _ = _make_mock_agent_with_tool("list_pods", "pod1")
        adapter = ServerAdapter(agent)

        result = adapter._process_approvals([{"role": "user", "content": "hi"}], {})
        assert result == []

    def test_no_data_returns_empty(self):
        agent, _ = _make_mock_agent_with_tool("list_pods", "pod1")
        adapter = ServerAdapter(agent)

        result = adapter._process_approvals([], {})
        assert result == []

    def test_mixed_approve_reject(self):
        agent = MagicMock()
        tool_a = MagicMock()
        tool_a.name = "list_pods"
        tool_a.execute = MagicMock(return_value="pod1")
        tool_b = MagicMock()
        tool_b.name = "delete_pod"
        agent.tools = [tool_a, tool_b]
        adapter = ServerAdapter(agent)

        messages_list = [
            {
                "role": "user",
                "content": "mixed",
                "data": {
                    "approvals": [
                        {
                            "id": "ap-1",
                            "type": "tool_call",
                            "name": "list_pods",
                            "input": {},
                            "execute": True,
                        },
                        {
                            "id": "ap-2",
                            "type": "command",
                            "name": "delete_pod",
                            "input": {"pod": "nginx"},
                            "execute": False,
                            "rejection_reason": "No",
                        },
                    ]
                },
            }
        ]

        result = adapter._process_approvals(messages_list, {})

        assert len(result) == 2
        assert result[0].output == "pod1"
        assert "Rejected" in result[1].output
        tool_a.execute.assert_called_once()
        tool_b.execute.assert_not_called()

    def test_command_type_approval(self):
        """Command-type approvals work through the same path."""
        agent, tool = _make_mock_agent_with_tool(
            "execute_terminal_cmd", "NAME  READY\nnginx  1/1"
        )
        adapter = ServerAdapter(agent)

        messages_list = [
            {
                "role": "user",
                "content": "approve",
                "data": {
                    "approvals": [
                        {
                            "id": "ap-1",
                            "type": "command",
                            "name": "execute_terminal_cmd",
                            "input": {"command": "kubectl get pods"},
                            "execute": True,
                        }
                    ]
                },
            }
        ]

        result = adapter._process_approvals(messages_list, {})

        assert len(result) == 1
        assert result[0].type == "command"
        assert result[0].output == "NAME  READY\nnginx  1/1"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_unified_approvals.py::TestProcessApprovals -v`
Expected: FAIL with `AttributeError: 'ServerAdapter' object has no attribute '_process_approvals'`

**Step 3: Write minimal implementation**

Add to `dcaf/core/adapters/inbound/server_adapter.py` after `_execute_tool()` (after line 321). Also add `ExecutedApproval` to the import from `....schemas.messages`:

```python
    def _process_approvals(
        self,
        messages_list: list[dict[str, Any]],
        platform_context: dict[str, Any],
    ) -> list[ExecutedApproval]:
        """
        Process approved/rejected items from the unified approvals field.

        Reads data.approvals[] from the latest message. For each:
        - If execute=True: runs the tool via _execute_tool() and captures output
        - If rejection_reason is set: captures the rejection as output
        """
        executed: list[ExecutedApproval] = []

        if not messages_list:
            return executed

        latest_message = messages_list[-1]
        data = latest_message.get("data", {})
        approvals = data.get("approvals", [])

        for approval in approvals:
            approval_id = approval.get("id", "")
            approval_type = approval.get("type", "")
            name = approval.get("name", "")
            tool_input = approval.get("input", {})

            if approval.get("execute", False):
                result = self._execute_tool(name, tool_input, platform_context)
                executed.append(
                    ExecutedApproval(
                        id=approval_id,
                        type=approval_type,
                        name=name,
                        input=tool_input,
                        output=result,
                    )
                )
            elif approval.get("rejection_reason"):
                executed.append(
                    ExecutedApproval(
                        id=approval_id,
                        type=approval_type,
                        name=name,
                        input=tool_input,
                        output=f"Rejected: {approval['rejection_reason']}",
                    )
                )

        return executed
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_unified_approvals.py -v`
Expected: PASS (all 21 tests)

**Step 5: Commit**

```bash
git add dcaf/core/adapters/inbound/server_adapter.py tests/core/test_unified_approvals.py
git commit -m "feat: add _process_approvals() to ServerAdapter"
```

---

### Task 6: Wire `_process_approvals()` into `invoke()` and `invoke_stream()`

**Files:**
- Modify: `dcaf/core/adapters/inbound/server_adapter.py` (lines 72-142 for invoke, lines 144-208 for invoke_stream)

**Step 1: Write the failing test**

Add to `tests/core/test_unified_approvals.py`:

```python
import asyncio
from dcaf.core.schemas.events import (
    ExecutedApprovalsEvent as CoreExecutedApprovalsEvent,
    TextDeltaEvent,
    DoneEvent,
)


def _make_mock_agent_for_invoke(tool_name: str, tool_result: str, llm_response: str):
    """Create a mock Agent that handles invoke() end-to-end."""
    from unittest.mock import AsyncMock

    mock_tool = MagicMock()
    mock_tool.name = tool_name
    mock_tool.execute = MagicMock(return_value=tool_result)

    mock_response = MagicMock()
    mock_response.needs_approval = False
    mock_response.to_message.return_value = MagicMock(
        content=llm_response,
        data=MagicMock(executed_approvals=[], executed_tool_calls=[]),
    )

    mock_agent = MagicMock()
    mock_agent.tools = [mock_tool]
    mock_agent.run = AsyncMock(return_value=mock_response)

    async def fake_stream(*args, **kwargs):
        yield TextDeltaEvent(text=llm_response)
        yield DoneEvent()

    mock_agent.run_stream = MagicMock(side_effect=fake_stream)

    return mock_agent, mock_tool


class TestInvokeWithApprovals:
    def test_invoke_processes_approvals(self):
        agent, tool = _make_mock_agent_for_invoke(
            "list_pods", "pod1\npod2", "Here are your pods."
        )
        adapter = ServerAdapter(agent)

        messages = {
            "messages": [
                {
                    "role": "user",
                    "content": "yes, approve",
                    "data": {
                        "approvals": [
                            {
                                "id": "ap-1",
                                "type": "tool_call",
                                "name": "list_pods",
                                "input": {"namespace": "default"},
                                "execute": True,
                            }
                        ]
                    },
                }
            ]
        }

        result = asyncio.get_event_loop().run_until_complete(adapter.invoke(messages))

        tool.execute.assert_called_once()
        assert len(result.data.executed_approvals) == 1

    def test_invoke_stream_emits_executed_approvals_event(self):
        agent, tool = _make_mock_agent_for_invoke(
            "list_pods", "pod1", "Here are your pods."
        )
        adapter = ServerAdapter(agent)

        messages = {
            "messages": [
                {
                    "role": "user",
                    "content": "approve",
                    "data": {
                        "approvals": [
                            {
                                "id": "ap-1",
                                "type": "command",
                                "name": "list_pods",
                                "input": {},
                                "execute": True,
                            }
                        ]
                    },
                }
            ]
        }

        async def collect():
            events = []
            async for event in adapter.invoke_stream(messages):
                events.append(event)
            return events

        events = asyncio.get_event_loop().run_until_complete(collect())

        event_types = [e.type for e in events]
        assert "executed_approvals" in event_types
        exec_event = [e for e in events if e.type == "executed_approvals"][0]
        assert len(exec_event.executed_approvals) == 1
        assert exec_event.executed_approvals[0].output == "pod1"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_unified_approvals.py::TestInvokeWithApprovals -v`
Expected: FAIL — `_process_approvals()` is never called from `invoke()` or `invoke_stream()`, so `executed_approvals` will be empty / no `ExecutedApprovalsEvent` emitted.

**Step 3: Write minimal implementation**

In `invoke()` (around line 100), after the existing `_process_approved_tool_calls()` call, add:

```python
        # Process unified approvals
        executed_approvals = self._process_approvals(messages_list, context)
```

Before returning `agent_msg` (around line 130), after the `executed_tool_calls` extension block, add:

```python
            if executed_approvals:
                agent_msg.data.executed_approvals.extend(executed_approvals)
```

In `invoke_stream()` (around line 160), after the existing `_process_approved_tool_calls()` block and its `ExecutedToolCallsEvent` yield, add:

```python
        # Process unified approvals
        executed_approvals = self._process_approvals(messages_list, context)
        if executed_approvals:
            yield ExecutedApprovalsEvent(executed_approvals=executed_approvals)
```

Also inject results into `core_messages` for LLM context (same pattern as the existing tool call injection):

```python
        if executed_approvals:
            result_parts = [
                f"Tool result for {ea.name} with inputs {ea.input}: {ea.output}"
                for ea in executed_approvals
            ]
            result_content = "\n\n".join(result_parts)
            if core_messages and core_messages[-1]["role"] == "user":
                core_messages[-1]["content"] += "\n\n" + result_content
            else:
                core_messages.append({"role": "user", "content": result_content})
```

Add `ExecutedApprovalsEvent` to the import from `....schemas.events` at the top of the file.

**Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_unified_approvals.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add dcaf/core/adapters/inbound/server_adapter.py tests/core/test_unified_approvals.py
git commit -m "feat: wire _process_approvals into invoke() and invoke_stream()"
```

---

### Task 7: Run full test suite and verify no regressions

**Step 1: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: All existing tests PASS, no regressions. New test file passes.

**Step 2: Verify legacy paths still work**

Run: `pytest tests/core/test_approval_service.py tests/core/test_request_fields.py tests/v1/ -v`
Expected: All PASS — legacy `cmds` and `tool_calls` processing is untouched.

**Step 3: Commit (if any fixes were needed)**

```bash
git commit -m "fix: address test regressions from unified approvals"
```

---

### Task 8: Final commit — update design doc with implementation notes

**Files:**
- Modify: `docs/plans/2026-02-20-unified-approvals-design.md`

**Step 1: Add Phase 1 completion note**

Append to the design doc:

```markdown
## Phase 1 Status

Phase 1 complete. The following were added:
- `Approval` and `ExecutedApproval` models (both public and core schemas)
- `ApprovalsEvent` and `ExecutedApprovalsEvent` stream events (both public and core)
- `ServerAdapter._process_approvals()` wired into both `invoke()` and `invoke_stream()`
- Context injection for LLM to see approval results
- Full test coverage in `tests/core/test_unified_approvals.py`

Legacy `data.cmds` and `data.tool_calls` remain fully functional.
```

**Step 2: Commit**

```bash
git add docs/plans/2026-02-20-unified-approvals-design.md
git commit -m "docs: mark Phase 1 of unified approvals as complete"
```
