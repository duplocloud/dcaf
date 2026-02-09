"""Tests for Interceptors (dcaf.core.interceptors)."""

import pytest

from dcaf.core.interceptors import (
    InterceptorError,
    InterceptorPipeline,
    LLMRequest,
    LLMResponse,
    create_request_from_messages,
    create_response_from_text,
    normalize_interceptors,
)
from dcaf.core.session import Session

# =============================================================================
# LLMRequest Tests
# =============================================================================


class TestLLMRequest:
    def test_create_basic(self):
        request = LLMRequest(messages=[{"role": "user", "content": "hello"}])
        assert len(request.messages) == 1
        assert request.tools == []
        assert request.system is None
        assert request.context == {}

    def test_context_defaults_to_empty_dict(self):
        request = LLMRequest(messages=[], context=None)
        assert request.context == {}

    def test_session_defaults_to_empty_session(self):
        request = LLMRequest(messages=[])
        assert request.session is not None
        assert isinstance(request.session, Session)
        assert request.session.is_empty

    def test_get_latest_user_message(self):
        request = LLMRequest(
            messages=[
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "reply"},
                {"role": "user", "content": "second"},
            ]
        )
        assert request.get_latest_user_message() == "second"

    def test_get_latest_user_message_no_user_messages(self):
        request = LLMRequest(messages=[{"role": "assistant", "content": "hello"}])
        assert request.get_latest_user_message() == ""

    def test_get_latest_user_message_empty_messages(self):
        request = LLMRequest(messages=[])
        assert request.get_latest_user_message() == ""

    def test_add_system_context_to_existing(self):
        request = LLMRequest(messages=[], system="Be helpful.")
        request.add_system_context("User is in production.")
        assert "Be helpful." in request.system
        assert "User is in production." in request.system

    def test_add_system_context_to_none(self):
        request = LLMRequest(messages=[], system=None)
        request.add_system_context("New context")
        assert request.system == "New context"

    def test_session_passed_through(self):
        session = Session()
        session.set("key", "value")
        request = LLMRequest(messages=[], session=session)
        assert request.session.get("key") == "value"


# =============================================================================
# LLMResponse Tests
# =============================================================================


class TestLLMResponse:
    def test_create_basic(self):
        response = LLMResponse(text="Hello!")
        assert response.text == "Hello!"
        assert response.tool_calls == []
        assert response.usage is None
        assert response.raw is None

    def test_session_defaults_to_empty_session(self):
        response = LLMResponse(text="test")
        assert response.session is not None
        assert isinstance(response.session, Session)

    def test_has_tool_calls_empty(self):
        response = LLMResponse(text="test")
        assert not response.has_tool_calls()

    def test_has_tool_calls_with_calls(self):
        response = LLMResponse(
            text="test",
            tool_calls=[{"id": "1", "name": "tool", "input": {}}],
        )
        assert response.has_tool_calls()

    def test_get_text_length(self):
        response = LLMResponse(text="hello")
        assert response.get_text_length() == 5

    def test_get_text_length_empty(self):
        response = LLMResponse(text="")
        assert response.get_text_length() == 0


# =============================================================================
# InterceptorError Tests
# =============================================================================


class TestInterceptorError:
    def test_basic(self):
        error = InterceptorError(user_message="Blocked")
        assert error.user_message == "Blocked"
        assert error.code is None
        assert error.details == {}
        assert str(error) == "Blocked"

    def test_with_code(self):
        error = InterceptorError(user_message="Blocked", code="FORBIDDEN")
        assert error.code == "FORBIDDEN"
        assert str(error) == "[FORBIDDEN] Blocked"

    def test_with_details(self):
        error = InterceptorError(
            user_message="Bad input",
            code="VALIDATION",
            details={"field": "name"},
        )
        assert error.details == {"field": "name"}

    def test_is_exception(self):
        error = InterceptorError(user_message="test")
        assert isinstance(error, Exception)


# =============================================================================
# normalize_interceptors Tests
# =============================================================================


class TestNormalizeInterceptors:
    def test_none_returns_empty_list(self):
        assert normalize_interceptors(None) == []

    def test_single_function_returns_list(self):
        def my_func(x):
            return x

        result = normalize_interceptors(my_func)
        assert result == [my_func]

    def test_list_returns_list(self):
        def a(x):
            return x

        def b(x):
            return x

        result = normalize_interceptors([a, b])
        assert result == [a, b]

    def test_empty_list_returns_empty_list(self):
        assert normalize_interceptors([]) == []


