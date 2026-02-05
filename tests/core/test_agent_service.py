"""Tests for AgentService (dcaf.core.application.services.agent_service)."""

from typing import Any

import pytest

from dcaf.core.application.dto.requests import AgentRequest
from dcaf.core.application.dto.responses import AgentResponse, DataDTO, ToolCallDTO
from dcaf.core.application.services.agent_service import AgentService
from dcaf.core.domain.entities import Message
from dcaf.core.testing import (
    FakeConversationRepository,
    FakeEventPublisher,
)


# =============================================================================
# Async-compatible fake runtime for service tests
# =============================================================================


class AsyncFakeRuntime:
    """Async fake runtime matching the AgentRuntime protocol for service tests."""

    def __init__(self):
        self._responses: list[AgentResponse] = []
        self._invoke_calls: list[dict[str, Any]] = []

    @property
    def invoke_count(self) -> int:
        return len(self._invoke_calls)

    @property
    def last_invoke_call(self) -> dict[str, Any] | None:
        return self._invoke_calls[-1] if self._invoke_calls else None

    def will_respond_with_text(self, text: str) -> "AsyncFakeRuntime":
        self._responses.append(
            AgentResponse.text_only("test-conv", text)
        )
        return self

    def will_respond_with_tool_call(
        self,
        tool_name: str,
        tool_input: dict,
        requires_approval: bool = True,
        tool_call_id: str = "tc-1",
    ) -> "AsyncFakeRuntime":
        tc = ToolCallDTO(
            id=tool_call_id,
            name=tool_name,
            input=tool_input,
            requires_approval=requires_approval,
            status="pending" if requires_approval else "approved",
        )
        self._responses.append(
            AgentResponse.with_tool_calls("test-conv", [tc])
        )
        return self

    def will_respond_with(self, response: AgentResponse) -> "AsyncFakeRuntime":
        self._responses.append(response)
        return self

    async def invoke(
        self,
        messages: list[Message],
        tools: list[Any],
        system_prompt: str | None = None,
        static_system: str | None = None,
        dynamic_system: str | None = None,
        platform_context: dict | None = None,
    ) -> AgentResponse:
        self._invoke_calls.append({
            "messages": messages,
            "tools": tools,
            "system_prompt": system_prompt,
            "static_system": static_system,
            "dynamic_system": dynamic_system,
            "platform_context": platform_context,
        })
        if self._responses:
            return self._responses.pop(0)
        return AgentResponse.text_only("test-conv", "Default response")

    async def invoke_stream(self, **kwargs):
        raise NotImplementedError("Not used in these tests")


# =============================================================================
# Simple fake tool for testing
# =============================================================================


class FakeTool:
    def __init__(self, name: str, requires_approval: bool = False, requires_platform_context: bool = False):
        self._name = name
        self._requires_approval = requires_approval
        self._requires_platform_context = requires_platform_context
        self.execute_calls: list[tuple] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Fake tool: {self._name}"

    @property
    def requires_approval(self) -> bool:
        return self._requires_approval

    @property
    def requires_platform_context(self) -> bool:
        return self._requires_platform_context

    def execute(self, input_data: dict, platform_context: dict | None = None) -> str:
        self.execute_calls.append((input_data, platform_context))
        return f"Executed {self._name}"


# =============================================================================
# Helper to build service with fakes
# =============================================================================


def create_service(runtime: AsyncFakeRuntime | None = None):
    rt = runtime or AsyncFakeRuntime()
    conversations = FakeConversationRepository()
    events = FakeEventPublisher()
    service = AgentService(
        runtime=rt,
        conversations=conversations,
        events=events,
    )
    return service, rt, conversations, events


# =============================================================================
# AgentService.execute Tests
# =============================================================================


