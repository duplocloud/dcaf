"""
Tests for AgnoResponseConverter, specifically the tool_approval_types registry feature.

These tests verify that:
1. AgnoResponseConverter accepts a tool_approval_types constructor argument
2. RunPausedEvent handling annotates ToolCallDTOs with the correct approval_type
3. Unknown tools default to "tool_call"
4. No-arg construction defaults to an empty registry
"""

from unittest.mock import MagicMock

# =============================================================================
# Tests: tool_approval_types constructor and RunPausedEvent handling
# =============================================================================


def test_response_converter_no_args_defaults_empty_registry():
    """AgnoResponseConverter() with no args must have an empty _tool_approval_types dict."""
    from dcaf.core.adapters.outbound.agno.response_converter import AgnoResponseConverter

    converter = AgnoResponseConverter()
    assert converter._tool_approval_types == {}


def test_response_converter_annotates_shell_tool_as_command():
    """RunPausedEvent for run_shell_command should produce a ToolCallDTO with approval_type='command'."""
    from dcaf.core.adapters.outbound.agno.adapter import TOOLKIT_TOOL_APPROVAL_TYPES
    from dcaf.core.adapters.outbound.agno.response_converter import AgnoResponseConverter

    converter = AgnoResponseConverter(tool_approval_types=TOOLKIT_TOOL_APPROVAL_TYPES)

    tool_exec = MagicMock()
    tool_exec.requires_confirmation = True
    tool_exec.tool_call_id = "tc-1"
    tool_exec.tool_name = "run_shell_command"
    tool_exec.tool_args = {"args": ["kubectl", "get", "pods"]}

    event = MagicMock()
    type(event).__name__ = "RunPausedEvent"
    event.tools = [tool_exec]

    result = converter.convert_stream_event(event)
    assert result is not None, "Expected a StreamEvent, got None"

    # tool_calls are serialised to dicts by StreamEvent.tool_calls_event
    tool_calls = result.data["tool_calls"]
    assert len(tool_calls) == 1
    tc = tool_calls[0]
    # Support both dict (serialised) and ToolCallDTO (object) access
    approval_type = tc["approval_type"] if isinstance(tc, dict) else tc.approval_type
    assert approval_type == "command", f"Expected 'command', got: {approval_type!r}"


def test_response_converter_defaults_unknown_tool_to_tool_call():
    """RunPausedEvent for an unregistered tool should default approval_type to 'tool_call'."""
    from dcaf.core.adapters.outbound.agno.response_converter import AgnoResponseConverter

    converter = AgnoResponseConverter(tool_approval_types={})

    tool_exec = MagicMock()
    tool_exec.requires_confirmation = True
    tool_exec.tool_call_id = "tc-2"
    tool_exec.tool_name = "some_custom_tool"
    tool_exec.tool_args = {}

    event = MagicMock()
    type(event).__name__ = "RunPausedEvent"
    event.tools = [tool_exec]

    result = converter.convert_stream_event(event)
    assert result is not None, "Expected a StreamEvent, got None"
    tc = result.data["tool_calls"][0]
    approval_type = tc["approval_type"] if isinstance(tc, dict) else tc.approval_type
    assert approval_type == "tool_call", f"Expected 'tool_call', got: {approval_type!r}"


def test_response_converter_tool_approval_types_stored_correctly():
    """Constructor must store the provided registry in _tool_approval_types."""
    from dcaf.core.adapters.outbound.agno.response_converter import AgnoResponseConverter

    registry = {"my_tool": "command", "other_tool": "tool_call"}
    converter = AgnoResponseConverter(tool_approval_types=registry)
    assert converter._tool_approval_types is registry
