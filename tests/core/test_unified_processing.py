"""Tests for the unified approval processing path in ServerAdapter.

Covers:
- _normalize_approvals: merges data.approvals[], data.cmds[], data.tool_calls[]
- _fan_out_executed: converts ExecutedApproval list to legacy types
- invoke/invoke_stream: single processing path end-to-end
"""

from unittest.mock import AsyncMock, MagicMock

from dcaf.core.adapters.inbound.server_adapter import ServerAdapter
from dcaf.core.schemas.events import DoneEvent, TextDeltaEvent
from dcaf.core.schemas.messages import ExecutedApproval


def _make_adapter(**kwargs):
    mock_agent = MagicMock()
    mock_agent.tools = []
    return ServerAdapter(mock_agent, **kwargs)


def _make_agent_with_tool(tool_name: str, tool_result: str):
    mock_tool = MagicMock()
    mock_tool.name = tool_name
    mock_tool.execute = MagicMock(return_value=tool_result)
    mock_agent = MagicMock()
    mock_agent.tools = [mock_tool]
    return mock_agent, mock_tool


# ---------------------------------------------------------------------------
# _normalize_approvals
# ---------------------------------------------------------------------------


class TestNormalizeApprovals:
    def test_empty_messages_returns_empty(self):
        adapter = _make_adapter()
        assert adapter._normalize_approvals([]) == []

    def test_no_data_field_returns_empty(self):
        adapter = _make_adapter()
        result = adapter._normalize_approvals([{"role": "user", "content": "hi"}])
        assert result == []

    def test_approvals_passed_through(self):
        adapter = _make_adapter()
        messages = [
            {
                "role": "user",
                "data": {
                    "approvals": [
                        {
                            "id": "a1",
                            "type": "tool_call",
                            "name": "foo",
                            "input": {},
                            "execute": True,
                        }
                    ]
                },
            }
        ]
        result = adapter._normalize_approvals(messages)
        assert len(result) == 1
        assert result[0]["id"] == "a1"
        assert result[0]["type"] == "tool_call"

    def test_cmds_normalized_to_approval_with_command_type(self):
        adapter = _make_adapter()
        messages = [
            {
                "role": "user",
                "data": {"cmds": [{"command": "kubectl get pods", "execute": True}]},
            }
        ]
        result = adapter._normalize_approvals(messages)
        assert len(result) == 1
        assert result[0]["type"] == "command"
        assert result[0]["input"]["command"] == "kubectl get pods"
        assert result[0]["execute"] is True

    def test_cmds_normalized_id_is_generated(self):
        adapter = _make_adapter()
        messages = [
            {
                "role": "user",
                "data": {"cmds": [{"command": "ls", "execute": True}]},
            }
        ]
        result = adapter._normalize_approvals(messages)
        assert result[0]["id"]  # non-empty generated UUID

    def test_cmds_files_included_in_normalized_input(self):
        adapter = _make_adapter()
        files = [{"file_path": "f.yaml", "file_content": "x: 1"}]
        messages = [
            {
                "role": "user",
                "data": {"cmds": [{"command": "helm install .", "execute": True, "files": files}]},
            }
        ]
        result = adapter._normalize_approvals(messages)
        assert result[0]["input"]["files"] == files

    def test_cmds_rejection_reason_preserved(self):
        adapter = _make_adapter()
        messages = [
            {
                "role": "user",
                "data": {
                    "cmds": [
                        {"command": "rm -rf /", "execute": False, "rejection_reason": "Dangerous"}
                    ]
                },
            }
        ]
        result = adapter._normalize_approvals(messages)
        assert result[0]["rejection_reason"] == "Dangerous"

    def test_tool_calls_normalized_to_approval_with_tool_call_type(self):
        adapter = _make_adapter()
        messages = [
            {
                "role": "user",
                "data": {
                    "tool_calls": [
                        {
                            "id": "tc-1",
                            "name": "list_pods",
                            "input": {"ns": "default"},
                            "execute": True,
                        }
                    ]
                },
            }
        ]
        result = adapter._normalize_approvals(messages)
        assert len(result) == 1
        assert result[0]["type"] == "tool_call"
        assert result[0]["name"] == "list_pods"
        assert result[0]["id"] == "tc-1"
        assert result[0]["input"] == {"ns": "default"}

    def test_tool_calls_without_id_gets_generated_id(self):
        adapter = _make_adapter()
        messages = [
            {
                "role": "user",
                "data": {"tool_calls": [{"name": "foo", "input": {}, "execute": True}]},
            }
        ]
        result = adapter._normalize_approvals(messages)
        assert result[0]["id"]  # non-empty

    def test_tool_call_already_in_approvals_is_deduplicated(self):
        """A tool_call whose id appears in data.approvals must not be processed twice."""
        adapter = _make_adapter()
        messages = [
            {
                "role": "user",
                "data": {
                    "approvals": [
                        {
                            "id": "tc-1",
                            "type": "tool_call",
                            "name": "foo",
                            "input": {},
                            "execute": True,
                        }
                    ],
                    "tool_calls": [{"id": "tc-1", "name": "foo", "input": {}, "execute": True}],
                },
            }
        ]
        result = adapter._normalize_approvals(messages)
        assert len(result) == 1  # not 2

    def test_all_three_sources_merged(self):
        adapter = _make_adapter()
        messages = [
            {
                "role": "user",
                "data": {
                    "approvals": [
                        {
                            "id": "a1",
                            "type": "tool_call",
                            "name": "foo",
                            "input": {},
                            "execute": True,
                        }
                    ],
                    "cmds": [{"command": "ls", "execute": True}],
                    "tool_calls": [{"id": "tc-2", "name": "bar", "input": {}, "execute": True}],
                },
            }
        ]
        result = adapter._normalize_approvals(messages)
        assert len(result) == 3

    def test_reads_from_latest_message_only(self):
        """Only the last message's data is used for current-turn approvals."""
        adapter = _make_adapter()
        messages = [
            {
                "role": "user",
                "data": {
                    "approvals": [
                        {
                            "id": "old",
                            "type": "tool_call",
                            "name": "old",
                            "input": {},
                            "execute": True,
                        }
                    ]
                },
            },
            {"role": "assistant", "content": "ok"},
            {
                "role": "user",
                "data": {
                    "approvals": [
                        {
                            "id": "new",
                            "type": "tool_call",
                            "name": "new",
                            "input": {},
                            "execute": True,
                        }
                    ]
                },
            },
        ]
        result = adapter._normalize_approvals(messages)
        assert len(result) == 1
        assert result[0]["id"] == "new"


