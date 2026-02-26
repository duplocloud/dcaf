# ServerAdapter Gap Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close six gaps in `ServerAdapter` so command-executing agents (k8s-agent, etc.) can migrate off ~300 lines of custom approval plumbing.

**Architecture:** All changes are additive to `dcaf/core/adapters/inbound/server_adapter.py`. A single new test file `tests/core/test_server_adapter.py` covers all new behavior. Existing tests in `test_unified_approvals.py` require one line updated due to `_execute_cmd` signature change.

**Tech Stack:** Python 3.11+, pytest-asyncio (auto mode), `subprocess`, `tempfile`, `shutil`, Pydantic v2, FastAPI streaming.

---

## Background: What exists today

`ServerAdapter` (`dcaf/core/adapters/inbound/server_adapter.py`) wraps a core `Agent` for use with the FastAPI server. It already handles three approval paths on inbound requests:
- `data.cmds[]` → `_process_approved_commands()`
- `data.tool_calls[]` → `_process_approved_tool_calls()`
- `data.approvals[]` → `_process_approvals()`

Six gaps prevent command-executing agents from fully migrating to it.

---

## Task 1: Pass `context` to `_process_approved_commands` (Gap 4)

**Why first:** The simplest change. Unblocks credential injection (kubeconfig, tokens) into subprocess. All other tasks build on this signature change.

**Files:**
- Modify: `dcaf/core/adapters/inbound/server_adapter.py`
- Create: `tests/core/test_server_adapter.py`

---

**Step 1: Create the test file with a failing test**

Create `tests/core/test_server_adapter.py`:

```python
"""Tests for ServerAdapter — gap fixes for command-executing agents."""

from unittest.mock import MagicMock, patch

import pytest

from dcaf.core.adapters.inbound.server_adapter import ServerAdapter


def _make_adapter(**kwargs):
    """Create a ServerAdapter with a minimal mock agent."""
    mock_agent = MagicMock()
    mock_agent.tools = []
    return ServerAdapter(mock_agent, **kwargs)


class TestProcessApprovedCommandsReceivesContext:
    def test_context_is_passed_to_execute_cmd(self):
        """_process_approved_commands must forward platform_context to _execute_cmd."""
        adapter = _make_adapter()
        ctx = {"tenant_name": "acme", "kubeconfig": "/tmp/kubeconfig"}

        with patch.object(adapter, "_execute_cmd", return_value="ok") as mock_exec:
            messages = [
                {
                    "role": "user",
                    "content": "go",
                    "data": {"cmds": [{"command": "kubectl get pods", "execute": True}]},
                }
            ]
            adapter._process_approved_commands(messages, ctx)
            mock_exec.assert_called_once_with("kubectl get pods", files=None, context=ctx)

    def test_empty_context_is_forwarded(self):
        adapter = _make_adapter()
        with patch.object(adapter, "_execute_cmd", return_value="ok") as mock_exec:
            messages = [
                {
                    "role": "user",
                    "content": "go",
                    "data": {"cmds": [{"command": "ls", "execute": True}]},
                }
            ]
            adapter._process_approved_commands(messages, {})
            mock_exec.assert_called_once_with("ls", files=None, context={})
```

**Step 2: Run to confirm failure**

```bash
pytest tests/core/test_server_adapter.py -v
```

Expected: `FAILED — TypeError: _process_approved_commands() takes 2 positional arguments but 3 were given`

---

**Step 3: Update `_process_approved_commands` signature and callers**

In `dcaf/core/adapters/inbound/server_adapter.py`:

Change the `_process_approved_commands` signature from:
```python
def _process_approved_commands(
    self,
    messages_list: list[dict[str, Any]],
) -> list[ExecutedCommand]:
```

To:
```python
def _process_approved_commands(
    self,
    messages_list: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> list[ExecutedCommand]:
```

Inside the method body, change line 401 from:
```python
output = self._execute_cmd(command)
```
To:
```python
output = self._execute_cmd(command, files=None, context=context)
```

