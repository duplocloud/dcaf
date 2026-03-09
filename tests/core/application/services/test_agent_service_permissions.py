"""Integration tests: AgentService._process_response with permission engine."""

from typing import Any

import pytest

from dcaf.core.application.dto.requests import AgentRequest
from dcaf.core.application.dto.responses import AgentResponse, ToolCallDTO
from dcaf.core.application.services.agent_service import AgentService
from dcaf.core.domain.entities import Message
from dcaf.core.domain.value_objects.platform_context import PlatformContext
from dcaf.core.testing import FakeConversationRepository, FakeEventPublisher


# ---------------------------------------------------------------------------
# Fake runtime that injects tool calls into the response
# ---------------------------------------------------------------------------


class FakeRuntimeWithToolCall:
    """Returns a fake tool-call response so AgentService exercises _process_response."""

    def __init__(
        self,
        tool_name: str,
        tool_input: dict | None = None,
        requires_approval: bool = False,
    ):
        self._tool_name = tool_name
        self._tool_input = tool_input or {"command": tool_name}
        self._requires_approval = requires_approval

    async def invoke(
        self,
        messages: list[Message],
        tools: list[Any],
        **kwargs: Any,
    ) -> AgentResponse:
        tc = ToolCallDTO(
            id="tc-1",
            name=self._tool_name,
            input=self._tool_input,
            requires_approval=self._requires_approval,
        )
        return AgentResponse.with_tool_calls("conv-test", [tc])

    async def invoke_stream(self, **kwargs: Any):
        return
        yield  # make it an async generator


def _make_service(runtime: Any) -> AgentService:
    return AgentService(
        runtime=runtime,
        conversations=FakeConversationRepository(),
        events=FakeEventPublisher(),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DENY_DELETE_ALLOW_GET = {
    "permissions": [
        {"layer": "global", "list": "deny", "rules": ["Bash(kubectl delete *)"]},
        {"layer": "global", "list": "allow", "rules": ["Bash(kubectl get *)"]},
    ]
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAgentServicePermissionBlocked:
    async def test_blocked_tool_call_is_rejected_not_pending(self):
        """A tool call matching a deny rule must end up REJECTED, not in HITL."""
        runtime = FakeRuntimeWithToolCall(
            tool_name="Bash",
            tool_input={"command": "kubectl delete pods --all"},
        )
        service = _make_service(runtime)
        request = AgentRequest(
            content="delete all pods",
            context=DENY_DELETE_ALLOW_GET,
        )

        response = await service.execute(request)

        assert not response.has_pending_approvals
        assert response.is_complete
        tool_calls = response.tool_calls
        assert len(tool_calls) == 1
        assert tool_calls[0].status in ("rejected", "failed")

    async def test_blocked_tool_reason_contains_deny(self):
        """The rejection reason must mention the deny rule."""
        runtime = FakeRuntimeWithToolCall(
            tool_name="Bash",
            tool_input={"command": "kubectl delete deployments/api"},
        )
        service = _make_service(runtime)
        request = AgentRequest(content="delete api", context=DENY_DELETE_ALLOW_GET)

        response = await service.execute(request)

        tool_call = response.tool_calls[0]
        assert "deny" in (tool_call.rejection_reason or "").lower() or \
               "blocked" in (tool_call.rejection_reason or "").lower()


class TestAgentServicePermissionAllowed:
    async def test_allowed_tool_call_executes_without_hitl(self):
        """A tool call matching an allow rule must execute and not go to HITL."""
        runtime = FakeRuntimeWithToolCall(
            tool_name="Bash",
            tool_input={"command": "kubectl get pods"},
        )
        service = _make_service(runtime)
        request = AgentRequest(content="get pods", context=DENY_DELETE_ALLOW_GET)

        response = await service.execute(request)

        assert not response.has_pending_approvals


class TestAgentServicePermissionHITLFallback:
    async def test_unmatched_tool_call_goes_to_hitl(self):
        """A tool call with no matching rule must go to HITL (step 11)."""
        runtime = FakeRuntimeWithToolCall(
            tool_name="Bash",
            tool_input={"command": "helm upgrade my-release ./chart"},
        )
        service = _make_service(runtime)
        request = AgentRequest(content="upgrade helm", context=DENY_DELETE_ALLOW_GET)

        response = await service.execute(request)

        assert response.has_pending_approvals
        assert not response.is_complete


class TestAgentServicePermissionsBackwardsCompat:
    async def test_no_permissions_uses_tool_requires_approval_flag(self):
        """When context has no permissions, tool.requires_approval governs."""
        runtime = FakeRuntimeWithToolCall(
            tool_name="Bash",
            tool_input={"command": "kubectl delete pods"},
            requires_approval=False,
        )
        service = _make_service(runtime)
        request = AgentRequest(content="do it", context={"tenant_name": "prod"})

        response = await service.execute(request)

        assert not response.has_pending_approvals

    async def test_no_context_uses_tool_flag(self):
        runtime = FakeRuntimeWithToolCall(
            tool_name="Bash",
            tool_input={"command": "kubectl get pods"},
            requires_approval=False,
        )
        service = _make_service(runtime)
        request = AgentRequest(content="get pods")

        response = await service.execute(request)

        assert not response.has_pending_approvals
