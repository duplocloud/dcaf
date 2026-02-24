"""Tests for the unified approvals data models and processing."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from dcaf.core.adapters.inbound.server_adapter import ServerAdapter
from dcaf.core.schemas.events import (
    ApprovalsEvent as CoreApprovalsEvent,
)
from dcaf.core.schemas.events import (
    DoneEvent,
    TextDeltaEvent,
)
from dcaf.core.schemas.events import (
    ExecutedApprovalsEvent as CoreExecutedApprovalsEvent,
)
from dcaf.core.schemas.messages import (
    Approval as CoreApproval,
)
from dcaf.core.schemas.messages import (
    Data as CoreData,
)
from dcaf.core.schemas.messages import (
    ExecutedApproval as CoreExecutedApproval,
)
from dcaf.schemas.events import ApprovalsEvent, ExecutedApprovalsEvent
from dcaf.schemas.messages import Approval, Data, ExecutedApproval


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
        """Command-type approvals with type='command' route to subprocess, not tool registry."""
        agent, tool = _make_mock_agent_with_tool("execute_terminal_cmd", "NAME  READY\nnginx  1/1")
        adapter = ServerAdapter(agent)
        adapter._execute_cmd = MagicMock(return_value="NAME  READY\nnginx  1/1")

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
        adapter._execute_cmd.assert_called_once_with("kubectl get pods")
        tool.execute.assert_not_called()


def _make_mock_agent_for_invoke(tool_name: str, tool_result: str, llm_response: str):
    """Create a mock Agent that handles invoke() end-to-end."""
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
        agent, tool = _make_mock_agent_for_invoke("list_pods", "pod1\npod2", "Here are your pods.")
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
        agent, tool = _make_mock_agent_for_invoke("list_pods", "pod1", "Here are your pods.")
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
                                "type": "tool_call",
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