# ---------------------------------------------------------------------------
# _fan_out_executed
# ---------------------------------------------------------------------------


class TestFanOutExecuted:
    def test_command_approval_produces_executed_command(self):
        adapter = _make_adapter()
        executed = [
            ExecutedApproval(
                id="x1",
                type="command",
                name="kubectl get pods",
                input={"command": "kubectl get pods"},
                output="pod1 Running",
            )
        ]
        cmds, tool_calls = adapter._fan_out_executed(executed)
        assert len(cmds) == 1
        assert cmds[0].command == "kubectl get pods"
        assert cmds[0].output == "pod1 Running"
        assert len(tool_calls) == 0

    def test_tool_call_approval_produces_executed_tool_call(self):
        adapter = _make_adapter()
        executed = [
            ExecutedApproval(
                id="tc-1",
                type="tool_call",
                name="list_pods",
                input={"ns": "default"},
                output="pod1",
            )
        ]
        cmds, tool_calls = adapter._fan_out_executed(executed)
        assert len(tool_calls) == 1
        assert tool_calls[0].id == "tc-1"
        assert tool_calls[0].name == "list_pods"
        assert tool_calls[0].input == {"ns": "default"}
        assert tool_calls[0].output == "pod1"
        assert len(cmds) == 0

    def test_mixed_approvals_split_correctly(self):
        adapter = _make_adapter()
        executed = [
            ExecutedApproval(
                id="x1", type="command", name="ls", input={"command": "ls -la"}, output="files"
            ),
            ExecutedApproval(id="tc-1", type="tool_call", name="foo", input={}, output="bar"),
        ]
        cmds, tool_calls = adapter._fan_out_executed(executed)
        assert len(cmds) == 1
        assert len(tool_calls) == 1

    def test_empty_list_returns_empty_lists(self):
        adapter = _make_adapter()
        cmds, tool_calls = adapter._fan_out_executed([])
        assert cmds == []
        assert tool_calls == []

    def test_command_uses_input_command_field(self):
        """ExecutedCommand.command must be input['command'], not the approval name."""
        adapter = _make_adapter()
        executed = [
            ExecutedApproval(
                id="x1",
                type="command",
                name="run_shell_command",
                input={"command": "kubectl get pods -n prod"},
                output="ok",
            )
        ]
        cmds, _ = adapter._fan_out_executed(executed)
        assert cmds[0].command == "kubectl get pods -n prod"


