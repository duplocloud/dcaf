"""Tests for the LLM layer (dcaf.core.llm)."""

from dataclasses import fields
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dcaf.core.llm import LLM, LLMResponse, create_llm

# =============================================================================
# LLMResponse Tests
# =============================================================================


class TestLLMResponse:
    def test_defaults(self):
        resp = LLMResponse()
        assert resp.text is None
        assert resp.tool_calls == []
        assert resp.usage == {}
        assert resp.raw is None

    def test_with_text(self):
        resp = LLMResponse(text="Hello")
        assert resp.text == "Hello"

    def test_with_tool_calls(self):
        calls = [{"name": "get_weather", "input": {"city": "NYC"}}]
        resp = LLMResponse(tool_calls=calls)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0]["name"] == "get_weather"

    def test_with_usage(self):
        resp = LLMResponse(usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})
        assert resp.usage["input_tokens"] == 10
        assert resp.usage["total_tokens"] == 15

    def test_is_dataclass(self):
        field_names = {f.name for f in fields(LLMResponse)}
        assert "text" in field_names
        assert "tool_calls" in field_names
        assert "usage" in field_names
        assert "raw" in field_names


# =============================================================================
# AgentResponse inherits from LLMResponse
# =============================================================================


class TestAgentResponseInheritance:
    def test_agent_response_is_subclass(self):
        from dcaf.core.agent import AgentResponse

        assert issubclass(AgentResponse, LLMResponse)

    def test_agent_response_has_llm_fields(self):
        from dcaf.core.agent import AgentResponse

        resp = AgentResponse()
        assert resp.text is None
        assert resp.tool_calls == []
        assert resp.usage == {}

    def test_agent_response_has_agent_fields(self):
        from dcaf.core.agent import AgentResponse

        resp = AgentResponse(
            text="Hi",
            tool_calls=[{"name": "t", "input": {}}],
            needs_approval=True,
            conversation_id="abc",
        )
        assert resp.text == "Hi"
        assert resp.needs_approval is True
        assert resp.conversation_id == "abc"
        assert len(resp.tool_calls) == 1


# =============================================================================
# LLM initialization
# =============================================================================


class TestLLMInit:
    @patch("dcaf.core.llm.AgnoModelFactory")
    @patch("dcaf.core.llm.get_default_gcp_metadata_manager")
    def test_stores_provider_and_model(self, mock_gcp, _mock_factory):
        mock_gcp.return_value = MagicMock()
        llm = LLM(provider="bedrock", model="my-model")
        assert llm.provider == "bedrock"
        assert llm.model_id == "my-model"

    @patch("dcaf.core.llm.AgnoModelFactory")
    @patch("dcaf.core.llm.get_default_gcp_metadata_manager")
    def test_provider_lowercased(self, mock_gcp, _mock_factory):
        mock_gcp.return_value = MagicMock()
        llm = LLM(provider="GOOGLE", model="gemini-2.0-flash")
        assert llm.provider == "google"


# =============================================================================
# LLM.get_model()
# =============================================================================


class TestLLMGetModel:
    @pytest.mark.asyncio
    @patch("dcaf.core.llm.AgnoModelFactory")
    @patch("dcaf.core.llm.get_default_gcp_metadata_manager")
    async def test_delegates_to_factory(self, mock_gcp, mock_factory_cls):
        mock_gcp.return_value = MagicMock()
        mock_factory = MagicMock()
        mock_factory.create_model = AsyncMock(return_value="fake-model-instance")
        mock_factory_cls.return_value = mock_factory

        llm = LLM(provider="bedrock", model="test-model")
        model = await llm.get_model()

        assert model == "fake-model-instance"
        mock_factory.create_model.assert_awaited_once()


# =============================================================================
# LLM.ainvoke()
# =============================================================================


