"""
LLM Layer - Direct LLM calls with automatic provider/model configuration.

This module provides a unified interface for making direct LLM calls across
all supported providers (Bedrock, Anthropic, OpenAI, Azure, Google, Ollama)
without requiring the full agent orchestration machinery.

The LLM layer is the single source of truth for model creation and
configuration. It is consumed by:

1. **Direct callers** (e.g., SlackResponseRouter) via ``LLM.invoke()``
2. **Agent orchestration** (e.g., AgnoAdapter) via ``LLM.get_model()``

Quick Start::

    from dcaf.core import LLM, create_llm

    # Create from environment variables (DCAF_PROVIDER, DCAF_MODEL, etc.)
    llm = create_llm()

    # Or with explicit configuration
    llm = create_llm(provider="google", model="gemini-2.0-flash")

    # Make a direct call (sync)
    response = llm.invoke(
        messages=[{"role": "user", "content": "Hello"}],
        system_prompt="You are helpful.",
    )
    print(response.text)
    print(response.tool_calls)
    print(response.usage)

    # Async call
    response = await llm.ainvoke(
        messages=[{"role": "user", "content": "Hello"}],
    )
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from agno.models.message import Message as AgnoMessage
from agno.models.response import ModelResponse

from .adapters.outbound.agno.gcp_metadata import get_default_gcp_metadata_manager
from .adapters.outbound.agno.model_factory import AgnoModelFactory, ModelConfig
from .config import (
    PROVIDER_MODEL_DEFAULTS,
    EnvVars,
    get_env,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Response type
# =============================================================================


@dataclass
class LLMResponse:
    """
    Response from a direct LLM call.

    This is the base response type for all LLM interactions. It carries the
    raw model output without any agent or protocol-specific concerns.

    ``AgentResponse`` extends this class to add agent-level fields
    (approvals, sessions, conversation tracking).

    Attributes:
        text: The model's text response, or None if the model only returned
              tool calls.
        tool_calls: Raw tool calls from the model. Each entry is a dict with
                    at minimum ``name`` and ``input`` keys.
        usage: Token usage metrics (``input_tokens``, ``output_tokens``,
               ``total_tokens``).
        raw: The underlying Agno ``ModelResponse`` for callers who need
             full access to provider-specific fields.
    """

    text: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    raw: ModelResponse | None = field(default=None, repr=False)


# =============================================================================
# LLM class
# =============================================================================


class LLM:
    """
    Direct LLM interface with automatic provider/model configuration.

    Wraps Agno's model classes to provide a clean, provider-agnostic API for
    making LLM calls. All provider detection, credential resolution, and model
    instantiation is handled internally via ``AgnoModelFactory``.

    Args:
        provider: Provider name (``bedrock``, ``anthropic``, ``openai``,
                  ``azure``, ``google``, ``ollama``).
        model: Model identifier (e.g., ``gemini-2.0-flash``,
               ``anthropic.claude-3-5-haiku-20241022-v1:0``).
        temperature: Sampling temperature (0.0–1.0).
        max_tokens: Maximum tokens in the response.
        **provider_kwargs: Provider-specific configuration passed through to
            ``AgnoModelFactory``. Supported keys include:
            - ``aws_profile``, ``aws_region``, ``aws_access_key``,
              ``aws_secret_key`` (for Bedrock)
            - ``api_key`` (for Anthropic, OpenAI, Azure)
            - ``google_project_id``, ``google_location`` (for Google)

    Example::

        llm = LLM(provider="bedrock", model="us.anthropic.claude-3-5-haiku-20241022-v1:0")
        response = llm.invoke(
            messages=[{"role": "user", "content": "What is 2+2?"}],
            system_prompt="Answer concisely.",
            max_tokens=100,
        )
        print(response.text)
    """

    def __init__(
        self,
        provider: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        **provider_kwargs: Any,
    ) -> None:
        self._provider = provider.lower()
        self._model_id = model
        self._temperature = temperature
        self._max_tokens = max_tokens

        # Build the model config for the factory
        config = ModelConfig(
            model_id=model,
            provider=self._provider,
            max_tokens=max_tokens,
            temperature=temperature,
            aws_profile=provider_kwargs.get("aws_profile"),
            aws_region=provider_kwargs.get("aws_region"),
            aws_access_key=provider_kwargs.get("aws_access_key"),
            aws_secret_key=provider_kwargs.get("aws_secret_key"),
            api_key=provider_kwargs.get("api_key"),
            google_project_id=provider_kwargs.get("google_project_id"),
            google_location=provider_kwargs.get("google_location"),
        )

        gcp_metadata = provider_kwargs.get(
            "gcp_metadata_manager", get_default_gcp_metadata_manager()
        )

        self._model_factory = AgnoModelFactory(
            config=config,
            gcp_metadata_manager=gcp_metadata,
        )

        logger.info(
            f"LLM initialized: provider={self._provider}, model={model}, "
            f"temperature={temperature}, max_tokens={max_tokens}"
        )

    @property
    def model_id(self) -> str:
        """The model identifier."""
        return self._model_id

    @property
    def provider(self) -> str:
        """The provider name."""
        return self._provider

    async def get_model(self) -> Any:
        """
        Get the underlying Agno model instance.

        This is used by ``AgnoAdapter`` to feed the model into ``AgnoAgent``
        for full agent orchestration. The model is created lazily and cached.

        Returns:
            An Agno model instance (e.g., ``AwsBedrock``, ``Gemini``, etc.)
        """
        return await self._model_factory.create_model()

    async def ainvoke(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """
        Make an async direct LLM call.

        This is a single-shot call — no tool execution loop, no agent
        orchestration. The model is invoked once and the response is returned.

        Args:
            messages: List of message dicts with ``role`` and ``content`` keys.
            system_prompt: Optional system prompt.
            tools: Optional list of tool schemas (dicts with ``name``,
                   ``description``, ``input_schema``/``parameters``).
            tool_choice: Tool choice strategy (``auto``, ``any``, or
                         ``{"name": "tool_name"}``).
            max_tokens: Override max tokens for this call.
            temperature: Override temperature for this call.

        Returns:
            ``LLMResponse`` with text, tool_calls, usage, and raw response.
        """
        model = await self.get_model()

        # Apply per-call overrides
        if max_tokens is not None:
            model.max_tokens = max_tokens
        elif self._max_tokens:
            model.max_tokens = self._max_tokens

        if temperature is not None:
            model.temperature = temperature

        # Build Agno message list
        agno_messages = self._build_messages(messages, system_prompt)

        # Create an empty assistant message placeholder (required by Agno's invoke)
        assistant_message = AgnoMessage(role="assistant")

        logger.info(
            f"LLM.ainvoke: {len(agno_messages)} messages, "
            f"tools={len(tools) if tools else 0}, "
            f"model={self._model_id}"
        )

        # Call the model directly — single invocation, no agent loop
        model_response: ModelResponse = await model.ainvoke(
            messages=agno_messages,
            assistant_message=assistant_message,
            tools=tools,
            tool_choice=tool_choice,
        )

        return self._convert_response(model_response)

    def invoke(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """
        Make a synchronous direct LLM call.

        Convenience wrapper around :meth:`ainvoke` for non-async contexts
        (e.g., ``SlackResponseRouter``).

        Args:
            messages: List of message dicts with ``role`` and ``content`` keys.
            system_prompt: Optional system prompt.
            tools: Optional list of tool schemas.
            tool_choice: Tool choice strategy.
            max_tokens: Override max tokens for this call.
            temperature: Override temperature for this call.

        Returns:
            ``LLMResponse`` with text, tool_calls, usage, and raw response.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an async context — use a thread to avoid blocking
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run,
                    self.ainvoke(
                        messages=messages,
                        system_prompt=system_prompt,
                        tools=tools,
                        tool_choice=tool_choice,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    ),
                )
                return future.result()
        else:
            return asyncio.run(
                self.ainvoke(
                    messages=messages,
                    system_prompt=system_prompt,
                    tools=tools,
                    tool_choice=tool_choice,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            )

    async def cleanup(self) -> None:
        """Release any resources held by the underlying model factory."""
        await self._model_factory.cleanup()

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _build_messages(
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
    ) -> list[AgnoMessage]:
        """Convert simple dicts to Agno Message objects."""
        agno_messages: list[AgnoMessage] = []

        # Prepend system prompt as a system message
        if system_prompt:
            agno_messages.append(AgnoMessage(role="system", content=system_prompt))

        for msg in messages:
            agno_messages.append(
                AgnoMessage(
                    role=msg["role"],
                    content=msg.get("content", ""),
                )
            )

        return agno_messages

    @staticmethod
    def _convert_response(model_response: ModelResponse) -> LLMResponse:
        """Convert Agno ModelResponse to LLMResponse."""
        # Extract text content
        text = None
        content = model_response.content
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif isinstance(block, dict) and "text" in block:
                    text_parts.append(block["text"])
                elif hasattr(block, "text"):
                    text_parts.append(str(block.text))
            if text_parts:
                text = " ".join(text_parts)

        # Extract tool calls — normalize to [{name, input}, ...]
        tool_calls: list[dict[str, Any]] = []
        for tc in model_response.tool_calls or []:
            name = tc.get("function", {}).get("name", tc.get("name", ""))
            arguments = tc.get("function", {}).get("arguments", tc.get("input", {}))

            # Arguments may be a JSON string
            if isinstance(arguments, str):
                import contextlib
                import json

                with contextlib.suppress(json.JSONDecodeError, ValueError):
                    arguments = json.loads(arguments)

            tool_calls.append({"name": name, "input": arguments})

        # Extract usage metrics
        usage: dict[str, int] = {}
        if model_response.input_tokens is not None:
            usage["input_tokens"] = model_response.input_tokens
        if model_response.output_tokens is not None:
            usage["output_tokens"] = model_response.output_tokens
        if model_response.total_tokens is not None:
            usage["total_tokens"] = model_response.total_tokens

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            usage=usage,
            raw=model_response,
        )