# ---------------------------------------------------------------------------
# End-to-end: invoke_stream unified path
# ---------------------------------------------------------------------------


def _make_streaming_agent(tool_name: str, tool_result: str, llm_text: str):
    mock_tool = MagicMock()
    mock_tool.name = tool_name
    mock_tool.execute = MagicMock(return_value=tool_result)

    mock_agent = MagicMock()
    mock_agent.tools = [mock_tool]

    async def fake_stream(*args, **kwargs):
        yield TextDeltaEvent(text=llm_text)
        yield DoneEvent()

    mock_agent.run_stream = MagicMock(side_effect=fake_stream)
    return mock_agent, mock_tool


class TestUnifiedPathInvokeStream:
    async def test_legacy_cmds_execute_via_unified_path(self):
        """data.cmds[] approval triggers execution and emits ExecutedApprovalsEvent."""
        adapter = _make_adapter()
        adapter._execute_cmd = MagicMock(return_value="pod1 Running")

        messages = {
            "messages": [
                {
                    "role": "user",
                    "content": "",
                    "data": {"cmds": [{"command": "kubectl get pods", "execute": True}]},
                }
            ]
        }

        events = [e async for e in adapter.invoke_stream(messages)]
        event_types = [e.type for e in events]

        assert "executed_approvals" in event_types
        exec_event = next(e for e in events if e.type == "executed_approvals")
        assert exec_event.executed_approvals[0].type == "command"
        assert exec_event.executed_approvals[0].output == "pod1 Running"

    async def test_legacy_cmds_also_emit_executed_commands_event(self):
        """data.cmds[] approval also emits legacy ExecutedCommandsEvent."""
        adapter = _make_adapter()
        adapter._execute_cmd = MagicMock(return_value="files listed")

        messages = {
            "messages": [
                {
                    "role": "user",
                    "content": "",
                    "data": {"cmds": [{"command": "ls -la", "execute": True}]},
                }
            ]
        }

        events = [e async for e in adapter.invoke_stream(messages)]
        event_types = [e.type for e in events]

        assert "executed_commands" in event_types
        ec_event = next(e for e in events if e.type == "executed_commands")
        assert ec_event.executed_cmds[0].command == "ls -la"
        assert ec_event.executed_cmds[0].output == "files listed"

    async def test_legacy_tool_calls_execute_via_unified_path(self):
        """data.tool_calls[] approval triggers execution and emits ExecutedApprovalsEvent."""
        agent, tool = _make_agent_with_tool("list_pods", "pod1")
        adapter = ServerAdapter(agent)

        messages = {
            "messages": [
                {
                    "role": "user",
                    "content": "",
                    "data": {
                        "tool_calls": [
                            {"id": "tc-1", "name": "list_pods", "input": {}, "execute": True}
                        ]
                    },
                }
            ]
        }

        events = [e async for e in adapter.invoke_stream(messages)]
        event_types = [e.type for e in events]

        assert "executed_approvals" in event_types
        tool.execute.assert_called_once()

    async def test_legacy_tool_calls_also_emit_executed_tool_calls_event(self):
        """data.tool_calls[] approval also emits legacy ExecutedToolCallsEvent."""
        agent, tool = _make_agent_with_tool("list_pods", "pod1")
        adapter = ServerAdapter(agent)

        messages = {
            "messages": [
                {
                    "role": "user",
                    "content": "",
                    "data": {
                        "tool_calls": [
                            {"id": "tc-1", "name": "list_pods", "input": {}, "execute": True}
                        ]
                    },
                }
            ]
        }

        events = [e async for e in adapter.invoke_stream(messages)]
        event_types = [e.type for e in events]

        assert "executed_tool_calls" in event_types

    async def test_mixed_approvals_and_cmds_all_execute(self):
        """data.approvals + data.cmds in same message all get executed."""
        adapter = _make_adapter()
        adapter._execute_cmd = MagicMock(return_value="cmd output")

        mock_tool = MagicMock()
        mock_tool.name = "list_pods"
        mock_tool.execute = MagicMock(return_value="pod output")
        adapter.agent.tools = [mock_tool]

        messages = {
            "messages": [
                {
                    "role": "user",
                    "content": "",
                    "data": {
                        "approvals": [
                            {
                                "id": "a1",
                                "type": "tool_call",
                                "name": "list_pods",
                                "input": {},
                                "execute": True,
                            }
                        ],
                        "cmds": [{"command": "ls", "execute": True}],
                    },
                }
            ]
        }

        events = [e async for e in adapter.invoke_stream(messages)]
        exec_event = next(e for e in events if e.type == "executed_approvals")
        assert len(exec_event.executed_approvals) == 2


