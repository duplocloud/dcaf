"""
End-to-end tests: approval_type flows from @tool through to ApprovalsEvent.

These tests verify the pipeline, not individual components. They mock at the
LLM boundary (Agno) and assert on emitted events.
"""
import pytest
from dcaf.core.tools import Tool, tool
from dcaf.core.application.dto.responses import ToolCallDTO
from dcaf.schemas.messages import ToolCall
from dcaf.schemas.events import ApprovalsEvent, CommandsEvent, ToolCallsEvent


# ── Component tests (no mocking needed) ──────────────────────────────────────


def test_tool_decorator_sets_approval_type():
    @tool(description="Run kubectl", approval_type="command", requires_approval=True)
    def run_kubectl(args: str) -> str:
        return args

    assert run_kubectl.approval_type == "command"


def test_tool_call_dto_round_trips_approval_type():
    dto = ToolCallDTO(id="1", name="run_kubectl", input={}, approval_type="command")
    d = dto.to_dict()
    restored = ToolCallDTO.from_dict(d)
    assert restored.approval_type == "command"


def test_schema_tool_call_carries_approval_type():
    tc = ToolCall(
        id="1",
        name="run_kubectl",
        input={"args": "get pods"},
        tool_description="Run kubectl",
        input_description={},
        approval_type="command",
    )
    assert tc.approval_type == "command"


def test_schema_tool_call_defaults_to_tool_call():
    tc = ToolCall(
        id="1",
        name="get_user",
        input={},
        tool_description="Get user",
        input_description={},
    )
    assert tc.approval_type == "tool_call"


# ── Registry tests ────────────────────────────────────────────────────────────


def test_shell_tool_mapped_to_command_in_registry():
    from dcaf.core.adapters.outbound.agno.adapter import TOOLKIT_TOOL_APPROVAL_TYPES
    assert TOOLKIT_TOOL_APPROVAL_TYPES["run_shell_command"] == "command"


def test_response_converter_uses_registry_for_shell_tool():
    from unittest.mock import MagicMock
    from dcaf.core.adapters.outbound.agno.response_converter import AgnoResponseConverter
    from dcaf.core.adapters.outbound.agno.adapter import TOOLKIT_TOOL_APPROVAL_TYPES

    converter = AgnoResponseConverter(tool_approval_types=dict(TOOLKIT_TOOL_APPROVAL_TYPES))

    tool_exec = MagicMock()
    tool_exec.requires_confirmation = True
    tool_exec.tool_call_id = "tc-shell"
    tool_exec.tool_name = "run_shell_command"
    tool_exec.tool_args = {"args": ["kubectl", "get", "pods"]}

    event = MagicMock()
    type(event).__name__ = "RunPausedEvent"
    event.tools = [tool_exec]

    result = converter.convert_stream_event(event)
    assert result is not None
    # data["tool_calls"] is a list of dicts (serialized via to_dict())
    assert result.data["tool_calls"][0]["approval_type"] == "command"


# ── Server adapter split tests ────────────────────────────────────────────────


def test_server_adapter_splits_command_to_commands_event():
    """ToolCallsEvent with approval_type='command' -> ApprovalsEvent + CommandsEvent."""
    tc = ToolCall(
        id="1", name="run_shell_command", input={},
        tool_description="", input_description={},
        approval_type="command",
    )
    tc_event = ToolCallsEvent(tool_calls=[tc])

    from unittest.mock import MagicMock
    from dcaf.core.adapters.inbound.server_adapter import ServerAdapter
    adapter = ServerAdapter.__new__(ServerAdapter)
    adapter.agent = MagicMock()

    result = adapter._translate_tool_calls_event(tc_event)
    event_types = [type(e).__name__ for e in result]

    assert "ApprovalsEvent" in event_types
    assert "CommandsEvent" in event_types
    assert "ToolCallsEvent" not in event_types


def test_server_adapter_splits_tool_call_to_tool_calls_event():
    """ToolCallsEvent with approval_type='tool_call' -> ApprovalsEvent + ToolCallsEvent."""
    tc = ToolCall(
        id="1", name="get_user", input={},
        tool_description="", input_description={},
        approval_type="tool_call",
    )
    tc_event = ToolCallsEvent(tool_calls=[tc])

    from unittest.mock import MagicMock
    from dcaf.core.adapters.inbound.server_adapter import ServerAdapter
    adapter = ServerAdapter.__new__(ServerAdapter)
    adapter.agent = MagicMock()

    result = adapter._translate_tool_calls_event(tc_event)
    event_types = [type(e).__name__ for e in result]

    assert "ApprovalsEvent" in event_types
    assert "ToolCallsEvent" in event_types
    assert "CommandsEvent" not in event_types