# =============================================================================
# Factory function
# =============================================================================


def create_llm(
    provider: str | None = None,
    model: str | None = None,
    **overrides: Any,
) -> LLM:
    """
    Create an LLM from environment variables.

    Reads ``DCAF_PROVIDER``, ``DCAF_MODEL``, and provider-specific env vars
    to configure the LLM automatically. Any parameter can be overridden
    explicitly.

    Args:
        provider: Override provider (default: from ``DCAF_PROVIDER``).
        model: Override model (default: from ``DCAF_MODEL``).
        **overrides: Additional kwargs passed to ``LLM()``. Supported keys:
            ``temperature``, ``max_tokens``, ``aws_profile``, ``aws_region``,
            ``api_key``, ``google_project_id``, ``google_location``, etc.

    Returns:
        A configured ``LLM`` instance.

    Example::

        # Everything from environment
        llm = create_llm()

        # Override provider and model
        llm = create_llm(provider="google", model="gemini-2.0-flash")

        # Override with custom temperature
        llm = create_llm(temperature=0.0, max_tokens=200)
    """
    resolved_provider = provider or get_env(EnvVars.PROVIDER) or "bedrock"
    resolved_model = (
        model or get_env(EnvVars.MODEL) or PROVIDER_MODEL_DEFAULTS.get(resolved_provider, "")
    )

    # Build kwargs from environment, then apply overrides
    kwargs: dict[str, Any] = {}

    # Temperature and max_tokens
    if "temperature" not in overrides:
        temp = get_env(EnvVars.TEMPERATURE, cast=float)
        if temp is not None:
            kwargs["temperature"] = temp
    if "max_tokens" not in overrides:
        max_tok = get_env(EnvVars.MAX_TOKENS, cast=int)
        if max_tok is not None:
            kwargs["max_tokens"] = max_tok

    # Provider-specific env vars
    if resolved_provider == "bedrock":
        if profile := get_env(EnvVars.AWS_PROFILE):
            kwargs.setdefault("aws_profile", profile)
        if region := get_env(EnvVars.AWS_REGION):
            kwargs.setdefault("aws_region", region)
        if access_key := get_env(EnvVars.AWS_ACCESS_KEY_ID):
            kwargs.setdefault("aws_access_key", access_key)
        if secret_key := get_env(EnvVars.AWS_SECRET_ACCESS_KEY):
            kwargs.setdefault("aws_secret_key", secret_key)
    elif resolved_provider == "anthropic":
        if api_key := get_env(EnvVars.ANTHROPIC_API_KEY):
            kwargs.setdefault("api_key", api_key)
    elif resolved_provider == "openai":
        if api_key := get_env(EnvVars.OPENAI_API_KEY):
            kwargs.setdefault("api_key", api_key)
    elif resolved_provider == "azure":
        if api_key := get_env(EnvVars.AZURE_OPENAI_API_KEY):
            kwargs.setdefault("api_key", api_key)
    elif resolved_provider == "google":
        if project_id := get_env(EnvVars.GOOGLE_PROJECT_ID):
            kwargs.setdefault("google_project_id", project_id)
        if location := get_env(EnvVars.GOOGLE_MODEL_LOCATION):
            kwargs.setdefault("google_location", location)

    # Apply explicit overrides last
    kwargs.update(overrides)

    logger.info(f"create_llm: provider={resolved_provider}, model={resolved_model}")

    return LLM(
        provider=resolved_provider,
        model=resolved_model,
        **kwargs,
    )