Update the two callers in `invoke()` (line 104) and `invoke_stream()` (line 177):
```python
# invoke()
executed_commands = self._process_approved_commands(messages_list, context)

# invoke_stream()
executed_commands = self._process_approved_commands(messages_list, context)
```

Also update `_execute_cmd` signature (even though impl stays the same for now):
```python
def _execute_cmd(
    self,
    command: str,
    files: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
) -> str:
```

**Step 4: Run tests**

```bash
pytest tests/core/test_server_adapter.py -v
```
Expected: `PASSED`

Also run:
```bash
pytest tests/core/test_unified_approvals.py -v
```

Expected: One test failure — `test_command_type_approval` at line 390 asserts:
```python
adapter._execute_cmd.assert_called_once_with("kubectl get pods")
```
Update that assertion to:
```python
adapter._execute_cmd.assert_called_once_with("kubectl get pods", files=None, context={})
```

Re-run: `pytest tests/core/test_unified_approvals.py -v` → all pass.

**Step 5: Run full suite**

```bash
pytest -v
```
Expected: All tests pass (excluding the 2 pre-existing AWS failures in `test_channel_routing.py`).

**Step 6: Commit**

```bash
git add dcaf/core/adapters/inbound/server_adapter.py \
        tests/core/test_server_adapter.py \
        tests/core/test_unified_approvals.py
git commit -m "feat(server-adapter): pass context to _process_approved_commands (gap 4)"
```

---

## Task 2: Pass `files` through to `_execute_cmd` with tempdir support (Gap 3)

**Why:** `data.cmds[].files` (e.g., Helm `values.yaml`) is currently silently dropped. The base implementation writes files to a temp directory, sets `cwd`, runs the command, and cleans up.

**Files:**
- Modify: `dcaf/core/adapters/inbound/server_adapter.py`
- Modify: `tests/core/test_server_adapter.py`

---

**Step 1: Add failing tests**

Append to `tests/core/test_server_adapter.py`:

```python
import os
import tempfile


class TestProcessApprovedCommandsPassesFiles:
    def test_files_extracted_and_passed_to_execute_cmd(self):
        """Files in data.cmds[].files must be forwarded to _execute_cmd."""
        adapter = _make_adapter()
        files = [{"file_path": "values.yaml", "file_content": "replicaCount: 2"}]

        with patch.object(adapter, "_execute_cmd", return_value="ok") as mock_exec:
            messages = [
                {
                    "role": "user",
                    "content": "go",
                    "data": {
                        "cmds": [
                            {
                                "command": "helm install myapp .",
                                "execute": True,
                                "files": files,
                            }
                        ]
                    },
                }
            ]
            adapter._process_approved_commands(messages, {})
            mock_exec.assert_called_once_with("helm install myapp .", files=files, context={})

    def test_no_files_passes_none(self):
        adapter = _make_adapter()
        with patch.object(adapter, "_execute_cmd", return_value="ok") as mock_exec:
            messages = [
                {
                    "role": "user",
                    "content": "go",
                    "data": {"cmds": [{"command": "ls", "execute": True}]},
                }
            ]
            adapter._process_approved_commands(messages, {})
            mock_exec.assert_called_once_with("ls", files=None, context={})


class TestExecuteCmdWithFiles:
    def test_files_are_written_to_tempdir(self):
        """When files are provided, _execute_cmd writes them before running the command."""
        adapter = _make_adapter()
        files = [{"file_path": "hello.txt", "file_content": "world"}]

        # Command that reads the file we wrote
        result = adapter._execute_cmd("cat hello.txt", files=files, context={})

        assert result.strip() == "world"

    def test_tempdir_is_cleaned_up_after_execution(self):
        """Temp directory must not persist after _execute_cmd returns."""
        adapter = _make_adapter()
        captured_dirs: list[str] = []

        original_mkdtemp = tempfile.mkdtemp

        def recording_mkdtemp(**kwargs):
            d = original_mkdtemp(**kwargs)
            captured_dirs.append(d)
            return d

        files = [{"file_path": "f.txt", "file_content": "x"}]
        with patch("tempfile.mkdtemp", side_effect=recording_mkdtemp):
            adapter._execute_cmd("echo done", files=files, context={})

        assert len(captured_dirs) == 1
        assert not os.path.exists(captured_dirs[0]), "Temp dir should be deleted"

    def test_tempdir_cleaned_up_on_error(self):
        """Temp directory is cleaned up even when the command raises."""
        adapter = _make_adapter()
        captured_dirs: list[str] = []

        original_mkdtemp = tempfile.mkdtemp

        def recording_mkdtemp(**kwargs):
            d = original_mkdtemp(**kwargs)
            captured_dirs.append(d)
            return d

        files = [{"file_path": "f.txt", "file_content": "x"}]
        with patch("tempfile.mkdtemp", side_effect=recording_mkdtemp):
            # subprocess.run won't raise, but simulate file-write failure
            with patch("builtins.open", side_effect=OSError("disk full")):
                result = adapter._execute_cmd("echo nope", files=files, context={})

        assert "Error" in result
        assert not os.path.exists(captured_dirs[0]), "Temp dir should be deleted on error"

    def test_no_files_runs_in_default_cwd(self):
        """Without files, command runs normally (no tempdir created)."""
        adapter = _make_adapter()
        with patch("tempfile.mkdtemp") as mock_mkdtemp:
            adapter._execute_cmd("echo hello", files=None, context={})
            mock_mkdtemp.assert_not_called()
```