class TestUnifiedPathInvoke:
    async def test_legacy_cmds_included_in_response_data(self):
        """invoke() response.data.executed_cmds populated from data.cmds[] approval."""
        mock_response = MagicMock()
        mock_response.needs_approval = False
        mock_response.to_message.return_value = MagicMock(
            content="done",
            data=MagicMock(
                executed_approvals=[],
                executed_tool_calls=[],
                executed_cmds=[],
            ),
        )
        mock_agent = MagicMock()
        mock_agent.tools = []
        mock_agent.run = AsyncMock(return_value=mock_response)
        adapter = ServerAdapter(mock_agent)
        adapter._execute_cmd = MagicMock(return_value="ls output")

        messages = {
            "messages": [
                {
                    "role": "user",
                    "content": "",
                    "data": {"cmds": [{"command": "ls", "execute": True}]},
                }
            ]
        }

        result = await adapter.invoke(messages)
        assert len(result.data.executed_cmds) == 1
        assert result.data.executed_cmds[0].command == "ls"

    async def test_legacy_tool_calls_included_in_response_data(self):
        """invoke() response.data.executed_tool_calls populated from data.tool_calls[]."""
        mock_response = MagicMock()
        mock_response.needs_approval = False
        mock_response.to_message.return_value = MagicMock(
            content="done",
            data=MagicMock(
                executed_approvals=[],
                executed_tool_calls=[],
                executed_cmds=[],
            ),
        )
        agent, tool = _make_agent_with_tool("foo", "bar")
        agent.run = AsyncMock(return_value=mock_response)
        adapter = ServerAdapter(agent)

        messages = {
            "messages": [
                {
                    "role": "user",
                    "content": "",
                    "data": {
                        "tool_calls": [{"id": "tc-1", "name": "foo", "input": {}, "execute": True}]
                    },
                }
            ]
        }

        result = await adapter.invoke(messages)
        assert len(result.data.executed_tool_calls) == 1
        assert result.data.executed_tool_calls[0].name == "foo"
