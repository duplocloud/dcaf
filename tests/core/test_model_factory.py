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


class FakeGCPMetadata:
    """Stub GCPMetadataManager for tests that don't need real GCP."""

    def get_project(self) -> str:
        return "test-project"

    def get_location(self) -> str:
        return "us-central1"


class TestGoogleVertexGcpAccessToken:
    @patch("dcaf.core.adapters.outbound.agno.model_factory.AgnoModelFactory._create_google_model")
    async def test_create_model_with_gcp_access_token_bypasses_cache(self, mock_create_google):
        """When gcp_access_token is provided, a fresh model is returned (not the cached one)."""
        mock_create_google.return_value = object()
        config = ModelConfig(model_id="gemini-2.0-flash", provider="google")
        factory = AgnoModelFactory(config, gcp_metadata_manager=FakeGCPMetadata())

        await factory.create_model(gcp_access_token="ya29.token1")
        await factory.create_model(gcp_access_token="ya29.token2")

        assert mock_create_google.call_count == 2

    @patch("dcaf.core.adapters.outbound.agno.model_factory.AgnoModelFactory._create_google_model")
    async def test_create_model_without_token_still_caches(self, mock_create_google):
        """When no token is provided, the model is cached as before."""
        mock_create_google.return_value = object()
        config = ModelConfig(model_id="gemini-2.0-flash", provider="google")
        factory = AgnoModelFactory(config, gcp_metadata_manager=FakeGCPMetadata())

        await factory.create_model()
        await factory.create_model()

        assert mock_create_google.call_count == 1

    @patch("dcaf.core.adapters.outbound.agno.model_factory.AgnoModelFactory._create_google_model")
    async def test_create_model_passes_gcp_access_token_to_google_model(self, mock_create_google):
        """create_model forwards gcp_access_token to _create_google_model."""
        mock_create_google.return_value = object()
        config = ModelConfig(model_id="gemini-2.0-flash", provider="google")
        factory = AgnoModelFactory(config, gcp_metadata_manager=FakeGCPMetadata())

        await factory.create_model(gcp_access_token="ya29.mytoken")

        mock_create_google.assert_called_once_with(gcp_access_token="ya29.mytoken")

    @patch("agno.models.google.Gemini")
    def test_create_vertex_gemini_with_access_token_passes_credentials(self, mock_gemini):
        """Gemini model receives google.oauth2.credentials.Credentials(token=token)."""
        from google.oauth2.credentials import Credentials

        config = ModelConfig(
            model_id="gemini-2.0-flash",
            provider="google",
            google_project_id="my-project",
        )
        factory = AgnoModelFactory(config, gcp_metadata_manager=FakeGCPMetadata())
        factory._create_vertex_gemini_model(
            project_id="my-project", location="us-central1", gcp_access_token="ya29.token"
        )
        call_kwargs = mock_gemini.call_args.kwargs
        assert isinstance(call_kwargs.get("credentials"), Credentials)

    @patch("agno.models.vertexai.claude.Claude")
    def test_create_vertex_claude_with_access_token_passes_client_params(self, mock_claude):
        """Vertex Claude receives client_params={'access_token': token}."""
        config = ModelConfig(
            model_id="claude-sonnet-4@20250514",
            provider="google",
            google_project_id="my-project",
        )
        factory = AgnoModelFactory(config, gcp_metadata_manager=FakeGCPMetadata())
        factory._create_vertex_claude_model(
            project_id="my-project", location="us-east5", gcp_access_token="ya29.token"
        )
        call_kwargs = mock_claude.call_args.kwargs
        assert call_kwargs.get("client_params") == {"access_token": "ya29.token"}
