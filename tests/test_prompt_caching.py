"""Tests for Bedrock prompt caching functionality."""

import logging

from dcaf.core.adapters.outbound.agno.caching_bedrock import CachingAwsBedrock


class TestCachingAwsBedrock:
    """Tests for CachingAwsBedrock class."""

    def test_build_cached_system_message_static_only(self):
        """Static-only system message has checkpoint at end."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
            static_system="Static instructions here." * 300,  # Make it long enough
        )

        result = model._build_cached_system_message()

        assert len(result) == 2
        assert result[0]["text"].startswith("Static instructions")
        assert result[1] == {"cachePoint": {"type": "default"}}

    def test_build_cached_system_message_static_and_dynamic(self):
        """Static + dynamic has checkpoint between them."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
            static_system="Static instructions." * 300,
            dynamic_system="Dynamic context.",
        )

        result = model._build_cached_system_message()

        assert len(result) == 3
        assert result[0]["text"].startswith("Static instructions")
        assert result[1] == {"cachePoint": {"type": "default"}}
        assert result[2] == {"text": "Dynamic context."}

    def test_build_cached_system_message_dynamic_only(self):
        """Dynamic-only system message has no checkpoint."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
            dynamic_system="Dynamic context only.",
        )

        result = model._build_cached_system_message()

        assert len(result) == 1
        assert result[0] == {"text": "Dynamic context only."}
        # No cache checkpoint - nothing static to cache

    def test_add_cache_checkpoint(self):
        """Cache checkpoint is added to system message."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
        )

        system_message = [{"text": "You are a helpful assistant." * 300}]
        result = model._add_cache_checkpoint(system_message)

        assert len(result) == 2
        assert result[0]["text"].startswith("You are a helpful assistant")
        assert result[1] == {"cachePoint": {"type": "default"}}

    def test_add_cache_checkpoint_does_not_mutate_original(self):
        """Original system message is not modified."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
        )

        original = [{"text": "You are a helpful assistant."}]
        original_copy = list(original)

        model._add_cache_checkpoint(original)

        assert original == original_copy  # Original unchanged

    def test_check_token_threshold_below_minimum(self):
        """Short text below threshold returns False."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
        )

        short_text = "Too short"
        result = model._check_token_threshold(short_text)

        assert result is False

    def test_check_token_threshold_above_minimum(self):
        """Long text above threshold returns True."""
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
        )

        # Create text with ~2000 tokens (8000 chars)
        long_text = "This is a long system prompt. " * 270
        result = model._check_token_threshold(long_text)

        assert result is True

    def test_log_cache_metrics_cache_hit(self, caplog):
        """Cache HIT is logged correctly."""
        caplog.set_level(logging.INFO)
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
        )

        response = {
            "usage": {
                "inputTokens": 100,
                "outputTokens": 50,
                "cacheReadInputTokens": 950,
            }
        }

        model._log_cache_metrics(response)

        assert "Cache HIT" in caplog.text
        assert "950 tokens" in caplog.text

    def test_log_cache_metrics_cache_miss(self, caplog):
        """Cache MISS is logged correctly."""
        caplog.set_level(logging.INFO)
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
        )

        response = {
            "usage": {
                "inputTokens": 1000,
                "outputTokens": 50,
                "cacheCreationInputTokens": 950,
            }
        }

        model._log_cache_metrics(response)

        assert "Cache MISS" in caplog.text
        assert "950 tokens" in caplog.text


class TestAgentWithCaching:
    """Tests for Agent class with caching enabled."""

    def test_agent_build_system_parts_static_only(self):
        """Build system parts with static content only."""
        from dcaf.core import Agent

        agent = Agent(system_prompt="Static instructions")

        static, dynamic = agent._build_system_parts({})

        assert static == "Static instructions"
        assert dynamic is None

    def test_agent_build_system_parts_with_context_string(self):
        """Build system parts with static + string context."""
        from dcaf.core import Agent

        agent = Agent(
            system_prompt="Static instructions",
            system_context="Dynamic context",
        )

        static, dynamic = agent._build_system_parts({})

        assert static == "Static instructions"
        assert dynamic == "Dynamic context"

    def test_agent_build_system_parts_with_context_callable(self):
        """Build system parts with static + callable context."""
        from dcaf.core import Agent

        agent = Agent(
            system_prompt="Static instructions",
            system_context=lambda ctx: f"Tenant: {ctx.get('tenant', 'unknown')}",
        )

        static, dynamic = agent._build_system_parts({"tenant": "acme"})

        assert static == "Static instructions"
        assert dynamic == "Tenant: acme"

    def test_agent_with_model_config_caching(self):
        """Agent with cache in model_config."""
        from dcaf.core import Agent

        agent = Agent(system_prompt="Test prompt", model_config={"cache_system_prompt": True})

        assert agent._model_config.get("cache_system_prompt") is True

    def test_agent_without_caching(self):
        """Agent without caching config."""
        from dcaf.core import Agent

        agent = Agent(system_prompt="Test prompt")

        assert agent._model_config.get("cache_system_prompt", False) is False
