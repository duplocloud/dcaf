"""Tests for Agent facade (dcaf.core.agent)."""

from unittest.mock import patch

import pytest

from dcaf.core.agent import Agent, AgentResponse, PendingToolCall
from dcaf.core.application.dto.responses import (
    AgentResponse as InternalAgentResponse,
)
from dcaf.core.application.dto.responses import (
    DataDTO,
    ToolCallDTO,
)
from dcaf.core.interceptors import InterceptorError, LLMRequest, LLMResponse
from dcaf.core.models import ChatMessage
from dcaf.core.session import Session

# =============================================================================
# Helpers
# =============================================================================


class FakeRuntime:
    """Fake runtime adapter for testing Agent without real LLM calls."""

    def __init__(self):
        self._response_text = "Hello from agent"
        self._response_tool_calls: list[ToolCallDTO] = []
        self._response_has_pending = False
        self._invoke_calls: list[dict] = []

    def will_respond_with_text(self, text: str):
        self._response_text = text

    def will_respond_with_tool_calls(self, tool_calls: list[ToolCallDTO]):
        self._response_tool_calls = tool_calls
        self._response_has_pending = True

    async def invoke(self, **kwargs) -> InternalAgentResponse:
        self._invoke_calls.append(kwargs)
        return InternalAgentResponse(
            conversation_id="conv-123",
            text=self._response_text,
            data=DataDTO(tool_calls=self._response_tool_calls),
            has_pending_approvals=self._response_has_pending,
            is_complete=not self._response_has_pending,
        )

    async def invoke_stream(self, **_kwargs):
        yield {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "streamed"}}


def _create_agent(runtime: FakeRuntime | None = None, **kwargs) -> Agent:
    """Create an Agent with a patched runtime to avoid real LLM calls."""
    rt = runtime or FakeRuntime()
    with patch("dcaf.core.agent.load_adapter", return_value=rt):
        agent = Agent(**kwargs)
    return agent


# =============================================================================
# Agent.__init__ Tests
# =============================================================================


class TestAgentInit:
    def test_default_values(self):
        agent = _create_agent()
        assert agent.tools == []
        assert agent.system_prompt is None
        assert agent.name == "dcaf-agent"
        assert agent.description == "A DCAF agent"

    def test_custom_tools(self):
        tools = [lambda: None]
        agent = _create_agent(tools=tools)
        assert agent.tools == tools

    def test_system_prompt(self):
        agent = _create_agent(system_prompt="Be helpful")
        assert agent.system_prompt == "Be helpful"

    def test_description_falls_back_to_system_prompt(self):
        agent = _create_agent(system_prompt="A K8s assistant")
        assert agent.description == "A K8s assistant"

    def test_custom_name_and_description(self):
        agent = _create_agent(name="my-agent", description="Does things")
        assert agent.name == "my-agent"
        assert agent.description == "Does things"

    def test_model_config_defaults_to_empty_dict(self):
        agent = _create_agent()
        assert agent._model_config == {}

    def test_on_interceptor_error_default(self):
        agent = _create_agent()
        assert agent._on_interceptor_error == "abort"

    def test_request_interceptors_normalized(self):
        def my_interceptor(req):
            return req

        agent = _create_agent(request_interceptors=my_interceptor)
        assert agent._request_interceptors == [my_interceptor]

    def test_response_interceptors_normalized(self):
        def my_interceptor(resp):
            return resp

        agent = _create_agent(response_interceptors=[my_interceptor])
        assert agent._response_interceptors == [my_interceptor]

    def test_no_interceptors_normalized_to_empty(self):
        agent = _create_agent()
        assert agent._request_interceptors == []
        assert agent._response_interceptors == []

    def test_event_registry_empty_by_default(self):
        agent = _create_agent()
        assert not agent._event_registry.has_subscribers("any_event")

    def test_on_decorator_subscribes_handler(self):
        agent = _create_agent()

        @agent.on("tool_call_started")
        def handler(event):
            pass

        assert agent._event_registry.has_subscribers("tool_call_started")
        assert handler in agent._event_registry.get_handlers("tool_call_started")

    def test_on_decorator_multiple_event_types(self):
        agent = _create_agent()

        @agent.on("tool_call_started", "tool_call_completed")
        def handler(event):
            pass

        assert agent._event_registry.has_subscribers("tool_call_started")
        assert agent._event_registry.has_subscribers("tool_call_completed")
        assert handler in agent._event_registry.get_handlers("tool_call_started")
        assert handler in agent._event_registry.get_handlers("tool_call_completed")


