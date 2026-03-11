"""Tests for the full data.cmds[] / executed_cmds workflow.

Covers:
- CommandsEvent contains actual command string (not tool name)
- CommandsEvent includes files from tool input
- User-sent executed_cmds are injected into LLM context
- Command rejection reason is recorded in ExecutedCommand
- Multi-turn history executed_cmds all injected
"""

from unittest.mock import MagicMock

from dcaf.core.adapters.inbound.server_adapter import ServerAdapter
from dcaf.core.schemas.events import DoneEvent, ToolCallsEvent
from dcaf.core.schemas.messages import ToolCall


def _make_adapter(**kwargs):
    mock_agent = MagicMock()
    mock_agent.tools = []
    return ServerAdapter(mock_agent, **kwargs)


def _make_command_tool_call(
    *,
    id: str = "tc-1",
    name: str = "run_shell_command",
    command: str = "kubectl get pods",
    files: list | None = None,
    intent: str | None = None,
) -> ToolCall:
    input_data: dict = {"command": command}
    if files is not None:
        input_data["files"] = files
    return ToolCall(
        id=id,
        name=name,
        input=input_data,
        tool_description="Run a shell command",
        input_description={},
        approval_type="command",
        intent=intent,
    )


# ---------------------------------------------------------------------------
# CommandsEvent data structure correctness
# ---------------------------------------------------------------------------


class TestCommandsEventContainsActualCommand:
    def test_commands_event_command_field_is_actual_command_string(self):
        """CommandsEvent.commands[].command must be the shell command, not the tool name."""
        adapter = _make_adapter()
        tool_call = _make_command_tool_call(
            name="run_shell_command", command="kubectl get pods -n default"
        )
        event = ToolCallsEvent(tool_calls=[tool_call])

        results = adapter._translate_tool_calls_event(event)
        commands_events = [e for e in results if e.type == "commands"]

        assert len(commands_events) == 1
        cmd = commands_events[0].commands[0]
        assert cmd.command == "kubectl get pods -n default", (
            f"Expected actual command string, got '{cmd.command}' (tool name instead?)"
        )

    def test_commands_event_command_field_is_not_tool_name(self):
        """Command.command must never equal the tool function name."""
        adapter = _make_adapter()
        tool_call = _make_command_tool_call(name="run_shell_command", command="ls -la /tmp")
        event = ToolCallsEvent(tool_calls=[tool_call])

        results = adapter._translate_tool_calls_event(event)
        commands_events = [e for e in results if e.type == "commands"]

        cmd = commands_events[0].commands[0]
        assert cmd.command != "run_shell_command", (
            "Command.command must be the shell command, not the Python tool name"
        )

    def test_commands_event_execute_defaults_to_false(self):
        """CommandsEvent proposals must have execute=False (pending approval)."""
        adapter = _make_adapter()
        tool_call = _make_command_tool_call(command="helm list")
        event = ToolCallsEvent(tool_calls=[tool_call])

        results = adapter._translate_tool_calls_event(event)
        commands_events = [e for e in results if e.type == "commands"]

        cmd = commands_events[0].commands[0]
        assert cmd.execute is False, "Proposed command must have execute=False"


class TestCommandsEventIncludesFiles:
    def test_files_from_tool_input_are_in_commands_event(self):
        """CommandsEvent.commands[].files must include files from tool input."""
        adapter = _make_adapter()
        files = [{"file_path": "values.yaml", "file_content": "replicaCount: 3"}]
        tool_call = _make_command_tool_call(command="helm upgrade myapp .", files=files)
        event = ToolCallsEvent(tool_calls=[tool_call])

        results = adapter._translate_tool_calls_event(event)
        commands_events = [e for e in results if e.type == "commands"]

        cmd = commands_events[0].commands[0]
        assert cmd.files is not None, "Command must include files from tool input"
        assert len(cmd.files) == 1
        assert cmd.files[0].file_path == "values.yaml"
        assert cmd.files[0].file_content == "replicaCount: 3"

    def test_no_files_in_input_means_none_in_command(self):
        """When tool input has no files, Command.files should be None."""
        adapter = _make_adapter()
        tool_call = _make_command_tool_call(command="ls -la")
        event = ToolCallsEvent(tool_calls=[tool_call])

        results = adapter._translate_tool_calls_event(event)
        commands_events = [e for e in results if e.type == "commands"]

        cmd = commands_events[0].commands[0]
        assert cmd.files is None


# ---------------------------------------------------------------------------
# User-sent executed_cmds injected into LLM context
# ---------------------------------------------------------------------------