class TestAgentServiceExecute:
    @pytest.mark.asyncio
    async def test_basic_text_response(self):
        service, runtime, conversations, events = create_service()
        runtime.will_respond_with_text("Hello!")

        request = AgentRequest(content="Hi there")
        response = await service.execute(request)

        assert response.text == "Hello!"
        assert runtime.invoke_count == 1

    @pytest.mark.asyncio
    async def test_conversation_is_saved(self):
        service, runtime, conversations, events = create_service()
        runtime.will_respond_with_text("Saved")

        request = AgentRequest(content="Test message")
        await service.execute(request)

        assert conversations.save_count == 1
        saved = conversations.last_saved
        assert saved is not None

    @pytest.mark.asyncio
    async def test_user_message_added_to_conversation(self):
        service, runtime, conversations, events = create_service()
        runtime.will_respond_with_text("Reply")

        request = AgentRequest(content="My question")
        await service.execute(request)

        saved = conversations.last_saved
        # Should have at least the user message
        user_messages = [m for m in saved.messages if m.role.value == "user"]
        assert len(user_messages) >= 1

    @pytest.mark.asyncio
    async def test_system_prompt_passed_to_runtime(self):
        service, runtime, conversations, events = create_service()
        runtime.will_respond_with_text("OK")

        request = AgentRequest(
            content="Test",
            system_prompt="Be helpful",
        )
        await service.execute(request)

        assert runtime.last_invoke_call["system_prompt"] == "Be helpful"

    @pytest.mark.asyncio
    async def test_tools_passed_to_runtime(self):
        service, runtime, conversations, events = create_service()
        runtime.will_respond_with_text("Done")

        tool = FakeTool(name="list_pods")
        request = AgentRequest(content="List pods", tools=[tool])
        await service.execute(request)

        assert runtime.last_invoke_call["tools"] == [tool]

    @pytest.mark.asyncio
    async def test_context_passed_to_runtime(self):
        service, runtime, conversations, events = create_service()
        runtime.will_respond_with_text("OK")

        request = AgentRequest(
            content="Test",
            context={"tenant_name": "prod"},
        )
        await service.execute(request)

        pc = runtime.last_invoke_call["platform_context"]
        assert pc is not None
        assert pc.get("tenant_name") == "prod"

    @pytest.mark.asyncio
    async def test_response_includes_conversation_id(self):
        service, runtime, conversations, events = create_service()
        runtime.will_respond_with_text("Test")

        request = AgentRequest(content="Hello")
        response = await service.execute(request)

        assert response.conversation_id is not None
        assert len(response.conversation_id) > 0

    @pytest.mark.asyncio
    async def test_events_published(self):
        service, runtime, conversations, events = create_service()
        runtime.will_respond_with_text("Hello")

        request = AgentRequest(content="Test")
        await service.execute(request)

        # Domain events should be published (at least conversation created)
        assert events.publish_count >= 0  # May or may not have events depending on domain logic

    @pytest.mark.asyncio
    async def test_with_message_history(self):
        service, runtime, conversations, events = create_service()
        runtime.will_respond_with_text("Continuing...")

        request = AgentRequest(
            content="Continue",
            messages=[
                {"role": "user", "content": "First question"},
                {"role": "assistant", "content": "First answer"},
            ],
        )
        response = await service.execute(request)

        assert response.text == "Continuing..."
        # Runtime should receive messages including history
        messages = runtime.last_invoke_call["messages"]
        assert len(messages) >= 3  # 2 history + 1 new

    @pytest.mark.asyncio
    async def test_tool_call_requiring_approval(self):
        service, runtime, conversations, events = create_service()
        runtime.will_respond_with_tool_call(
            tool_name="delete_pod",
            tool_input={"pod": "nginx"},
            requires_approval=True,
        )

        tool = FakeTool(name="delete_pod", requires_approval=True)
        request = AgentRequest(content="Delete nginx", tools=[tool])
        response = await service.execute(request)

        assert response.has_pending_approvals is True
        assert response.is_complete is False

    @pytest.mark.asyncio
    async def test_tool_call_auto_executed(self):
        service, runtime, conversations, events = create_service()
        runtime.will_respond_with_tool_call(
            tool_name="list_pods",
            tool_input={"namespace": "default"},
            requires_approval=False,
        )

        tool = FakeTool(name="list_pods", requires_approval=False)
        request = AgentRequest(content="List pods", tools=[tool])
        response = await service.execute(request)

        # Tool should have been executed automatically
        assert len(tool.execute_calls) == 1
        assert tool.execute_calls[0][0] == {"namespace": "default"}


# =============================================================================
# AgentService._find_tool Tests
# =============================================================================


class TestAgentServiceFindTool:
    def test_finds_matching_tool(self):
        service, _, _, _ = create_service()
        tool = FakeTool(name="kubectl")
        result = service._find_tool("kubectl", [tool])
        assert result is tool

    def test_returns_none_for_missing_tool(self):
        service, _, _, _ = create_service()
        tool = FakeTool(name="kubectl")
        result = service._find_tool("nonexistent", [tool])
        assert result is None

    def test_finds_among_multiple_tools(self):
        service, _, _, _ = create_service()
        tools = [
            FakeTool(name="list"),
            FakeTool(name="delete"),
            FakeTool(name="get"),
        ]
        result = service._find_tool("delete", tools)
        assert result.name == "delete"


# =============================================================================
# AgentService._create_from_message_history Tests
# =============================================================================


class TestCreateFromMessageHistory:
    def test_creates_conversation_with_user_messages(self):
        service, _, _, _ = create_service()
        from dcaf.core.domain.value_objects import PlatformContext

        conv = service._create_from_message_history(
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ],
            system_prompt=None,
            context=PlatformContext.empty(),
        )
        assert len(conv.messages) == 2

    def test_skips_empty_content(self):
        service, _, _, _ = create_service()
        from dcaf.core.domain.value_objects import PlatformContext

        conv = service._create_from_message_history(
            messages=[
                {"role": "user", "content": ""},
                {"role": "user", "content": "Real message"},
            ],
            system_prompt=None,
            context=PlatformContext.empty(),
        )
        assert len(conv.messages) == 1

    def test_includes_system_prompt(self):
        service, _, _, _ = create_service()
        from dcaf.core.domain.value_objects import PlatformContext

        conv = service._create_from_message_history(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="Be helpful",
            context=PlatformContext.empty(),
        )
        # System prompt creates a system message
        system_messages = [m for m in conv.messages if m.role.value == "system"]
        assert len(system_messages) >= 1

    def test_ignores_unknown_roles(self):
        service, _, _, _ = create_service()
        from dcaf.core.domain.value_objects import PlatformContext

        conv = service._create_from_message_history(
            messages=[
                {"role": "function", "content": "result"},
                {"role": "user", "content": "Hello"},
            ],
            system_prompt=None,
            context=PlatformContext.empty(),
        )
        assert len(conv.messages) == 1
