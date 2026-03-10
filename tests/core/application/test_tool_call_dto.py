"""Tests for ToolCallDTO.approval_type field."""

from dcaf.core.application.dto.responses import ToolCallDTO


def test_tool_call_dto_approval_type_defaults_to_tool_call():
    dto = ToolCallDTO(id="1", name="foo", input={})
    assert dto.approval_type == "tool_call"


def test_tool_call_dto_approval_type_command():
    dto = ToolCallDTO(id="1", name="foo", input={}, approval_type="command")
    assert dto.approval_type == "command"


def test_tool_call_dto_approval_type_in_to_dict():
    dto = ToolCallDTO(id="1", name="foo", input={}, approval_type="command")
    d = dto.to_dict()
    assert d["approval_type"] == "command"


def test_tool_call_dto_from_dict_preserves_approval_type():
    d = {"id": "1", "name": "foo", "input": {}, "approval_type": "command"}
    dto = ToolCallDTO.from_dict(d)
    assert dto.approval_type == "command"


def test_tool_call_dto_from_dict_default_approval_type():
    # When approval_type not in dict, should default to "tool_call"
    d = {"id": "1", "name": "foo", "input": {}}
    dto = ToolCallDTO.from_dict(d)
    assert dto.approval_type == "tool_call"