class TestLLMAInvoke:
    @pytest.mark.asyncio
    @patch("dcaf.core.llm.AgnoModelFactory")
    @patch("dcaf.core.llm.get_default_gcp_metadata_manager")
    async def test_returns_llm_response(self, mock_gcp, mock_factory_cls):
        mock_gcp.return_value = MagicMock()

        # Build a mock model that returns a ModelResponse-like object
        mock_model_response = MagicMock()
        mock_model_response.content = "Hello world"
        mock_model_response.tool_calls = None
        mock_model_response.input_tokens = 10
        mock_model_response.output_tokens = 5
        mock_model_response.total_tokens = 15

        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_model_response)

        mock_factory = MagicMock()
        mock_factory.create_model = AsyncMock(return_value=mock_model)
        mock_factory_cls.return_value = mock_factory

        llm = LLM(provider="bedrock", model="test-model")
        response = await llm.ainvoke(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="Be helpful.",
        )

        assert isinstance(response, LLMResponse)
        assert response.text == "Hello world"
        assert response.usage["input_tokens"] == 10
        assert response.usage["output_tokens"] == 5

    @pytest.mark.asyncio
    @patch("dcaf.core.llm.AgnoModelFactory")
    @patch("dcaf.core.llm.get_default_gcp_metadata_manager")
    async def test_extracts_tool_calls(self, mock_gcp, mock_factory_cls):
        mock_gcp.return_value = MagicMock()

        mock_model_response = MagicMock()
        mock_model_response.content = None
        mock_model_response.tool_calls = [
            {"function": {"name": "get_weather", "arguments": '{"city": "NYC"}'}}
        ]
        mock_model_response.input_tokens = None
        mock_model_response.output_tokens = None
        mock_model_response.total_tokens = None

        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_model_response)

        mock_factory = MagicMock()
        mock_factory.create_model = AsyncMock(return_value=mock_model)
        mock_factory_cls.return_value = mock_factory

        llm = LLM(provider="bedrock", model="test-model")
        response = await llm.ainvoke(
            messages=[{"role": "user", "content": "Weather?"}],
            tools=[{"name": "get_weather", "description": "Get weather", "input_schema": {}}],
        )

        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["name"] == "get_weather"
        assert response.tool_calls[0]["input"] == {"city": "NYC"}

    @pytest.mark.asyncio
    @patch("dcaf.core.llm.AgnoModelFactory")
    @patch("dcaf.core.llm.get_default_gcp_metadata_manager")
    async def test_per_call_overrides(self, mock_gcp, mock_factory_cls):
        mock_gcp.return_value = MagicMock()

        mock_model_response = MagicMock()
        mock_model_response.content = "ok"
        mock_model_response.tool_calls = None
        mock_model_response.input_tokens = None
        mock_model_response.output_tokens = None
        mock_model_response.total_tokens = None

        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_model_response)

        mock_factory = MagicMock()
        mock_factory.create_model = AsyncMock(return_value=mock_model)
        mock_factory_cls.return_value = mock_factory

        llm = LLM(provider="bedrock", model="test-model", max_tokens=4096, temperature=0.1)
        await llm.ainvoke(
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=200,
            temperature=0.0,
        )

        # Verify per-call overrides were applied to the model
        assert mock_model.max_tokens == 200
        assert mock_model.temperature == 0.0


# =============================================================================
# LLM.invoke() (sync wrapper)
# =============================================================================


class TestLLMInvoke:
    @patch("dcaf.core.llm.AgnoModelFactory")
    @patch("dcaf.core.llm.get_default_gcp_metadata_manager")
    def test_sync_invoke_returns_response(self, mock_gcp, mock_factory_cls):
        mock_gcp.return_value = MagicMock()

        mock_model_response = MagicMock()
        mock_model_response.content = "Sync hello"
        mock_model_response.tool_calls = None
        mock_model_response.input_tokens = None
        mock_model_response.output_tokens = None
        mock_model_response.total_tokens = None

        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_model_response)

        mock_factory = MagicMock()
        mock_factory.create_model = AsyncMock(return_value=mock_model)
        mock_factory_cls.return_value = mock_factory

        llm = LLM(provider="bedrock", model="test-model")
        response = llm.invoke(messages=[{"role": "user", "content": "Hello"}])

        assert isinstance(response, LLMResponse)
        assert response.text == "Sync hello"


# =============================================================================
# create_llm() factory
# =============================================================================


