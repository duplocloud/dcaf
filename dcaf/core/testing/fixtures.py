"""pytest fixtures for DCAF Core testing."""

from collections.abc import Generator
from typing import Any

import pytest

from ..application.services import AgentService, ApprovalService
from ..domain.services import ApprovalPolicy
from .builders import (
    ConversationBuilder,
    MessageBuilder,
    ToolBuilder,
    ToolCallBuilder,
)
from .fakes import (
    FakeAgentRuntime,
    FakeApprovalCallback,
    FakeConversationRepository,
    FakeEventPublisher,
)

# ============================================================================
# Fake Fixtures
# ============================================================================


@pytest.fixture
def fake_runtime() -> FakeAgentRuntime:
    """Provide a fake agent runtime."""
    return FakeAgentRuntime()


@pytest.fixture
def fake_conversations() -> FakeConversationRepository:
    """Provide a fake conversation repository."""
    return FakeConversationRepository()


@pytest.fixture
def fake_approval_callback() -> FakeApprovalCallback:
    """Provide a fake approval callback."""
    return FakeApprovalCallback()


@pytest.fixture
def fake_events() -> FakeEventPublisher:
    """Provide a fake event publisher."""
    return FakeEventPublisher()


# ============================================================================
# Service Fixtures
# ============================================================================


@pytest.fixture
def agent_service(
    fake_runtime: FakeAgentRuntime,
    fake_conversations: FakeConversationRepository,
    fake_events: FakeEventPublisher,
) -> AgentService:
    """Provide an AgentService with fake dependencies."""
    return AgentService(
        runtime=fake_runtime,  # type: ignore[arg-type]
        conversations=fake_conversations,
        events=fake_events,
        approval_policy=ApprovalPolicy(),
    )


@pytest.fixture
def approval_service(
    fake_conversations: FakeConversationRepository,
    fake_events: FakeEventPublisher,
) -> ApprovalService:
    """Provide an ApprovalService with fake dependencies."""
    return ApprovalService(
        conversations=fake_conversations,
        events=fake_events,
    )


# ============================================================================
# Builder Fixtures
# ============================================================================


@pytest.fixture
def message_builder() -> MessageBuilder:
    """Provide a message builder."""
    return MessageBuilder()


@pytest.fixture
def tool_call_builder() -> ToolCallBuilder:
    """Provide a tool call builder."""
    return ToolCallBuilder()


@pytest.fixture
def conversation_builder() -> ConversationBuilder:
    """Provide a conversation builder."""
    return ConversationBuilder()


@pytest.fixture
def tool_builder() -> ToolBuilder:
    """Provide a tool builder."""
    return ToolBuilder()


# ============================================================================
# Domain Object Fixtures
# ============================================================================


@pytest.fixture
def sample_conversation() -> Generator:
    """Provide a sample conversation with one turn."""
    yield ConversationBuilder.with_single_turn()


@pytest.fixture
def sample_kubectl_tool() -> Any:
    """Provide a sample kubectl tool."""
    return ToolBuilder.kubectl_tool()


@pytest.fixture
def sample_user_message() -> Any:
    """Provide a sample user message."""
    return MessageBuilder.user_message("Hello, can you help me?")


@pytest.fixture
def sample_pending_tool_call() -> Any:
    """Provide a sample pending tool call."""
    return ToolCallBuilder.pending_kubectl_call()


# ============================================================================
# Integration Test Fixtures
# ============================================================================


@pytest.fixture
def approval_required_runtime(fake_runtime: FakeAgentRuntime) -> FakeAgentRuntime:
    """Provide a runtime configured to return tool calls requiring approval."""
    fake_runtime.will_respond_with_tool_call(
        tool_name="kubectl",
        tool_input={"command": "delete pod my-pod"},
        requires_approval=True,
    )
    return fake_runtime


@pytest.fixture
def auto_approve_callback(fake_approval_callback: FakeApprovalCallback) -> FakeApprovalCallback:
    """Provide a callback configured to auto-approve."""
    return fake_approval_callback.will_approve_all()


@pytest.fixture
def auto_reject_callback(fake_approval_callback: FakeApprovalCallback) -> FakeApprovalCallback:
    """Provide a callback configured to auto-reject."""
    return fake_approval_callback.will_reject_all("Rejected by test")
