"""Tests for ServerAdapter — gap fixes for command-executing agents."""

import os
import tempfile
from unittest.mock import MagicMock, patch

from dcaf.core.adapters.inbound.server_adapter import ServerAdapter
from dcaf.core.schemas.events import DoneEvent, TextDeltaEvent, ToolCallsEvent
from dcaf.core.schemas.messages import ToolCall


def _make_adapter(**kwargs):
    """Create a ServerAdapter with a minimal mock agent."""
    mock_agent = MagicMock()
    mock_agent.tools = []
    return ServerAdapter(mock_agent, **kwargs)


class TestProcessApprovedCommandsReceivesContext:
    def test_context_is_passed_to_execute_cmd(self):
        """_process_approved_commands must forward platform_context to _execute_cmd."""
        adapter = _make_adapter()
        ctx = {"tenant_name": "acme", "kubeconfig": "/home/user/.kube/config"}

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
        """Temp directory is cleaned up even when file writing raises."""
        adapter = _make_adapter()
        captured_dirs: list[str] = []

        original_mkdtemp = tempfile.mkdtemp

        def recording_mkdtemp(**kwargs):
            d = original_mkdtemp(**kwargs)
            captured_dirs.append(d)
            return d

        files = [{"file_path": "f.txt", "file_content": "x"}]
        with (
            patch("tempfile.mkdtemp", side_effect=recording_mkdtemp),
            # Simulate file-write failure
            patch("builtins.open", side_effect=OSError("disk full")),
        ):
            result = adapter._execute_cmd("echo nope", files=files, context={})

        assert "Error" in result
        assert not os.path.exists(captured_dirs[0]), "Temp dir should be deleted on error"

    def test_no_files_runs_in_default_cwd(self):
        """Without files, command runs normally (no tempdir created)."""
        adapter = _make_adapter()
        with patch("tempfile.mkdtemp") as mock_mkdtemp:
            adapter._execute_cmd("echo hello", files=None, context={})
            mock_mkdtemp.assert_not_called()


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
    async def test_tool_calls_event_produces_approvals_event(self):
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

        events = [e async for e in adapter.invoke_stream({"messages": [{"role": "user", "content": "go"}]})]
        event_types = [e.type for e in events]

        assert "approvals" in event_types, "ApprovalsEvent must be emitted"
        assert "tool_calls" in event_types, "ToolCallsEvent must still be emitted (backward compat)"

    async def test_approvals_event_contains_correct_approval(self):
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

        events = [e async for e in adapter.invoke_stream({"messages": [{"role": "user", "content": "go"}]})]
        approvals_events = [e for e in events if e.type == "approvals"]

        assert len(approvals_events) == 1
        approval = approvals_events[0].approvals[0]
        assert approval.id == "tc-42"
        assert approval.type == "tool_call"
        assert approval.name == "delete_pod"
        assert approval.input == {"pod": "nginx"}
        assert approval.description == "Delete a pod"
        assert approval.intent == "Remove the pod"

    async def test_approvals_event_emitted_before_tool_calls_event(self):
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

        events = [e async for e in adapter.invoke_stream({"messages": [{"role": "user", "content": "go"}]})]
        types = [e.type for e in events]

        approvals_idx = types.index("approvals")
        tool_calls_idx = types.index("tool_calls")
        assert approvals_idx < tool_calls_idx, "ApprovalsEvent must precede ToolCallsEvent"

    async def test_no_tool_calls_event_no_approvals_event(self):
        """If the agent never yields ToolCallsEvent, no ApprovalsEvent is emitted."""
        agent = _make_agent_that_streams(
            TextDeltaEvent(text="hello"),
            DoneEvent(),
        )
        adapter = ServerAdapter(agent)

        events = [e async for e in adapter.invoke_stream({"messages": [{"role": "user", "content": "hi"}]})]
        assert not any(e.type == "approvals" for e in events)
