"""
Agno Model Factory - Creates LLM model instances for different providers.

This module provides a factory class for creating Agno model instances
based on the configured provider (Bedrock, Anthropic, OpenAI, etc.).

The factory encapsulates provider-specific configuration and credential
handling, providing a clean interface for model creation.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any

from .caching_bedrock import CachingAwsBedrock
from .gcp_metadata import GCPMetadataManager, get_default_gcp_metadata_manager

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Configuration for model creation."""

    model_id: str
    provider: str
    max_tokens: int = 4096
    temperature: float = 0.1

    # AWS configuration
    aws_profile: str | None = None
    aws_region: str | None = None
    aws_access_key: str | None = None
    aws_secret_key: str | None = None

    # Generic API key (OpenAI, Anthropic)
    api_key: str | None = None

    # Google configuration
    google_project_id: str | None = None
    google_location: str | None = None

    # Caching configuration
    cache_system_prompt: bool = False
    static_system: str | None = None
    dynamic_system: str | None = None


class AgnoModelFactory:
    """
    Factory for creating Agno model instances.

    This factory handles provider-specific model creation, including:
    - AWS Bedrock with async session management
    - Direct Anthropic API
    - OpenAI and Azure OpenAI
    - Google Vertex AI (Gemini)
    - Local Ollama models

    Example:
        factory = AgnoModelFactory(
            config=ModelConfig(
                model_id="anthropic.claude-3-sonnet",
                provider="bedrock",
                aws_profile="production",
            )
        )
        model = await factory.create_model()
    """

    # Supported providers
    SUPPORTED_PROVIDERS = frozenset(
        {
            "bedrock",
            "anthropic",
            "openai",
            "azure",
            "google",
            "ollama",
        }
    )

    def __init__(
        self,
        config: ModelConfig,
        gcp_metadata_manager: GCPMetadataManager | None = None,
    ) -> None:
        """
        Initialize the model factory.

        Args:
            config: Model configuration
            gcp_metadata_manager: Optional GCP metadata manager for testing
        """
        self._config = config
        self._gcp_metadata_manager = gcp_metadata_manager or get_default_gcp_metadata_manager()

        # Cached model and session (for reuse)
        self._model: Any = None
        self._async_session: Any = None

    @property
    def model_id(self) -> str:
        """Get the model identifier."""
        return self._config.model_id

    @property
    def provider(self) -> str:
        """Get the provider name."""
        return self._config.provider

    async def create_model(self) -> Any:
        """
        Create or retrieve the cached model instance.

        Returns:
            An Agno model instance

        Raises:
            ValueError: If the provider is not supported
        """
        if self._model is not None:
            return self._model

        provider = self._config.provider.lower()

        if provider == "bedrock":
            self._model = await self._create_bedrock_model()
        elif provider == "anthropic":
            self._model = self._create_anthropic_model()
        elif provider == "openai":
            self._model = self._create_openai_model()
        elif provider == "azure":
            self._model = self._create_azure_model()
        elif provider == "google":
            self._model = self._create_google_model()
        elif provider == "ollama":
            self._model = self._create_ollama_model()
        else:
            supported = ", ".join(sorted(self.SUPPORTED_PROVIDERS))
            raise ValueError(
                f"Unsupported provider: '{provider}'. Supported providers: {supported}"
            )

        return self._model

    async def _create_bedrock_model(self) -> Any:
        """
        Create an AWS Bedrock model with async session.

        Uses aioboto3 for true async AWS calls, which is critical for
        non-blocking operation in async contexts like FastAPI.

        Returns:
            Agno AwsBedrock model configured with async session
        """
        import aioboto3

        config = self._config

        # Infer region from model ID if it's an ARN
        region = self._infer_region_from_model_id(config.model_id, config.aws_region or "us-east-1")

        # Create async session with profile if specified
        if config.aws_profile:
            logger.info(f"Agno: Using AWS profile '{config.aws_profile}' (region: {region})")
            async_session = aioboto3.Session(
                region_name=region,
                profile_name=config.aws_profile,
            )
        else:
            # Use default credential chain (env vars, instance profile, etc.)
            logger.info(f"Agno: Using default AWS credentials (region: {region})")
            async_session = aioboto3.Session(region_name=region)

        # Cache the session
        self._async_session = async_session

        # Log configuration
        logger.info(
            f"Agno: Initialized Bedrock model {config.model_id} "
            f"(temperature={config.temperature}, max_tokens={config.max_tokens}, "
            f"cache_system_prompt={config.cache_system_prompt})"
        )

        # Always use CachingAwsBedrock for raw logging support
        logger.debug("Using CachingAwsBedrock for raw LLM logging support")
        return CachingAwsBedrock(
            id=config.model_id,
            aws_region=region,
            async_session=async_session,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            cache_system_prompt=config.cache_system_prompt,
            static_system=config.static_system,
            dynamic_system=config.dynamic_system,
        )

    @staticmethod
    def _infer_region_from_model_id(model_id: str, fallback_region: str) -> str:
        """
        Extract AWS region from Bedrock model ARN.

        Args:
            model_id: Model ID or ARN
            fallback_region: Region to use if extraction fails

        Returns:
            AWS region string
        """
        try:
            if model_id.startswith("arn:aws:bedrock:"):
                parts = model_id.split(":")
                if len(parts) > 3 and parts[3]:
                    return parts[3]
        except Exception:
            pass
        return fallback_region

    def _create_anthropic_model(self) -> Any:
        """Create a direct Anthropic API model."""
        from agno.models.anthropic import Claude as DirectClaude

        config = self._config
        model_kwargs: dict[str, Any] = {
            "id": config.model_id,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
        }

        if config.api_key:
            model_kwargs["api_key"] = config.api_key

        logger.info(f"Creating Anthropic model: {config.model_id}")
        return DirectClaude(**model_kwargs)

    def _create_openai_model(self) -> Any:
        """Create an OpenAI model."""
        try:
            from agno.models.openai import OpenAIChat
        except ImportError as e:
            raise ImportError(
                "OpenAI provider requires the 'openai' package. Install it with: pip install openai"
            ) from e

        config = self._config
        model_kwargs: dict[str, Any] = {
            "id": config.model_id,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
        }

        if config.api_key:
            model_kwargs["api_key"] = config.api_key

        logger.info(f"Creating OpenAI model: {config.model_id}")
        return OpenAIChat(**model_kwargs)

    def _create_azure_model(self) -> Any:
        """Create an Azure OpenAI model."""
        try:
            from agno.models.azure import AzureOpenAI
        except ImportError as e:
            raise ImportError(
                "Azure provider requires the 'openai' package. Install it with: pip install openai"
            ) from e

        config = self._config
        model_kwargs: dict[str, Any] = {
            "id": config.model_id,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
        }

        if config.api_key:
            model_kwargs["api_key"] = config.api_key

        logger.info(f"Creating Azure OpenAI model: {config.model_id}")
        return AzureOpenAI(**model_kwargs)

    def _create_google_model(self) -> Any:
        """
        Create a Google Vertex AI model.

        Automatically selects the correct Agno model class based on the model ID:
        - Claude models (model_id starts with "claude") use agno.models.vertexai.claude
        - All other models use agno.models.google.Gemini

        Uses Vertex AI with Application Default Credentials (ADC):
        - Works with GKE Workload Identity
        - Auto-detects project_id from ADC or metadata service
        - Auto-detects location from zone, with override option

        Raises:
            ValueError: If project_id or location cannot be determined
            ImportError: If required packages are not installed
        """
        config = self._config
        is_claude = config.model_id.lower().startswith("claude")

        # Auto-detect GCP project using the metadata manager
        project_id = config.google_project_id or self._gcp_metadata_manager.get_project()

        if not project_id:
            raise ValueError(
                "Google provider requires a project ID. "
                "Set GOOGLE_CLOUD_PROJECT environment variable."
            )

        # Location sources:
        # 1. DCAF_GOOGLE_MODEL_LOCATION env var (override)
        # 2. Auto-detect from zone via metadata manager
        location = None
        location_source = None

        if os.environ.get("DCAF_GOOGLE_MODEL_LOCATION"):
            location = os.environ.get("DCAF_GOOGLE_MODEL_LOCATION")
            location_source = "DCAF_GOOGLE_MODEL_LOCATION env var"
        else:
            detected = self._gcp_metadata_manager.get_location()
            if detected:
                location = detected
                location_source = "auto-detected from zone"

        if not location:
            raise ValueError(
                "Google provider requires a model location. "
                "Set DCAF_GOOGLE_MODEL_LOCATION environment variable. "
                "See https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations "
                "for available regions (e.g., us-central1, us-east5)."
            )

        logger.info(f"GCP model location: {location} ({location_source})")

        if is_claude:
            return self._create_vertex_claude_model(project_id=project_id, location=location)

        return self._create_vertex_gemini_model(project_id=project_id, location=location)

    def _create_vertex_claude_model(self, *, project_id: str, location: str) -> Any:
        """
        Create a Claude model via Google Vertex AI.

        Uses agno.models.vertexai.claude for Anthropic Claude models hosted
        on Vertex AI. Authentication is handled via Application Default
        Credentials (ADC), same as the Gemini path.

        Args:
            project_id: GCP project ID
            location: GCP region (e.g., us-east5)

        Raises:
            ImportError: If agno vertex AI claude package is not installed
        """
        try:
            from agno.models.vertexai.claude import Claude as VertexClaude
        except ImportError as e:
            raise ImportError(
                "Google provider with Claude models requires the "
                "'anthropic[vertex]' package. "
                "Install it with: pip install 'anthropic[vertex]'"
            ) from e

        config = self._config

        model_kwargs: dict[str, Any] = {
            "id": config.model_id,
            "project_id": project_id,
            "region": location,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
        }

        logger.info(
            f"Creating Vertex AI Claude model: {config.model_id} "
            f"(project={project_id}, region={location})"
        )

        return VertexClaude(**model_kwargs)

    def _create_vertex_gemini_model(self, *, project_id: str, location: str) -> Any:
        """
        Create a Gemini model via Google Vertex AI.

        Args:
            project_id: GCP project ID
            location: GCP region (e.g., us-central1)

        Raises:
            ImportError: If google-generativeai is not installed
        """
        try:
            from agno.models.google import Gemini
        except ImportError as e:
            raise ImportError(
                "Google provider requires the 'google-generativeai' package. "
                "Install it with: pip install google-generativeai"
            ) from e

        config = self._config

        model_kwargs: dict[str, Any] = {
            "id": config.model_id,
            "max_output_tokens": config.max_tokens,
            "temperature": config.temperature,
            "vertexai": True,
            "project_id": project_id,
            "location": location,
        }

        logger.info(
            f"Creating Vertex AI Gemini model: {config.model_id} "
            f"(project={project_id}, location={location})"
        )

        return Gemini(**model_kwargs)

    def _create_ollama_model(self) -> Any:
        """Create a local Ollama model."""
        try:
            from agno.models.ollama import Ollama
        except ImportError as e:
            raise ImportError(
                "Ollama provider requires the 'ollama' package. "
                "Install it with: pip install ollama\n"
                "Also ensure Ollama is running: https://ollama.ai/"
            ) from e

        config = self._config
        model_kwargs: dict[str, Any] = {"id": config.model_id}

        if config.temperature is not None:
            model_kwargs["options"] = {"temperature": config.temperature}

        logger.info(f"Creating Ollama model: {config.model_id}")
        return Ollama(**model_kwargs)

    async def cleanup(self) -> None:
        """Clean up any resources (sessions, connections)."""
        self._model = None
        self._async_session = None