class TestUserExecutedCmdsInjectedIntoContext:
    def test_user_executed_cmds_appended_to_message_content(self):
        """data.executed_cmds from user turn must be injected into LLM message content."""
        adapter = _make_adapter()
        messages = [
            {
                "role": "user",
                "content": "I ran my own commands, analyze them",
                "data": {
                    "executed_cmds": [
                        {
                            "command": "kubectl get pods",
                            "output": "NAME   READY   STATUS\napp    1/1     Running",
                        }
                    ]
                },
            }
        ]

        core_messages = adapter._convert_messages(messages)

        assert len(core_messages) == 1
        content = core_messages[0]["content"]
        assert "kubectl get pods" in content
        assert "NAME   READY   STATUS" in content

    def test_multiple_user_executed_cmds_all_injected(self):
        """All executed_cmds entries must appear in LLM context."""
        adapter = _make_adapter()
        messages = [
            {
                "role": "user",
                "content": "check these",
                "data": {
                    "executed_cmds": [
                        {"command": "kubectl get pods", "output": "app Running"},
                        {"command": "kubectl get services", "output": "svc ClusterIP"},
                    ]
                },
            }
        ]

        core_messages = adapter._convert_messages(messages)
        content = core_messages[0]["content"]

        assert "kubectl get pods" in content
        assert "app Running" in content
        assert "kubectl get services" in content
        assert "svc ClusterIP" in content

    def test_user_executed_cmds_in_earlier_turn_also_injected(self):
        """executed_cmds on an earlier user turn must be preserved in history."""
        adapter = _make_adapter()
        messages = [
            {
                "role": "user",
                "content": "first turn",
                "data": {
                    "executed_cmds": [{"command": "kubectl get nodes", "output": "node1 Ready"}]
                },
            },
            {"role": "assistant", "content": "ok"},
            {
                "role": "user",
                "content": "second turn",
                "data": {},
            },
        ]

        core_messages = adapter._convert_messages(messages)

        # First user message must include the executed cmd
        assert "kubectl get nodes" in core_messages[0]["content"]
        assert "node1 Ready" in core_messages[0]["content"]


# ---------------------------------------------------------------------------
# Command rejection reason
# ---------------------------------------------------------------------------


class TestCommandRejectionReason:
    def _process_cmds(self, adapter, messages, ctx=None):
        """Helper: normalize + process approvals, fan out to ExecutedCommand list."""
        normalized = adapter._normalize_approvals(messages)
        executed_approvals = adapter._process_approvals(normalized, ctx or {})
        cmds, _ = adapter._fan_out_executed(executed_approvals)
        return cmds

    def test_rejected_command_records_rejection_reason(self):
        """Rejected command with rejection_reason must be recorded with that reason."""
        adapter = _make_adapter()
        messages = [
            {
                "role": "user",
                "content": "",
                "data": {
                    "cmds": [
                        {
                            "command": "rm -rf /",
                            "execute": False,
                            "rejection_reason": "Too dangerous",
                        }
                    ]
                },
            }
        ]

        results = self._process_cmds(adapter, messages)

        assert len(results) == 1
        assert results[0].command == "rm -rf /"
        assert "Too dangerous" in results[0].output

    def test_approved_command_executes_and_not_rejected(self):
        """Approved command must be executed, not treated as rejected."""
        adapter = _make_adapter()
        messages = [
            {
                "role": "user",
                "content": "",
                "data": {"cmds": [{"command": "echo hello", "execute": True}]},
            }
        ]

        results = self._process_cmds(adapter, messages)

        assert len(results) == 1
        assert "hello" in results[0].output
        assert "Rejected" not in results[0].output

    def test_unapproved_command_without_reason_is_skipped(self):
        """Command with execute=False and no rejection_reason must be ignored."""
        adapter = _make_adapter()
        messages = [
            {
                "role": "user",
                "content": "",
                "data": {"cmds": [{"command": "ls", "execute": False}]},
            }
        ]

        results = self._process_cmds(adapter, messages)

        assert len(results) == 0


# ---------------------------------------------------------------------------
# CommandsEvent emitted in invoke_stream for command-type tool calls
# ---------------------------------------------------------------------------


def _make_agent_that_streams(*events):
    mock_agent = MagicMock()
    mock_agent.tools = []

    async def fake_stream(*args, **kwargs):
        for event in events:
            yield event

    mock_agent.run_stream = MagicMock(side_effect=fake_stream)
    return mock_agent


class TestCommandsEventEmittedInStream:
    async def test_command_type_tool_call_emits_commands_event(self):
        """invoke_stream must emit CommandsEvent for command-type tool calls."""
        tool_call = _make_command_tool_call(command="kubectl get pods")
        agent = _make_agent_that_streams(
            ToolCallsEvent(tool_calls=[tool_call]),
            DoneEvent(),
        )
        adapter = ServerAdapter(agent)

        events = [
            e
            async for e in adapter.invoke_stream(
                {"messages": [{"role": "user", "content": "check pods"}]}
            )
        ]

        assert any(e.type == "commands" for e in events), "CommandsEvent must be emitted"

    async def test_commands_event_has_correct_command_string(self):
        """CommandsEvent in stream must contain actual shell command, not tool name."""
        tool_call = _make_command_tool_call(
            name="run_shell_command", command="kubectl get pods -n prod"
        )
        agent = _make_agent_that_streams(
            ToolCallsEvent(tool_calls=[tool_call]),
            DoneEvent(),
        )
        adapter = ServerAdapter(agent)

        events = [
            e
            async for e in adapter.invoke_stream(
                {"messages": [{"role": "user", "content": "check pods"}]}
            )
        ]

        commands_events = [e for e in events if e.type == "commands"]
        assert len(commands_events) == 1
        assert commands_events[0].commands[0].command == "kubectl get pods -n prod"

    async def test_approvals_event_also_emitted_for_command_type(self):
        """ApprovalsEvent must also be emitted alongside CommandsEvent."""
        tool_call = _make_command_tool_call(command="helm list")
        agent = _make_agent_that_streams(
            ToolCallsEvent(tool_calls=[tool_call]),
            DoneEvent(),
        )
        adapter = ServerAdapter(agent)

        events = [
            e
            async for e in adapter.invoke_stream(
                {"messages": [{"role": "user", "content": "list charts"}]}
            )
        ]

        assert any(e.type == "approvals" for e in events)
        assert any(e.type == "commands" for e in events)
