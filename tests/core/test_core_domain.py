"""Tests for the core domain layer."""

import pytest

from dcaf.core.domain.entities import (
    Conversation,
    Message,
    MessageRole,
    ToolCall,
    ToolCallStatus,
)
from dcaf.core.domain.exceptions import (
    ConversationBlocked,
    InvalidStateTransition,
    ToolCallNotFound,
)
from dcaf.core.domain.value_objects import (
    PlatformContext,
    ToolCallId,
    ToolInput,
)

# =============================================================================
# Value Object Tests
# =============================================================================


class TestToolCallId:
    """Tests for ToolCallId value object."""

    def test_create_with_valid_value(self):
        id = ToolCallId("tc-123")
        assert str(id) == "tc-123"

    def test_generate_creates_unique_ids(self):
        id1 = ToolCallId.generate()
        id2 = ToolCallId.generate()
        assert id1 != id2

    def test_empty_value_raises_error(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            ToolCallId("")

    def test_equality(self):
        id1 = ToolCallId("tc-123")
        id2 = ToolCallId("tc-123")
        assert id1 == id2


class TestToolInput:
    """Tests for ToolInput value object."""

    def test_create_with_parameters(self):
        input = ToolInput({"command": "get pods", "namespace": "default"})
        assert input.parameters == {"command": "get pods", "namespace": "default"}

    def test_get_parameter(self):
        input = ToolInput({"key": "value"})
        assert input.get("key") == "value"
        assert input.get("missing", "default") == "default"

    def test_contains(self):
        input = ToolInput({"key": "value"})
        assert "key" in input
        assert "missing" not in input

    def test_empty_input(self):
        input = ToolInput.empty()
        assert input.parameters == {}


class TestPlatformContext:
    """Tests for PlatformContext value object."""

    def test_create_with_values(self):
        context = PlatformContext(
            tenant_name="my-tenant",
            k8s_namespace="production",
        )
        assert context.tenant_name == "my-tenant"
        assert context.k8s_namespace == "production"

    def test_to_dict(self):
        context = PlatformContext(tenant_name="test")
        d = context.to_dict()
        assert d["tenant_name"] == "test"

    def test_empty_context(self):
        context = PlatformContext.empty()
        assert context.tenant_name is None


# =============================================================================
# Entity Tests
# =============================================================================


class TestToolCall:
    """Tests for ToolCall entity."""

    def test_create_pending(self):
        tc = ToolCall(
            id=ToolCallId("tc-1"),
            tool_name="kubectl",
            input=ToolInput({"command": "get pods"}),
        )
        assert tc.is_pending
        assert tc.status == ToolCallStatus.PENDING

    def test_approve_transitions_state(self):
        tc = ToolCall(
            id=ToolCallId("tc-1"),
            tool_name="kubectl",
            input=ToolInput({}),
        )
        tc.approve()
        assert tc.is_approved
        assert tc.status == ToolCallStatus.APPROVED

    def test_reject_transitions_state(self):
        tc = ToolCall(
            id=ToolCallId("tc-1"),
            tool_name="kubectl",
            input=ToolInput({}),
        )
        tc.reject("Too risky")
        assert tc.is_rejected
        assert tc.rejection_reason == "Too risky"

    def test_complete_lifecycle(self):
        tc = ToolCall(
            id=ToolCallId("tc-1"),
            tool_name="kubectl",
            input=ToolInput({}),
        )
        tc.approve()
        tc.start_execution()
        tc.complete("Success!")
        assert tc.is_completed
        assert tc.result == "Success!"

    def test_cannot_approve_twice(self):
        tc = ToolCall(
            id=ToolCallId("tc-1"),
            tool_name="kubectl",
            input=ToolInput({}),
        )
        tc.approve()
        with pytest.raises(InvalidStateTransition):
            tc.approve()

    def test_cannot_approve_rejected(self):
        tc = ToolCall(
            id=ToolCallId("tc-1"),
            tool_name="kubectl",
            input=ToolInput({}),
        )
        tc.reject("No")
        with pytest.raises(InvalidStateTransition):
            tc.approve()


class TestMessage:
    """Tests for Message entity."""

    def test_create_user_message(self):
        msg = Message.user("Hello")
        assert msg.is_user_message
        assert msg.text == "Hello"
        assert msg.role == MessageRole.USER

    def test_create_assistant_message(self):
        msg = Message.assistant("Hi there!")
        assert msg.is_assistant_message
        assert msg.text == "Hi there!"

    def test_create_system_message(self):
        msg = Message.system("You are helpful")
        assert msg.is_system_message


class TestConversation:
    """Tests for Conversation aggregate."""

    def test_create_empty(self):
        conv = Conversation.create()
        assert conv.message_count == 0
        assert not conv.is_blocked

    def test_add_messages(self):
        conv = Conversation.create()

        conv.add_user_message("Hello")
        conv.add_assistant_message("Hi!")

        assert conv.message_count == 2

    def test_blocks_on_pending_approval(self):
        conv = Conversation.create()
        tc = ToolCall(
            id=ToolCallId("tc-1"),
            tool_name="kubectl",
            input=ToolInput({}),
            requires_approval=True,
        )
        conv.request_tool_approval([tc])

        assert conv.is_blocked
        assert conv.has_pending_approvals

    def test_cannot_add_user_message_when_blocked(self):
        conv = Conversation.create()
        tc = ToolCall(
            id=ToolCallId("tc-1"),
            tool_name="kubectl",
            input=ToolInput({}),
            requires_approval=True,
        )
        conv.request_tool_approval([tc])

        with pytest.raises(ConversationBlocked):
            conv.add_user_message("Another message")

    def test_approve_tool_call(self):
        conv = Conversation.create()
        tc = ToolCall(
            id=ToolCallId("tc-1"),
            tool_name="kubectl",
            input=ToolInput({}),
            requires_approval=True,
        )
        conv.request_tool_approval([tc])

        conv.approve_tool_call("tc-1")
        assert not conv.has_pending_approvals

    def test_approve_nonexistent_raises_error(self):
        conv = Conversation.create()
        with pytest.raises(ToolCallNotFound):
            conv.approve_tool_call("nonexistent")