# =============================================================================
# InterceptorPipeline Tests
# =============================================================================


class TestInterceptorPipeline:
    @pytest.mark.asyncio
    async def test_empty_pipeline(self):
        pipeline = InterceptorPipeline(interceptors=[], pipeline_name="test")
        result = await pipeline.run("input")
        assert result == "input"

    @pytest.mark.asyncio
    async def test_single_sync_interceptor(self):
        def add_suffix(data):
            return data + "_modified"

        pipeline = InterceptorPipeline(interceptors=[add_suffix], pipeline_name="test")
        result = await pipeline.run("input")
        assert result == "input_modified"

    @pytest.mark.asyncio
    async def test_multiple_sync_interceptors(self):
        def step1(data):
            return data + "_1"

        def step2(data):
            return data + "_2"

        def step3(data):
            return data + "_3"

        pipeline = InterceptorPipeline(interceptors=[step1, step2, step3], pipeline_name="test")
        result = await pipeline.run("start")
        assert result == "start_1_2_3"

    @pytest.mark.asyncio
    async def test_async_interceptor(self):
        async def async_step(data):
            return data + "_async"

        pipeline = InterceptorPipeline(interceptors=[async_step], pipeline_name="test")
        result = await pipeline.run("input")
        assert result == "input_async"

    @pytest.mark.asyncio
    async def test_mixed_sync_async_interceptors(self):
        def sync_step(data):
            return data + "_sync"

        async def async_step(data):
            return data + "_async"

        pipeline = InterceptorPipeline(interceptors=[sync_step, async_step], pipeline_name="test")
        result = await pipeline.run("start")
        assert result == "start_sync_async"

    @pytest.mark.asyncio
    async def test_interceptor_error_stops_pipeline(self):
        def blocker(data):
            raise InterceptorError(user_message="Blocked!", code="BLOCK")

        def should_not_run(data):
            return data + "_never"

        pipeline = InterceptorPipeline(interceptors=[blocker, should_not_run], pipeline_name="test")
        with pytest.raises(InterceptorError) as exc_info:
            await pipeline.run("input")
        assert exc_info.value.user_message == "Blocked!"

    @pytest.mark.asyncio
    async def test_unexpected_error_propagates(self):
        def bad_interceptor(data):
            raise ValueError("something went wrong")

        pipeline = InterceptorPipeline(interceptors=[bad_interceptor], pipeline_name="test")
        with pytest.raises(ValueError, match="something went wrong"):
            await pipeline.run("input")

    @pytest.mark.asyncio
    async def test_pipeline_with_llm_request(self):
        def add_context(request: LLMRequest) -> LLMRequest:
            request.context["added"] = True
            return request

        pipeline = InterceptorPipeline(interceptors=[add_context], pipeline_name="request")
        request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
        result = await pipeline.run(request)
        assert result.context["added"] is True

    @pytest.mark.asyncio
    async def test_pipeline_with_llm_response(self):
        def clean_text(response: LLMResponse) -> LLMResponse:
            response.text = response.text.upper()
            return response

        pipeline = InterceptorPipeline(interceptors=[clean_text], pipeline_name="response")
        response = LLMResponse(text="hello world")
        result = await pipeline.run(response)
        assert result.text == "HELLO WORLD"


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestCreateRequestFromMessages:
    def test_basic(self):
        request = create_request_from_messages(messages=[{"role": "user", "content": "hello"}])
        assert len(request.messages) == 1
        assert request.tools == []
        assert request.system is None
        assert request.context == {}

    def test_with_all_params(self):
        session = Session()
        session.set("key", "val")
        request = create_request_from_messages(
            messages=[{"role": "user", "content": "hi"}],
            tools=["tool1"],
            system_prompt="Be helpful",
            context={"tenant": "prod"},
            session=session,
        )
        assert request.system == "Be helpful"
        assert request.context == {"tenant": "prod"}
        assert request.tools == ["tool1"]
        assert request.session.get("key") == "val"


class TestCreateResponseFromText:
    def test_basic(self):
        response = create_response_from_text(text="Hello!")
        assert response.text == "Hello!"
        assert response.tool_calls == []
        assert response.usage is None

    def test_with_all_params(self):
        session = Session()
        response = create_response_from_text(
            text="Result",
            tool_calls=[{"id": "1", "name": "t", "input": {}}],
            usage={"input_tokens": 10},
            raw={"original": True},
            session=session,
        )
        assert response.text == "Result"
        assert len(response.tool_calls) == 1
        assert response.usage == {"input_tokens": 10}
        assert response.raw == {"original": True}
