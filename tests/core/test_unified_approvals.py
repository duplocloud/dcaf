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


from dcaf.schemas.events import ApprovalsEvent, ExecutedApprovalsEvent
from dcaf.schemas.messages import Approval, ExecutedApproval


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


from dcaf.core.schemas.events import (
    ApprovalsEvent as CoreApprovalsEvent,
    ExecutedApprovalsEvent as CoreExecutedApprovalsEvent,
)
from dcaf.core.schemas.messages import (
    Approval as CoreApproval,
    ExecutedApproval as CoreExecutedApproval,
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