# =============================================================================
# Agent.run() Tests
# =============================================================================


class TestAgentRun:
    @pytest.mark.asyncio
    async def test_basic_text_response(self):
        runtime = FakeRuntime()
        runtime.will_respond_with_text("Hello!")
        agent = _create_agent(runtime=runtime)

        response = await agent.run(messages=[{"role": "user", "content": "Hi"}])

        assert response.text == "Hello!"
        assert response.is_complete is True
        assert response.needs_approval is False

    @pytest.mark.asyncio
    async def test_empty_messages_raises_error(self):
        agent = _create_agent()

        with pytest.raises(ValueError, match="messages cannot be empty"):
            await agent.run(messages=[])

    @pytest.mark.asyncio
    async def test_accepts_dict_messages(self):
        agent = _create_agent()

        response = await agent.run(messages=[{"role": "user", "content": "Hello"}])

        assert response.text is not None

    @pytest.mark.asyncio
    async def test_accepts_chat_message_instances(self):
        agent = _create_agent()

        response = await agent.run(messages=[ChatMessage(role="user", content="Hello")])

        assert response.text is not None

    @pytest.mark.asyncio
    async def test_conversation_id_returned(self):
        agent = _create_agent()

        response = await agent.run(messages=[{"role": "user", "content": "Hi"}])

        # conversation_id is generated by AgentService, just verify it's non-empty
        assert response.conversation_id
        assert isinstance(response.conversation_id, str)

    @pytest.mark.asyncio
    async def test_session_dict_hydrated(self):
        agent = _create_agent()

        response = await agent.run(
            messages=[{"role": "user", "content": "Hi"}],
            session={"wizard_step": 2},
        )

        assert response.session == {"wizard_step": 2}

    @pytest.mark.asyncio
    async def test_session_object_hydrated(self):
        session = Session()
        session.set("key", "value")
        agent = _create_agent()

        response = await agent.run(
            messages=[{"role": "user", "content": "Hi"}],
            session=session,
        )

        assert response.session == {"key": "value"}

    @pytest.mark.asyncio
    async def test_session_none_returns_empty(self):
        agent = _create_agent()

        response = await agent.run(
            messages=[{"role": "user", "content": "Hi"}],
        )

        # Session should be empty dict or similar
        assert isinstance(response.session, dict)

    @pytest.mark.asyncio
    async def test_agent_ref_set_on_response(self):
        agent = _create_agent()

        response = await agent.run(messages=[{"role": "user", "content": "Hi"}])

        assert response._agent is agent


# =============================================================================
# Agent._build_system_parts Tests
# =============================================================================


class TestBuildSystemParts:
    def test_no_system_prompt_or_context(self):
        agent = _create_agent()
        static, dynamic = agent._build_system_parts()
        assert static is None
        assert dynamic is None

    def test_static_system_prompt_only(self):
        agent = _create_agent(system_prompt="Be helpful")
        static, dynamic = agent._build_system_parts()
        assert static == "Be helpful"
        assert dynamic is None

    def test_string_system_context(self):
        agent = _create_agent(
            system_prompt="Be helpful",
            system_context="User is in production",
        )
        static, dynamic = agent._build_system_parts()
        assert static == "Be helpful"
        assert dynamic == "User is in production"

    def test_callable_system_context(self):
        agent = _create_agent(
            system_context=lambda ctx: f"Tenant: {ctx.get('tenant_name', 'n/a')}",
        )
        static, dynamic = agent._build_system_parts(platform_context={"tenant_name": "prod"})
        assert static is None
        assert dynamic == "Tenant: prod"

    def test_callable_system_context_with_no_context(self):
        agent = _create_agent(
            system_context=lambda ctx: f"Tenant: {ctx.get('tenant_name', 'n/a')}",
        )
        static, dynamic = agent._build_system_parts()
        assert dynamic == "Tenant: n/a"


# =============================================================================
# Request Interceptor Tests
# =============================================================================