**Step 2: Run to confirm failures**

```bash
pytest tests/core/test_server_adapter.py::TestProcessApprovedCommandsPassesFiles \
       tests/core/test_server_adapter.py::TestExecuteCmdWithFiles -v
```
Expected: Multiple `FAILED` — files not extracted, no tempdir logic.

---

**Step 3: Implement file extraction in `_process_approved_commands`**

In `_process_approved_commands`, change:
```python
command = cmd.get("command", "")
if cmd.get("execute", False):
    logger.info("Executing approved command: %s", command)
    output = self._execute_cmd(command, files=None, context=context)
```
To:
```python
command = cmd.get("command", "")
files = cmd.get("files") or None  # list[dict] | None
if cmd.get("execute", False):
    logger.info("Executing approved command: %s", command)
    output = self._execute_cmd(command, files=files, context=context)
```

**Step 4: Implement tempdir logic in `_execute_cmd`**

Add `import shutil` and `import tempfile` to the top of `server_adapter.py`. Then replace `_execute_cmd` with:

```python
def _execute_cmd(
    self,
    command: str,
    files: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """Execute a shell command, optionally writing files to a temp working directory."""
    work_dir: str | None = None
    try:
        if files:
            work_dir = tempfile.mkdtemp()
            for f in files:
                # Use basename only — never allow path traversal
                safe_name = os.path.basename(f.get("file_path", "file"))
                with open(os.path.join(work_dir, safe_name), "w") as fh:
                    fh.write(f.get("file_content", ""))

        result = subprocess.run(  # noqa: S602
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=work_dir,
        )
        output = result.stdout
        if result.stderr:
            output = (
                (output + f"\n\nErrors:\n{result.stderr}")
                if output
                else f"Errors:\n{result.stderr}"
            )
        return output or "Command executed successfully with no output."
    except Exception as e:
        logger.error("Error executing command: %s", e)
        return f"Error executing command: {e}"
    finally:
        if work_dir:
            shutil.rmtree(work_dir, ignore_errors=True)
```

Also add `import os` to the imports at the top of `server_adapter.py`.

**Step 5: Run tests**

```bash
pytest tests/core/test_server_adapter.py -v
pytest tests/ -v
```
Expected: All new tests pass. Full suite passes.

**Step 6: Commit**

```bash
git add dcaf/core/adapters/inbound/server_adapter.py \
        tests/core/test_server_adapter.py
git commit -m "feat(server-adapter): pass files to _execute_cmd with tempdir support (gap 3)"
```

---

