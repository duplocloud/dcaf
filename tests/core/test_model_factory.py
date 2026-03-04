"""Tests for AgnoModelFactory AWS credential routing."""

from unittest.mock import patch

import pytest

from dcaf.core.adapters.outbound.agno.model_factory import AgnoModelFactory, ModelConfig


@pytest.fixture
def base_config():
    return ModelConfig(
        model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        provider="bedrock",
        aws_region="us-east-1",
    )


class TestBedrockCredentialRouting:
    @patch("dcaf.core.adapters.outbound.agno.model_factory.CachingAwsBedrock")
    @patch("dcaf.core.adapters.outbound.agno.model_factory.aioboto3")
    async def test_profile_creates_session_with_profile(
        self, mock_aioboto3, mock_caching, base_config
    ):
        base_config.aws_profile = "my-profile"
        factory = AgnoModelFactory(base_config)
        await factory._create_bedrock_model()
        call_kwargs = mock_aioboto3.Session.call_args.kwargs
        assert call_kwargs.get("profile_name") == "my-profile"
        assert "aws_access_key_id" not in call_kwargs

    @patch("dcaf.core.adapters.outbound.agno.model_factory.CachingAwsBedrock")
    @patch("dcaf.core.adapters.outbound.agno.model_factory.aioboto3")
    async def test_explicit_keys_create_session_with_credentials(
        self, mock_aioboto3, mock_caching, base_config
    ):
        base_config.aws_access_key = "AKIAIOSFODNN7EXAMPLE"
        base_config.aws_secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        factory = AgnoModelFactory(base_config)
        await factory._create_bedrock_model()
        call_kwargs = mock_aioboto3.Session.call_args.kwargs
        assert call_kwargs.get("aws_access_key_id") == "AKIAIOSFODNN7EXAMPLE"
        assert (
            call_kwargs.get("aws_secret_access_key") == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        )
        assert "profile_name" not in call_kwargs

    @patch("dcaf.core.adapters.outbound.agno.model_factory.CachingAwsBedrock")
    @patch("dcaf.core.adapters.outbound.agno.model_factory.aioboto3")
    async def test_no_credentials_uses_default_chain(
        self, mock_aioboto3, mock_caching, base_config
    ):
        factory = AgnoModelFactory(base_config)
        await factory._create_bedrock_model()
        call_kwargs = mock_aioboto3.Session.call_args.kwargs
        assert "profile_name" not in call_kwargs
        assert "aws_access_key_id" not in call_kwargs

    @patch("dcaf.core.adapters.outbound.agno.model_factory.CachingAwsBedrock")
    @patch("dcaf.core.adapters.outbound.agno.model_factory.aioboto3")
    async def test_profile_takes_precedence_over_keys(
        self, mock_aioboto3, mock_caching, base_config
    ):
        base_config.aws_profile = "my-profile"
        base_config.aws_access_key = "AKIAIOSFODNN7EXAMPLE"
        base_config.aws_secret_key = "secret"
        factory = AgnoModelFactory(base_config)
        await factory._create_bedrock_model()
        call_kwargs = mock_aioboto3.Session.call_args.kwargs
        assert call_kwargs.get("profile_name") == "my-profile"
        assert "aws_access_key_id" not in call_kwargs