class TestRequestInterceptors:
    @pytest.mark.asyncio
    async def test_request_interceptor_modifies_request(self):
        def add_context(request: LLMRequest) -> LLMRequest:
            request.context["injected"] = True
            return request

        agent = _create_agent(request_interceptors=add_context)

        response = await agent.run(messages=[{"role": "user", "content": "Hi"}])

        assert response.text is not None

    @pytest.mark.asyncio
    async def test_request_interceptor_error_propagates_on_abort(self):
        def blocker(request: LLMRequest) -> LLMRequest:
            raise InterceptorError(user_message="Blocked!", code="FORBIDDEN")

        agent = _create_agent(
            request_interceptors=blocker,
            on_interceptor_error="abort",
        )

        with pytest.raises(InterceptorError) as exc_info:
            await agent.run(messages=[{"role": "user", "content": "Hi"}])
        assert exc_info.value.user_message == "Blocked!"

    @pytest.mark.asyncio
    async def test_unexpected_interceptor_error_abort(self):
        def bad_interceptor(request: LLMRequest) -> LLMRequest:
            raise RuntimeError("Unexpected")

        agent = _create_agent(
            request_interceptors=bad_interceptor,
            on_interceptor_error="abort",
        )

        with pytest.raises(RuntimeError, match="Unexpected"):
            await agent.run(messages=[{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_unexpected_interceptor_error_continue(self):
        def bad_interceptor(request: LLMRequest) -> LLMRequest:
            raise RuntimeError("Unexpected")

        agent = _create_agent(
            request_interceptors=bad_interceptor,
            on_interceptor_error="continue",
        )

        # Should not raise, continues with original request
        response = await agent.run(messages=[{"role": "user", "content": "Hi"}])
        assert response.text is not None


# =============================================================================
# Response Interceptor Tests
# =============================================================================


class TestResponseInterceptors:
    @pytest.mark.asyncio
    async def test_response_interceptor_modifies_text(self):
        def uppercase(response: LLMResponse) -> LLMResponse:
            response.text = response.text.upper()
            return response

        runtime = FakeRuntime()
        runtime.will_respond_with_text("hello world")
        agent = _create_agent(
            runtime=runtime,
            response_interceptors=uppercase,
        )

        response = await agent.run(messages=[{"role": "user", "content": "Hi"}])

        assert response.text == "HELLO WORLD"

    @pytest.mark.asyncio
    async def test_response_interceptor_error_returns_message(self):
        def blocker(response: LLMResponse) -> LLMResponse:
            raise InterceptorError(user_message="Response blocked")

        runtime = FakeRuntime()
        runtime.will_respond_with_text("original text")
        agent = _create_agent(
            runtime=runtime,
            response_interceptors=blocker,
        )

        # InterceptorError in response interceptors returns the error message
        response = await agent.run(messages=[{"role": "user", "content": "Hi"}])
        assert response.text == "Response blocked"
        assert response.is_complete is True

    @pytest.mark.asyncio
    async def test_response_interceptor_unexpected_error_abort(self):
        def bad_interceptor(response: LLMResponse) -> LLMResponse:
            raise RuntimeError("Boom")

        runtime = FakeRuntime()
        runtime.will_respond_with_text("hello")
        agent = _create_agent(
            runtime=runtime,
            response_interceptors=bad_interceptor,
            on_interceptor_error="abort",
        )

        with pytest.raises(RuntimeError, match="Boom"):
            await agent.run(messages=[{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_response_interceptor_unexpected_error_continue(self):
        def bad_interceptor(response: LLMResponse) -> LLMResponse:
            raise RuntimeError("Boom")

        runtime = FakeRuntime()
        runtime.will_respond_with_text("hello")
        agent = _create_agent(
            runtime=runtime,
            response_interceptors=bad_interceptor,
            on_interceptor_error="continue",
        )

        # Should not raise, continues with original response
        response = await agent.run(messages=[{"role": "user", "content": "Hi"}])
        assert response.text == "hello"


# =============================================================================
# AgentResponse Tests
# =============================================================================


class TestAgentResponse:
    def test_defaults(self):
        response = AgentResponse()
        assert response.text is None
        assert response.needs_approval is False
        assert response.pending_tools == []
        assert response.conversation_id == ""
        assert response.is_complete is True
        assert response.session == {}
        assert response._agent is None

    def test_approve_all_without_agent_returns_self(self):
        response = AgentResponse(needs_approval=True)
        result = response.approve_all()
        assert result is response

    def test_reject_all_without_agent_returns_self(self):
        response = AgentResponse(needs_approval=True)
        result = response.reject_all("reason")
        assert result is response

    def test_approve_all_without_pending_returns_self(self):
        agent = _create_agent()
        response = AgentResponse(_agent=agent)
        result = response.approve_all()
        assert result is response

    def test_to_message_basic(self):
        response = AgentResponse(
            text="Hello",
            needs_approval=False,
            is_complete=True,
        )
        message = response.to_message()
        assert message.content == "Hello"
        assert message.meta_data["has_pending_approvals"] is False
        assert message.meta_data["is_complete"] is True

    def test_to_message_with_pending_tools(self):
        response = AgentResponse(
            text="Need approval",
            needs_approval=True,
            pending_tools=[
                PendingToolCall(
                    id="tc-1",
                    name="delete_pod",
                    input={"pod": "nginx"},
                    description="Delete a pod",
                )
            ],
        )
        message = response.to_message()
        assert message.meta_data["has_pending_approvals"] is True
        assert len(message.data.tool_calls) == 1
        assert message.data.tool_calls[0].name == "delete_pod"

    def test_to_message_none_text(self):
        response = AgentResponse(text=None)
        message = response.to_message()
        assert message.content == ""

    def test_to_message_includes_session(self):
        response = AgentResponse(
            text="Hi",
            session={"step": 3},
        )
        message = response.to_message()
        assert message.data.session == {"step": 3}


# =============================================================================
# PendingToolCall Tests
# =============================================================================


class TestPendingToolCall:
    def test_basic_fields(self):
        tc = PendingToolCall(
            id="tc-1",
            name="delete_pod",
            input={"pod": "nginx"},
            description="Delete a pod",
        )
        assert tc.id == "tc-1"
        assert tc.name == "delete_pod"
        assert tc.input == {"pod": "nginx"}
        assert tc.description == "Delete a pod"

    def test_approve_without_service_does_nothing(self):
        tc = PendingToolCall(
            id="tc-1",
            name="tool",
            input={},
        )
        # Should not raise
        tc.approve()

    def test_reject_without_service_does_nothing(self):
        tc = PendingToolCall(
            id="tc-1",
            name="tool",
            input={},
        )
        # Should not raise
        tc.reject("reason")


# =============================================================================
# Agent Event Registry Tests
# =============================================================================


class TestAgentEventRegistry:
    def test_event_registry_exists(self):
        agent = _create_agent()
        assert hasattr(agent, "_event_registry")
        assert agent._event_registry is not None

    def test_registry_has_no_subscribers_initially(self):
        agent = _create_agent()
        assert not agent._event_registry.has_subscribers("tool_call_started")
        assert not agent._event_registry.has_subscribers("text_delta")

    def test_on_decorator_registers_handler(self):
        agent = _create_agent()
        events_received = []

        @agent.on("tool_call_started")
        def handler(event):
            events_received.append(event)

        assert agent._event_registry.has_subscribers("tool_call_started")
        handlers = agent._event_registry.get_handlers("tool_call_started")
        assert len(handlers) == 1
        assert handlers[0] is handler

    def test_multiple_handlers_for_same_event(self):
        agent = _create_agent()

        @agent.on("text_delta")
        def handler1(event):
            pass

        @agent.on("text_delta")
        def handler2(event):
            pass

        handlers = agent._event_registry.get_handlers("text_delta")
        assert len(handlers) == 2
        assert handler1 in handlers
        assert handler2 in handlers

    def test_handler_subscribed_to_multiple_events(self):
        agent = _create_agent()

        @agent.on("tool_call_started", "tool_call_completed")
        def handler(event):
            pass

        assert agent._event_registry.has_subscribers("tool_call_started")
        assert agent._event_registry.has_subscribers("tool_call_completed")
        assert handler in agent._event_registry.get_handlers("tool_call_started")
        assert handler in agent._event_registry.get_handlers("tool_call_completed")