## Task 3: Custom executor callback (Gap 2)

**Why:** Agents with domain requirements (kubeconfig injection, sandboxing, timeouts) can't override the subprocess path without subclassing. A constructor callback makes this trivially composable and testable.

**Files:**
- Modify: `dcaf/core/adapters/inbound/server_adapter.py`
- Modify: `tests/core/test_server_adapter.py`

---

**Step 1: Add failing tests**

Append to `tests/core/test_server_adapter.py`:

```python
class TestCustomExecutorCallback:
    def test_custom_executor_called_instead_of_subprocess(self):
        """When execute_cmd is provided, it is called instead of the built-in subprocess."""
        calls: list[tuple] = []

        def my_executor(
            command: str,
            files: list[dict] | None,
            context: dict | None,
        ) -> str:
            calls.append((command, files, context))
            return "custom output"

        adapter = _make_adapter(execute_cmd=my_executor)

        with patch("subprocess.run") as mock_run:
            result = adapter._execute_cmd("echo hello", files=None, context={"tenant": "acme"})

        assert result == "custom output"
        assert calls == [("echo hello", None, {"tenant": "acme"})]
        mock_run.assert_not_called()

    def test_custom_executor_receives_files(self):
        files = [{"file_path": "values.yaml", "file_content": "x: 1"}]

        def my_executor(command, files, context):
            return f"got {len(files)} file(s)"

        adapter = _make_adapter(execute_cmd=my_executor)
        result = adapter._execute_cmd("helm install .", files=files, context={})
        assert result == "got 1 file(s)"

    def test_no_executor_uses_default_subprocess(self):
        """Without a custom executor, the built-in subprocess path is used."""
        adapter = _make_adapter()  # no execute_cmd kwarg
        result = adapter._execute_cmd("echo default", files=None, context={})
        assert "default" in result

    def test_custom_executor_wires_through_process_approved_commands(self):
        """Custom executor is called end-to-end from _process_approved_commands."""
        calls: list[str] = []

        def my_executor(command, files, context):
            calls.append(command)
            return "custom result"

        adapter = _make_adapter(execute_cmd=my_executor)
        messages = [
            {
                "role": "user",
                "content": "go",
                "data": {"cmds": [{"command": "kubectl get pods", "execute": True}]},
            }
        ]
        results = adapter._process_approved_commands(messages, {})
        assert calls == ["kubectl get pods"]
        assert results[0].output == "custom result"
```

**Step 2: Run to confirm failure**

```bash
pytest tests/core/test_server_adapter.py::TestCustomExecutorCallback -v
```
Expected: `FAILED — TypeError: __init__() got an unexpected keyword argument 'execute_cmd'`

---

**Step 3: Add `execute_cmd` parameter to `__init__` and route in `_execute_cmd`**

At the top of `server_adapter.py`, add the type alias after the existing imports:

```python
from collections.abc import Callable

ExecutorFn = Callable[[str, list[dict[str, Any]] | None, dict[str, Any] | None], str]
```

Change `__init__`:
```python
def __init__(
    self,
    agent: Agent,
    execute_cmd: ExecutorFn | None = None,
) -> None:
    self.agent = agent
    self._cmd_executor = execute_cmd
```

At the top of `_execute_cmd`, add the routing:
```python
def _execute_cmd(
    self,
    command: str,
    files: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """Execute a shell command. If a custom executor was provided at construction,
    it is called instead of the built-in subprocess implementation."""
    if self._cmd_executor is not None:
        return self._cmd_executor(command, files, context)

    # ... rest of existing tempdir + subprocess logic unchanged
```

**Step 4: Run tests**

```bash
pytest tests/core/test_server_adapter.py -v
pytest tests/ -v
```
Expected: All pass.

**Step 5: Commit**

```bash
git add dcaf/core/adapters/inbound/server_adapter.py \
        tests/core/test_server_adapter.py
git commit -m "feat(server-adapter): add execute_cmd constructor callback for custom executors (gap 2)"
```

---

