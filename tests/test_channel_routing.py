"""Tests for SlackResponseRouter decision logic."""

from unittest.mock import MagicMock

import pytest

from dcaf.channel_routing import SlackResponseRouter


class _FakeLLM:
    """Minimal fake LLM that returns canned responses."""

    def __init__(self, response):
        self.response = response
        self.last_call = None

    def invoke(self, **kwargs):
        self.last_call = kwargs
        return self.response


def _tool_response(should_respond: bool, reasoning: str = "") -> dict:
    """Build a Bedrock-shaped tool-use response."""
    return {
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "name": "slack_routing_decision",
                            "input": {
                                "should_respond": should_respond,
                                "reasoning": reasoning,
                            },
                        }
                    }
                ]
            }
        },
        "stopReason": "tool_use",
    }


class TestSlackResponseRouter:
    def _create_router(self, llm_response) -> tuple[SlackResponseRouter, _FakeLLM]:
        llm = _FakeLLM(llm_response)
        router = SlackResponseRouter(
            llm_client=llm,
            agent_name="TestBot",
            agent_description="A test agent",
            model_id="test-model",
        )
        return router, llm

    def test_should_respond_true(self):
        router, _ = self._create_router(
            _tool_response(True, "User asked a direct question")
        )
        result = router.should_agent_respond("@TestBot can you help?")
        assert result["should_respond"] is True
        assert result["reasoning"] == "User asked a direct question"

    def test_should_respond_false(self):
        router, _ = self._create_router(_tool_response(False))
        result = router.should_agent_respond("thanks got it")
        assert result["should_respond"] is False

    def test_passes_tool_schema_with_forced_tool_choice(self):
        router, llm = self._create_router(_tool_response(False))
        router.should_agent_respond("hello")

        assert llm.last_call is not None
        assert len(llm.last_call["tools"]) == 1
        assert llm.last_call["tools"][0]["name"] == "slack_routing_decision"
        assert llm.last_call["tool_choice"] == {
            "type": "tool",
            "name": "slack_routing_decision",
        }

    def test_accepts_list_input(self):
        router, llm = self._create_router(_tool_response(True))
        thread = [
            {"role": "user", "user": {"name": "Alice"}, "content": "Help me"},
            {"role": "assistant", "assistant": {"name": "TestBot"}, "content": "Sure"},
            {"role": "user", "user": {"name": "Alice"}, "content": "Thanks"},
        ]
        result = router.should_agent_respond(thread)
        assert result["should_respond"] is True
        assert "Alice" in llm.last_call["messages"][0]["content"]

    def test_legacy_string_response_respond(self):
        router, _ = self._create_router("1")
        result = router.should_agent_respond("@TestBot help")
        assert result["should_respond"] is True

    def test_legacy_string_response_silent(self):
        router, _ = self._create_router("0")
        result = router.should_agent_respond("ok thanks")
        assert result["should_respond"] is False

    def test_llm_error_defaults_to_silent(self):
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("API timeout")
        router = SlackResponseRouter(
            llm_client=llm,
            agent_name="TestBot",
            model_id="test-model",
        )
        result = router.should_agent_respond("hello")
        assert result["should_respond"] is False
        assert "Router error" in result["reasoning"]


class TestCreateLlmFromEnv:
    def test_defaults_to_bedrock(self, monkeypatch):
        monkeypatch.delenv("DCAF_PROVIDER", raising=False)
        monkeypatch.delenv("DCAF_SILENCE_MODEL_ID", raising=False)
        from dcaf.channel_routing import _create_llm_from_env

        llm, model_id = _create_llm_from_env()
        from dcaf.llm import BedrockLLM

        assert isinstance(llm, BedrockLLM)
        assert "haiku" in model_id

    def test_google_provider(self, monkeypatch):
        monkeypatch.setenv("DCAF_PROVIDER", "google")
        monkeypatch.delenv("DCAF_SILENCE_MODEL_ID", raising=False)

        from unittest.mock import patch

        with patch("dcaf.channel_routing.VertexLLM") as mock_cls:
            mock_cls.return_value = MagicMock()
            from dcaf.channel_routing import _create_llm_from_env

            llm, model_id = _create_llm_from_env()
            mock_cls.assert_called_once()
            assert "gemini" in model_id

    def test_custom_model_id(self, monkeypatch):
        monkeypatch.setenv("DCAF_PROVIDER", "bedrock")
        monkeypatch.setenv("DCAF_SILENCE_MODEL_ID", "custom-model-123")
        from dcaf.channel_routing import _create_llm_from_env

        _, model_id = _create_llm_from_env()
        assert model_id == "custom-model-123"