class TestCreateLlm:
    @patch("dcaf.core.llm.AgnoModelFactory")
    @patch("dcaf.core.llm.get_default_gcp_metadata_manager")
    def test_defaults_to_bedrock(self, mock_gcp, _mock_factory, monkeypatch):
        mock_gcp.return_value = MagicMock()
        monkeypatch.delenv("DCAF_PROVIDER", raising=False)
        monkeypatch.delenv("DCAF_MODEL", raising=False)

        llm = create_llm()
        assert llm.provider == "bedrock"

    @patch("dcaf.core.llm.AgnoModelFactory")
    @patch("dcaf.core.llm.get_default_gcp_metadata_manager")
    def test_explicit_provider_and_model(self, mock_gcp, _mock_factory):
        mock_gcp.return_value = MagicMock()
        llm = create_llm(provider="google", model="gemini-2.0-flash")
        assert llm.provider == "google"
        assert llm.model_id == "gemini-2.0-flash"

    @patch("dcaf.core.llm.AgnoModelFactory")
    @patch("dcaf.core.llm.get_default_gcp_metadata_manager")
    def test_env_var_provider(self, mock_gcp, _mock_factory, monkeypatch):
        mock_gcp.return_value = MagicMock()
        monkeypatch.setenv("DCAF_PROVIDER", "anthropic")
        monkeypatch.delenv("DCAF_MODEL", raising=False)

        llm = create_llm()
        assert llm.provider == "anthropic"

    @patch("dcaf.core.llm.AgnoModelFactory")
    @patch("dcaf.core.llm.get_default_gcp_metadata_manager")
    def test_env_var_model(self, mock_gcp, _mock_factory, monkeypatch):
        mock_gcp.return_value = MagicMock()
        monkeypatch.setenv("DCAF_MODEL", "custom-model-123")
        monkeypatch.delenv("DCAF_PROVIDER", raising=False)

        llm = create_llm()
        assert llm.model_id == "custom-model-123"

    @patch("dcaf.core.llm.AgnoModelFactory")
    @patch("dcaf.core.llm.get_default_gcp_metadata_manager")
    def test_overrides_temperature(self, mock_gcp, _mock_factory_cls):
        mock_gcp.return_value = MagicMock()
        llm = create_llm(provider="bedrock", model="test", temperature=0.0)
        assert llm._temperature == 0.0

    @patch("dcaf.core.llm.AgnoModelFactory")
    @patch("dcaf.core.llm.get_default_gcp_metadata_manager")
    def test_overrides_max_tokens(self, mock_gcp, _mock_factory_cls):
        mock_gcp.return_value = MagicMock()
        llm = create_llm(provider="bedrock", model="test", max_tokens=200)
        assert llm._max_tokens == 200


# =============================================================================
# _convert_response edge cases
# =============================================================================


class TestConvertResponse:
    def test_list_content_with_text_blocks(self):
        mock_resp = MagicMock()
        mock_resp.content = [{"text": "Part 1"}, {"text": "Part 2"}]
        mock_resp.tool_calls = None
        mock_resp.input_tokens = None
        mock_resp.output_tokens = None
        mock_resp.total_tokens = None

        result = LLM._convert_response(mock_resp)
        assert result.text == "Part 1 Part 2"

    def test_list_content_with_string_blocks(self):
        mock_resp = MagicMock()
        mock_resp.content = ["Hello", "World"]
        mock_resp.tool_calls = None
        mock_resp.input_tokens = None
        mock_resp.output_tokens = None
        mock_resp.total_tokens = None

        result = LLM._convert_response(mock_resp)
        assert result.text == "Hello World"

    def test_empty_content(self):
        mock_resp = MagicMock()
        mock_resp.content = None
        mock_resp.tool_calls = None
        mock_resp.input_tokens = None
        mock_resp.output_tokens = None
        mock_resp.total_tokens = None

        result = LLM._convert_response(mock_resp)
        assert result.text is None

    def test_tool_calls_with_json_string_arguments(self):
        mock_resp = MagicMock()
        mock_resp.content = None
        mock_resp.tool_calls = [
            {"function": {"name": "my_tool", "arguments": '{"key": "value"}'}}
        ]
        mock_resp.input_tokens = None
        mock_resp.output_tokens = None
        mock_resp.total_tokens = None

        result = LLM._convert_response(mock_resp)
        assert result.tool_calls[0]["input"] == {"key": "value"}

    def test_tool_calls_with_dict_arguments(self):
        mock_resp = MagicMock()
        mock_resp.content = None
        mock_resp.tool_calls = [
            {"name": "my_tool", "input": {"key": "value"}}
        ]
        mock_resp.input_tokens = None
        mock_resp.output_tokens = None
        mock_resp.total_tokens = None

        result = LLM._convert_response(mock_resp)
        assert result.tool_calls[0]["input"] == {"key": "value"}


# =============================================================================
# _build_messages
# =============================================================================


class TestBuildMessages:
    def test_with_system_prompt(self):
        messages = LLM._build_messages(
            [{"role": "user", "content": "Hi"}],
            system_prompt="Be concise.",
        )
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[0].content == "Be concise."
        assert messages[1].role == "user"

    def test_without_system_prompt(self):
        messages = LLM._build_messages([{"role": "user", "content": "Hi"}])
        assert len(messages) == 1
        assert messages[0].role == "user"

    def test_multiple_messages(self):
        messages = LLM._build_messages([
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "user", "content": "Thanks"},
        ])
        assert len(messages) == 3


# =============================================================================
# Exports
# =============================================================================


class TestExports:
    def test_llm_importable_from_core(self):
        from dcaf.core import LLM, create_llm

        assert LLM is not None
        assert create_llm is not None

    def test_llm_response_base_importable_from_core(self):
        from dcaf.core import LLMResponseBase

        assert LLMResponseBase is LLMResponse