## Task 4: Emit `ApprovalsEvent` alongside `ToolCallsEvent` in `invoke_stream` (Gap 1)

**Why:** Clients currently receive `ToolCallsEvent` from `agent.run_stream()`. The `ApprovalsEvent` schema exists but is never emitted on this path. The k8s-agent team (and any unified-approval client) needs `ApprovalsEvent` with `type="tool_call"` for each pending tool call.

**Backward compat:** Both events are emitted for now. `ToolCallsEvent` and `CommandsEvent` are not removed.

**Files:**
- Modify: `dcaf/core/adapters/inbound/server_adapter.py`
- Modify: `tests/core/test_server_adapter.py`

---

**Step 1: Add failing tests**

Append to `tests/core/test_server_adapter.py`:

```python
import asyncio
from dcaf.core.schemas.events import (
    ApprovalsEvent,
    DoneEvent,
    TextDeltaEvent,
    ToolCallsEvent,
)
from dcaf.core.schemas.messages import ToolCall


def _make_agent_that_streams(*events):
    """Create a mock agent whose run_stream yields the given events."""
    mock_agent = MagicMock()
    mock_agent.tools = []

    async def fake_stream(*args, **kwargs):
        for event in events:
            yield event

    mock_agent.run_stream = MagicMock(side_effect=fake_stream)
    return mock_agent


class TestInvokeStreamEmitsApprovalsEvent:
    def test_tool_calls_event_produces_approvals_event(self):
        """When agent yields ToolCallsEvent, invoke_stream also yields ApprovalsEvent."""
        tool_call = ToolCall(
            id="tc-1",
            name="execute_terminal_cmd",
            input={"command": "kubectl get pods"},
            tool_description="Run a terminal command",
            input_description={},
            intent="List pods",
        )
        agent = _make_agent_that_streams(
            ToolCallsEvent(tool_calls=[tool_call]),
            DoneEvent(),
        )
        adapter = ServerAdapter(agent)

        async def collect():
            return [e async for e in adapter.invoke_stream({"messages": [{"role": "user", "content": "go"}]})]

        events = asyncio.get_event_loop().run_until_complete(collect())
        event_types = [e.type for e in events]

        assert "approvals" in event_types, "ApprovalsEvent must be emitted"
        assert "tool_calls" in event_types, "ToolCallsEvent must still be emitted (backward compat)"

    def test_approvals_event_contains_correct_approval(self):
        """The ApprovalsEvent approval must map ToolCall fields correctly."""
        tool_call = ToolCall(
            id="tc-42",
            name="delete_pod",
            input={"pod": "nginx"},
            tool_description="Delete a pod",
            input_description={},
            intent="Remove the pod",
        )
        agent = _make_agent_that_streams(
            ToolCallsEvent(tool_calls=[tool_call]),
            DoneEvent(),
        )
        adapter = ServerAdapter(agent)

        async def collect():
            return [e async for e in adapter.invoke_stream({"messages": [{"role": "user", "content": "go"}]})]

        events = asyncio.get_event_loop().run_until_complete(collect())
        approvals_events = [e for e in events if e.type == "approvals"]

        assert len(approvals_events) == 1
        approval = approvals_events[0].approvals[0]
        assert approval.id == "tc-42"
        assert approval.type == "tool_call"
        assert approval.name == "delete_pod"
        assert approval.input == {"pod": "nginx"}
        assert approval.description == "Delete a pod"
        assert approval.intent == "Remove the pod"

    def test_approvals_event_emitted_before_tool_calls_event(self):
        """ApprovalsEvent should appear before ToolCallsEvent in the stream."""
        tool_call = ToolCall(
            id="tc-1",
            name="list_pods",
            input={},
            tool_description="List pods",
            input_description={},
        )
        agent = _make_agent_that_streams(
            ToolCallsEvent(tool_calls=[tool_call]),
            DoneEvent(),
        )
        adapter = ServerAdapter(agent)

        async def collect():
            return [e async for e in adapter.invoke_stream({"messages": [{"role": "user", "content": "go"}]})]

        events = asyncio.get_event_loop().run_until_complete(collect())
        types = [e.type for e in events]

        approvals_idx = types.index("approvals")
        tool_calls_idx = types.index("tool_calls")
        assert approvals_idx < tool_calls_idx, "ApprovalsEvent must precede ToolCallsEvent"

    def test_no_tool_calls_event_no_approvals_event(self):
        """If the agent never yields ToolCallsEvent, no ApprovalsEvent is emitted."""
        agent = _make_agent_that_streams(
            TextDeltaEvent(text="hello"),
            DoneEvent(),
        )
        adapter = ServerAdapter(agent)

        async def collect():
            return [e async for e in adapter.invoke_stream({"messages": [{"role": "user", "content": "hi"}]})]

        events = asyncio.get_event_loop().run_until_complete(collect())
        assert not any(e.type == "approvals" for e in events)
```

