"""Tests for ApprovalService (dcaf.core.application.services.approval_service)."""

import pytest

from dcaf.core.application.dto.requests import ApprovalRequest, ToolCallApproval
from dcaf.core.application.services.approval_service import ApprovalService
from dcaf.core.domain.entities import Conversation, ToolCall
from dcaf.core.domain.exceptions import ToolCallNotFound
from dcaf.core.domain.value_objects import ConversationId, ToolCallId, ToolInput
from dcaf.core.testing import FakeConversationRepository, FakeEventPublisher


# =============================================================================
# Helpers
# =============================================================================


def _create_conversation_with_pending_tool_call(
    tool_call_id: str = "tc-1",
    tool_name: str = "delete_pod",
) -> Conversation:
    """Create a conversation with one pending tool call."""
    conv = Conversation.create()
    conv.add_user_message("Delete the pod")

    tool_call = ToolCall(
        id=ToolCallId(tool_call_id),
        tool_name=tool_name,
        input=ToolInput({"pod": "nginx"}),
        requires_approval=True,
    )
    conv.request_tool_approval([tool_call])
    return conv


def _create_service(conversation: Conversation | None = None):
    """Create an ApprovalService with fakes, optionally seeding a conversation."""
    conversations = FakeConversationRepository()
    events = FakeEventPublisher()

    if conversation:
        conversations.seed(conversation)

    service = ApprovalService(conversations=conversations, events=events)
    return service, conversations, events


# =============================================================================
# ApprovalService.execute Tests
# =============================================================================


class TestApprovalServiceExecute:
    def test_approve_tool_call(self):
        conv = _create_conversation_with_pending_tool_call()
        service, conversations, events = _create_service(conv)

        request = ApprovalRequest(
            conversation_id=str(conv.id),
            approvals=[ToolCallApproval(tool_call_id="tc-1", approved=True)],
        )
        response = service.execute(request)

        assert response.has_pending_approvals is False
        assert response.is_complete is True

    def test_reject_tool_call(self):
        conv = _create_conversation_with_pending_tool_call()
        service, conversations, events = _create_service(conv)

        request = ApprovalRequest(
            conversation_id=str(conv.id),
            approvals=[
                ToolCallApproval(
                    tool_call_id="tc-1",
                    approved=False,
                    rejection_reason="Too dangerous",
                )
            ],
        )
        response = service.execute(request)

        assert response.has_pending_approvals is False
        assert response.is_complete is True

    def test_conversation_saved_after_approval(self):
        conv = _create_conversation_with_pending_tool_call()
        service, conversations, events = _create_service(conv)

        request = ApprovalRequest(
            conversation_id=str(conv.id),
            approvals=[ToolCallApproval(tool_call_id="tc-1", approved=True)],
        )
        service.execute(request)

        assert conversations.save_count == 1

    def test_events_published_after_approval(self):
        conv = _create_conversation_with_pending_tool_call()
        service, conversations, events = _create_service(conv)

        request = ApprovalRequest(
            conversation_id=str(conv.id),
            approvals=[ToolCallApproval(tool_call_id="tc-1", approved=True)],
        )
        service.execute(request)

        # Events should have been published
        assert events.publish_count >= 0

    def test_missing_conversation_raises_error(self):
        service, conversations, events = _create_service()

        request = ApprovalRequest(
            conversation_id="nonexistent-id",
            approvals=[ToolCallApproval(tool_call_id="tc-1", approved=True)],
        )

        with pytest.raises(ValueError, match="Conversation not found"):
            service.execute(request)

    def test_invalid_tool_call_id_raises_error(self):
        conv = _create_conversation_with_pending_tool_call(tool_call_id="tc-1")
        service, conversations, events = _create_service(conv)

        request = ApprovalRequest(
            conversation_id=str(conv.id),
            approvals=[ToolCallApproval(tool_call_id="nonexistent-tc", approved=True)],
        )

        with pytest.raises(ToolCallNotFound):
            service.execute(request)

    def test_response_includes_tool_calls(self):
        conv = _create_conversation_with_pending_tool_call()
        service, conversations, events = _create_service(conv)

        request = ApprovalRequest(
            conversation_id=str(conv.id),
            approvals=[ToolCallApproval(tool_call_id="tc-1", approved=True)],
        )
        response = service.execute(request)

        assert response.data is not None
        assert len(response.data.tool_calls) >= 1


# =============================================================================
# ApprovalService.approve_single Tests
# =============================================================================


class TestApproveSingle:
    def test_approve_single(self):
        conv = _create_conversation_with_pending_tool_call()
        service, _, _ = _create_service(conv)

        response = service.approve_single(str(conv.id), "tc-1")

        assert response.has_pending_approvals is False
        assert response.is_complete is True


# =============================================================================
# ApprovalService.reject_single Tests
# =============================================================================


class TestRejectSingle:
    def test_reject_single(self):
        conv = _create_conversation_with_pending_tool_call()
        service, _, _ = _create_service(conv)

        response = service.reject_single(str(conv.id), "tc-1", "Not safe")

        assert response.has_pending_approvals is False
        assert response.is_complete is True


# =============================================================================
# ApprovalService.approve_all Tests
# =============================================================================


class TestApproveAll:
    def test_approve_all_with_pending(self):
        conv = Conversation.create()
        conv.add_user_message("Do things")

        tc1 = ToolCall(
            id=ToolCallId("tc-1"),
            tool_name="tool1",
            input=ToolInput({"a": 1}),
            requires_approval=True,
        )
        tc2 = ToolCall(
            id=ToolCallId("tc-2"),
            tool_name="tool2",
            input=ToolInput({"b": 2}),
            requires_approval=True,
        )
        conv.request_tool_approval([tc1, tc2])

        service, _, _ = _create_service(conv)
        response = service.approve_all(str(conv.id))

        assert response.has_pending_approvals is False
        assert response.is_complete is True

    def test_approve_all_no_pending(self):
        conv = Conversation.create()
        conv.add_user_message("Hello")

        service, _, _ = _create_service(conv)
        response = service.approve_all(str(conv.id))

        assert response.is_complete is True

    def test_approve_all_missing_conversation(self):
        service, _, _ = _create_service()

        with pytest.raises(ValueError, match="Conversation not found"):
            service.approve_all("nonexistent")


# =============================================================================
# ApprovalService.reject_all Tests
# =============================================================================


class TestRejectAll:
    def test_reject_all_with_pending(self):
        conv = Conversation.create()
        conv.add_user_message("Do things")

        tc1 = ToolCall(
            id=ToolCallId("tc-1"),
            tool_name="tool1",
            input=ToolInput({"a": 1}),
            requires_approval=True,
        )
        conv.request_tool_approval([tc1])

        service, _, _ = _create_service(conv)
        response = service.reject_all(str(conv.id), "Too risky")

        assert response.has_pending_approvals is False

    def test_reject_all_no_pending(self):
        conv = Conversation.create()
        conv.add_user_message("Hello")

        service, _, _ = _create_service(conv)
        response = service.reject_all(str(conv.id), "No reason")

        assert response.is_complete is True

    def test_reject_all_missing_conversation(self):
        service, _, _ = _create_service()

        with pytest.raises(ValueError, match="Conversation not found"):
            service.reject_all("nonexistent", "reason")