**Step 2: Run to confirm failure**

```bash
pytest tests/core/test_server_adapter.py::TestInvokeStreamEmitsApprovalsEvent -v
```
Expected: `FAILED — assert "approvals" in [...]`

---

**Step 3: Update `invoke_stream` to translate `ToolCallsEvent`**

Add `ApprovalsEvent` and `Approval` to the imports in `server_adapter.py`:

```python
from ....schemas.events import (
    ApprovalsEvent,
    DoneEvent,
    ErrorEvent,
    ExecutedApprovalsEvent,
    ExecutedCommandsEvent,
    ExecutedToolCallsEvent,
    StreamEvent,
    ToolCallsEvent,
)
from ....schemas.messages import AgentMessage, Approval, ExecutedApproval, ExecutedCommand, ExecutedToolCall
```

In `invoke_stream`, change the inner streaming loop from:
```python
async for event in self.agent.run_stream(...):
    if isinstance(event, DoneEvent) and request_fields:
        event.meta_data["request_context"] = request_fields
    yield event
```

To:
```python
async for event in self.agent.run_stream(...):
    if isinstance(event, DoneEvent) and request_fields:
        event.meta_data["request_context"] = request_fields

    # Gap 1: translate ToolCallsEvent → ApprovalsEvent (emit first for unified clients)
    if isinstance(event, ToolCallsEvent) and event.tool_calls:
        approvals = [
            Approval(
                id=tc.id,
                type="tool_call",
                name=tc.name,
                input=tc.input,
                description=tc.tool_description,
                intent=tc.intent,
            )
            for tc in event.tool_calls
        ]
        yield ApprovalsEvent(approvals=approvals)

    yield event  # always emit original event for backward compat
```

**Step 4: Run tests**

```bash
pytest tests/core/test_server_adapter.py -v
pytest tests/ -v
```
Expected: All pass.

**Step 5: Commit**

```bash
git add dcaf/core/adapters/inbound/server_adapter.py \
        tests/core/test_server_adapter.py
git commit -m "feat(server-adapter): emit ApprovalsEvent from invoke_stream for each ToolCallsEvent (gap 1)"
```

---

## Task 5: Document `thread_id` convention and update docstrings (Gap 6)

**Why:** Gap 6 is already half-solved. After Task 1, `context` flows to all three processing methods. `thread_id` placed in `platform_context` (or at the top level of the request body via `_request_fields`) reaches any custom executor. No new API surface is needed — just documentation and a docstring update so the pattern is discoverable.

**Files:**
- Modify: `dcaf/core/adapters/inbound/server_adapter.py` (docstrings only)
- Modify: `tests/core/test_server_adapter.py` (one test to confirm thread_id flows)

---

**Step 1: Add a test confirming thread_id flows through context**

Append to `tests/core/test_server_adapter.py`:

```python
class TestThreadIdFlowsThroughContext:
    def test_thread_id_in_platform_context_reaches_custom_executor(self):
        """thread_id placed in platform_context flows to the custom executor via context."""
        received: list[dict] = []

        def my_executor(command, files, context):
            received.append(context or {})
            return "ok"

        adapter = _make_adapter(execute_cmd=my_executor)
        messages = [
            {
                "role": "user",
                "content": "go",
                "platform_context": {"thread_id": "thread-abc", "tenant_name": "acme"},
                "data": {"cmds": [{"command": "ls", "execute": True}]},
            }
        ]
        # _process_approved_commands needs the extracted context
        ctx = adapter._extract_platform_context(messages)
        adapter._process_approved_commands(messages, ctx)

        assert received[0].get("thread_id") == "thread-abc"
```

**Step 2: Run to confirm it passes immediately** (thread_id already works after Task 1)

```bash
pytest tests/core/test_server_adapter.py::TestThreadIdFlowsThroughContext -v
```
Expected: `PASSED` — no code change needed.

---

**Step 3: Update the class-level docstring**

In `ServerAdapter.__init__`, update the class docstring to include:

```python
"""
Adapts a Core Agent to work with the existing FastAPI server.

...

Args:
    agent: The Core Agent instance to wrap
    execute_cmd: Optional custom command executor. When provided, it replaces
        the built-in subprocess implementation. Signature::

            def my_executor(
                command: str,
                files: list[dict] | None,
                context: dict | None,
            ) -> str: ...

        Use this for kubeconfig injection, sandboxing, timeouts, or any
        domain-specific execution requirements.

        ``context`` contains the full platform_context for the request,
        including ``thread_id`` if the client sends it in ``platform_context``
        or at the top level of the request body.

Example — kubeconfig injection::

    def k8s_executor(command, files, context):
        env = os.environ.copy()
        env["KUBECONFIG"] = context.get("kubeconfig_path", "")
        thread_id = context.get("thread_id", "default")
        cwd = f"/data/{thread_id}"
        result = subprocess.run(command, shell=True, env=env, cwd=cwd, ...)
        return result.stdout

    adapter = ServerAdapter(agent, execute_cmd=k8s_executor)
"""
```

**Step 4: Commit**

```bash
git add dcaf/core/adapters/inbound/server_adapter.py \
        tests/core/test_server_adapter.py
git commit -m "docs(server-adapter): document thread_id convention and execute_cmd callback (gap 6)"
```

---

## Task 6: Final validation

**Step 1: Run linting and type check**

```bash
ruff check dcaf/core/adapters/inbound/server_adapter.py
ruff format --check dcaf/core/adapters/inbound/server_adapter.py
mypy dcaf/core/adapters/inbound/server_adapter.py
```

Fix any issues, then:

```bash
ruff check --fix dcaf/core/adapters/inbound/server_adapter.py
ruff format dcaf/core/adapters/inbound/server_adapter.py
```

**Step 2: Run import linter and code health**

```bash
lint-imports
python scripts/check_code_health.py
```

**Step 3: Run full test suite**

```bash
pytest -v
```
Expected: All tests pass (excluding the 2 pre-existing AWS failures).

**Step 4: Final commit (if any lint fixes were needed)**

```bash
git add dcaf/core/adapters/inbound/server_adapter.py
git commit -m "chore: lint and type fixes for server-adapter gap work"
```

---

## Summary of changes

| Task | Gap | Files changed | Tests added |
|------|-----|---------------|-------------|
| 1 | Gap 4 — context to `_process_approved_commands` | `server_adapter.py`, `test_unified_approvals.py` | 2 |
| 2 | Gap 3 — files + tempdir in `_execute_cmd` | `server_adapter.py` | 5 |
| 3 | Gap 2 — `execute_cmd` constructor callback | `server_adapter.py` | 4 |
| 4 | Gap 1 — `ApprovalsEvent` from `invoke_stream` | `server_adapter.py` | 4 |
| 5 | Gap 6 — `thread_id` convention + docs | `server_adapter.py` | 1 |
| 6 | — | lint/type cleanup | — |

**Gap 5 (per-thread working directory)** is intentionally omitted — it is fully covered by the `execute_cmd` callback from Gap 2. The custom executor owns the working directory, making a separate `working_dir` constructor parameter redundant.
