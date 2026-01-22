"""
Agno adapter implementing the AgentRuntime port.

This adapter integrates with the Agno SDK (https://docs.agno.com/) to provide
agent orchestration capabilities using various LLM providers (Bedrock, Anthropic, etc.).

The Agno SDK provides:
- Multi-model support (Claude, GPT, etc.)
- Tool execution with confirmation flows
- Streaming responses
- Session management

This adapter incorporates production-proven patterns for Bedrock compatibility,
including message history filtering and parallel tool execution workarounds.
"""

import logging
import os
from collections.abc import AsyncIterator
from typing import Any

# Agno SDK imports
from agno.agent import Agent as AgnoAgent
from agno.tools import tool as agno_tool_decorator
from agno.utils.log import set_log_level_to_debug, set_log_level_to_info

from ....application.dto.responses import (
    AgentResponse,
    StreamEvent,
)
from ....application.ports.mcp_protocol import MCPToolLike
from .gcp_metadata import GCPMetadataManager, get_default_gcp_metadata_manager
from .message_converter import AgnoMessageConverter
from .model_factory import AgnoModelFactory, ModelConfig
from .response_converter import AgnoMetrics, AgnoResponseConverter
from .tool_converter import AgnoToolConverter
from .types import DEFAULT_MAX_TOKENS, DEFAULT_MODEL_ID, DEFAULT_PROVIDER

logger = logging.getLogger(__name__)


def _sync_agno_log_level() -> None:
    """
    Sync Agno's debug mode with DCAF's logging level.

    This enables unified logging control via Python's standard LOG_LEVEL:
    - DEBUG (10): Enable Agno debug mode with level=2 (verbose)
    - INFO (20) or higher: Disable Agno debug mode (INFO level only)

    This is called once during AgnoAdapter initialization to ensure both
    DCAF and Agno logging are controlled by the same environment variable.
    """
    root_logger = logging.getLogger()
    current_level = root_logger.level

    if current_level <= logging.DEBUG:
        # Enable Agno debug mode with maximum verbosity
        set_log_level_to_debug(level=2)
        logger.debug(
            f"Agno debug mode enabled (level=2) - Python log level is DEBUG ({current_level})"
        )
    else:
        # Disable Agno debug mode (INFO level)
        set_log_level_to_info()
        logger.debug(
            f"Agno debug mode disabled (INFO only) - Python log level is {logging.getLevelName(current_level)} ({current_level})"
        )


class AgnoAdapter:
    """
    Adapts the Agno SDK to our AgentRuntime port.

    This adapter translates between our domain model and the Agno SDK,
    enabling the use of Agno for agent orchestration while keeping
    all Agno-specific code isolated in this module.

    Features:
        - Synchronous and async invocation (run/arun)
        - Async streaming responses
        - Tool conversion with requires_confirmation mapping
        - Message history filtering for Bedrock compatibility
        - Parallel tool execution workaround
        - Metrics extraction and logging

    Production Workarounds:
        - Message history is filtered to remove tool-related messages
        - Strict user/assistant alternation is enforced
        - Parallel tool calls are limited to prevent Bedrock bugs
        - System prompt includes single-tool instruction

    Example:
        adapter = AgnoAdapter(
            model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            provider="bedrock",
            aws_profile="my-profile",
        )

        # Invoke the agent (async - runs in FastAPI context)
        response = await adapter.invoke(
            messages=conversation.messages,
            tools=[kubectl_tool, aws_tool],
            system_prompt="You are a helpful assistant.",
        )
    """

    # Environment variable defaults
    DEFAULT_TOOL_CALL_LIMIT = 1  # Prevent parallel tool execution bug

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        provider: str = DEFAULT_PROVIDER,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = 0.1,  # Lower for more deterministic responses
        # AWS-specific configuration
        aws_profile: str | None = None,
        aws_region: str | None = None,
        aws_access_key: str | None = None,
        aws_secret_key: str | None = None,
        # Generic API key (for non-AWS providers like OpenAI, Anthropic)
        api_key: str | None = None,
        # Google Vertex AI configuration
        google_project_id: str | None = None,
        google_location: str | None = None,
        gcp_metadata_manager: GCPMetadataManager | None = None,
        # Model configuration (for caching, etc.)
        model_config: dict[str, Any] | None = None,
        # Behavior flags
        tool_call_limit: int | None = None,
        disable_history: bool = False,
        disable_tool_filtering: bool = False,
        **kwargs: Any,
    ) -> None:
        """
        Initialize the Agno adapter.

        Args:
            model_id: The model identifier.
                      For Bedrock: "anthropic.claude-3-sonnet-20240229-v1:0"
                      For Anthropic: "claude-3-sonnet-20240229"

            provider: The model provider. Supported values:
                      - "bedrock": AWS Bedrock (Claude via AWS)
                      - "anthropic": Direct Anthropic API
                      - "openai": OpenAI API
                      - "azure": Azure OpenAI
                      - "google": Google AI (Gemini)
                      - "ollama": Local Ollama server

            max_tokens: Maximum tokens in response (default 4096)
            temperature: Sampling temperature 0.0 to 1.0 (default 0.1)

            aws_profile: AWS profile name to use (from ~/.aws/credentials)
            aws_region: AWS region to use (falls back to AWS_REGION env var)
            aws_access_key: AWS access key ID (optional, prefer profile)
            aws_secret_key: AWS secret access key (optional, prefer profile)

            api_key: API key for OpenAI, Anthropic providers

            google_project_id: Google Cloud project ID (auto-detected if not set)
            google_location: Google Cloud region (auto-detected, defaults to us-central1)
            gcp_metadata_manager: Custom GCPMetadataManager instance for testing

            model_config: Configuration dict for model features (e.g., caching)
            tool_call_limit: Max concurrent tool calls (default 1 to avoid bug)
            disable_history: If True, don't pass message history
            disable_tool_filtering: If True, skip tool message filtering

            **kwargs: Additional arguments passed to the model
        """
        self._model_id = model_id
        self._provider = provider.lower()
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._model_config = model_config or {}

        # AWS configuration
        self._aws_profile = aws_profile
        self._aws_region = aws_region or os.getenv("AWS_REGION", "us-west-2")
        self._aws_access_key = aws_access_key
        self._aws_secret_key = aws_secret_key

        # Generic API key (OpenAI, Anthropic)
        self._api_key = api_key

        # Google Vertex AI configuration (auto-detected if not set)
        self._google_project_id = google_project_id
        self._google_location = google_location
        self._gcp_metadata_manager = gcp_metadata_manager or get_default_gcp_metadata_manager()

        # Behavior flags (can also be set via env vars)
        self._tool_call_limit = tool_call_limit or int(
            os.getenv("AGNO_TOOL_CALL_LIMIT", str(self.DEFAULT_TOOL_CALL_LIMIT))
        )
        self._disable_history = disable_history or (
            os.getenv("AGNO_DISABLE_HISTORY", "false").lower() == "true"
        )
        self._disable_tool_filtering = disable_tool_filtering or (
            os.getenv("DISABLE_TOOL_FILTERING", "false").lower() == "true"
        )

        self._extra_config = kwargs

        # Converters for messages, tools, and responses
        self._tool_converter = AgnoToolConverter()
        self._message_converter = AgnoMessageConverter()
        self._response_converter = AgnoResponseConverter()

        # System prompt parts for caching
        self._static_system: str | None = None
        self._dynamic_system: str | None = None

        # Create model factory (model created lazily)
        self._model_factory = AgnoModelFactory(
            config=ModelConfig(
                model_id=model_id,
                provider=provider.lower(),
                max_tokens=max_tokens,
                temperature=temperature,
                aws_profile=aws_profile,
                aws_region=self._aws_region,
                aws_access_key=aws_access_key,
                aws_secret_key=aws_secret_key,
                api_key=api_key,
                google_project_id=google_project_id,
                google_location=google_location,
                cache_system_prompt=self._model_config.get("cache_system_prompt", False),
            ),
            gcp_metadata_manager=self._gcp_metadata_manager,
        )

        # Sync Agno's logging with DCAF's logging level
        _sync_agno_log_level()

        logger.info(
            f"AgnoAdapter initialized: model={model_id}, provider={provider}, "
            f"region={self._aws_region}, tool_limit={self._tool_call_limit}, "
            f"cache_enabled={self._model_config.get('cache_system_prompt', False)}"
        )

    # =========================================================================
    # Async Interface (FastAPI runs in async context)
    # =========================================================================

    async def invoke(
        self,
        messages: list[Any],
        tools: list[Any],
        system_prompt: str | None = None,
        static_system: str | None = None,
        dynamic_system: str | None = None,
        platform_context: dict[str, Any] | None = None,
    ) -> AgentResponse:
        """
        Invoke the agent asynchronously.

        Args:
            messages: List of message objects (domain Message or dicts)
            tools: List of dcaf Tool objects
            system_prompt: Optional system prompt
            static_system: Static portion of system prompt (for caching)
            dynamic_system: Dynamic portion of system prompt (not cached)
            platform_context: Optional platform context to inject into tools

        Returns:
            AgentResponse with the result
        """
        # 🔍 LOG RUNTIME INVOKE PARAMETERS - What DCAF is passing to Agno adapter
        logger.debug("🔍 AGENT RUNTIME INVOKE PARAMETERS:")
        logger.debug(f"  Messages: {len(messages)} total")
        for i, msg in enumerate(messages):
            if hasattr(msg, "role"):
                role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                content = getattr(msg, "text", None) or getattr(msg, "content", None)
                logger.debug(f"    [{i}] {role}: {content}")
            elif isinstance(msg, dict):
                logger.debug(f"    [{i}] {msg.get('role')}: {msg.get('content')}")
            else:
                logger.debug(f"    [{i}] {type(msg).__name__}: {msg}")
        logger.debug(f"  Tools: {len(tools)} total")
        for tool in tools:
            tool_name = getattr(tool, "name", None) or getattr(tool, "__name__", str(tool))
            logger.debug(f"    - {tool_name}")
        logger.debug(
            f"  System Prompt: {system_prompt[:200] + '...' if system_prompt and len(system_prompt) > 200 else system_prompt}"
        )
        logger.debug(
            f"  Static System: {static_system[:200] + '...' if static_system and len(static_system) > 200 else static_system}"
        )
        logger.debug(
            f"  Dynamic System: {dynamic_system[:200] + '...' if dynamic_system and len(dynamic_system) > 200 else dynamic_system}"
        )
        logger.debug(f"  Platform Context: {platform_context}")

        # Store system prompt parts for model creation (if using caching)
        self._static_system = static_system
        self._dynamic_system = dynamic_system

        # Create the Agno agent with tools (context injected into tool wrappers)
        agno_agent = await self._create_agent_async(
            tools, system_prompt, platform_context=platform_context
        )

        # Build the message list for Agno
        messages_to_send = self._build_message_list(messages)

        # Extract tracing parameters from platform_context
        tracing_kwargs = self._extract_tracing_kwargs(platform_context)

        try:
            logger.info(f"Agno: Sending {len(messages_to_send)} messages to arun()")
            if tracing_kwargs:
                logger.info(f"Agno: Tracing context: {tracing_kwargs}")

            # Run the Agno agent asynchronously with tracing parameters
            run_output = await agno_agent.arun(messages_to_send, **tracing_kwargs)

            # Generate a conversation ID (prefer our run_id if provided)
            conversation_id = tracing_kwargs.get("run_id") or getattr(run_output, "run_id", None) or ""

            # Extract and log metrics
            metrics = self._response_converter.extract_metrics(run_output)
            if metrics:
                logger.info(
                    f"Agno Metrics: tokens={metrics.total_tokens} "
                    f"(in={metrics.input_tokens}, out={metrics.output_tokens}), "
                    f"duration={metrics.duration:.3f}s"
                )

            # Convert the RunOutput to our AgentResponse
            return self._response_converter.convert_run_output(
                run_output=run_output,
                conversation_id=conversation_id,
                metrics=metrics,
                tracing_context=tracing_kwargs,
            )

        except Exception as e:
            logger.error(f"Agno invocation failed: {e}", exc_info=True)
            raise

    async def invoke_stream(
        self,
        messages: list[Any],
        tools: list[Any],
        system_prompt: str | None = None,
        static_system: str | None = None,
        dynamic_system: str | None = None,
        platform_context: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """
        Invoke the agent with async streaming response.

        Args:
            messages: List of message objects
            tools: List of dcaf Tool objects
            system_prompt: Optional system prompt
            static_system: Static portion of system prompt (for caching)
            dynamic_system: Dynamic portion of system prompt (not cached)
            platform_context: Optional platform context to inject into tools

        Yields:
            StreamEvent objects for real-time updates
        """
        # 🔍 LOG RUNTIME INVOKE PARAMETERS - What DCAF is passing to Agno adapter (STREAMING)
        logger.debug("🔍 AGENT RUNTIME INVOKE PARAMETERS (STREAMING):")
        logger.debug(f"  Messages: {len(messages)} total")
        for i, msg in enumerate(messages):
            if hasattr(msg, "role"):
                role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                content = getattr(msg, "text", None) or getattr(msg, "content", None)
                logger.debug(f"    [{i}] {role}: {content}")
            elif isinstance(msg, dict):
                logger.debug(f"    [{i}] {msg.get('role')}: {msg.get('content')}")
            else:
                logger.debug(f"    [{i}] {type(msg).__name__}: {msg}")
        logger.debug(f"  Tools: {len(tools)} total")
        for tool in tools:
            tool_name = getattr(tool, "name", None) or getattr(tool, "__name__", str(tool))
            logger.debug(f"    - {tool_name}")
        logger.debug(
            f"  System Prompt: {system_prompt[:200] + '...' if system_prompt and len(system_prompt) > 200 else system_prompt}"
        )
        logger.debug(
            f"  Static System: {static_system[:200] + '...' if static_system and len(static_system) > 200 else static_system}"
        )
        logger.debug(
            f"  Dynamic System: {dynamic_system[:200] + '...' if dynamic_system and len(dynamic_system) > 200 else dynamic_system}"
        )
        logger.debug(f"  Platform Context: {platform_context}")

        # Store system prompt parts for model creation (if using caching)
        self._static_system = static_system
        self._dynamic_system = dynamic_system

        # Create the Agno agent with tools and streaming enabled (context injected)
        agno_agent = await self._create_agent_async(
            tools, system_prompt, stream=True, platform_context=platform_context
        )

        # Build the message list for Agno
        messages_to_send = self._build_message_list(messages)

        # Extract tracing parameters from platform_context
        tracing_kwargs = self._extract_tracing_kwargs(platform_context)
        if tracing_kwargs:
            logger.info(f"Agno: Streaming with tracing context: {tracing_kwargs}")

        try:
            yield StreamEvent.message_start()

            # Run with streaming and tracing parameters
            async for event in agno_agent.arun(messages_to_send, stream=True, **tracing_kwargs):
                stream_event = self._response_converter.convert_stream_event(event)
                if stream_event:
                    yield stream_event

                # Capture final output if available
                if hasattr(event, "run_output") and event.run_output:
                    # Prefer our run_id if provided
                    conv_id = tracing_kwargs.get("run_id") or getattr(event.run_output, "run_id", "") or ""
                    response = self._response_converter.convert_run_output(
                        run_output=event.run_output,
                        conversation_id=conv_id,
                        tracing_context=tracing_kwargs,
                    )
                    yield StreamEvent.message_end(response)
                    return

            # If we got here without a final response, yield a basic end
            yield StreamEvent.message_end(
                AgentResponse(
                    conversation_id=tracing_kwargs.get("run_id", ""),
                    text="",
                    is_complete=True,
                )
            )

        except Exception as e:
            logger.error(f"Agno streaming failed: {e}", exc_info=True)
            yield StreamEvent.error(str(e))

    # =========================================================================
    # Message Building (Bedrock-Compatible)
    # =========================================================================

    def _build_message_list(
        self,
        messages: list[Any],
        current_message: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Build a Bedrock-compatible message list from conversation history.

        This implements critical workarounds for Bedrock compatibility:
        1. Filters out tool-related messages (prevents ValidationException)
        2. Ensures first message is from 'user'
        3. Ensures strict user/assistant alternation

        Args:
            messages: List of message objects or dicts
            current_message: Optional current user message to append

        Returns:
            List of message dicts ready for Agno's arun()
        """
        if self._disable_history:
            logger.info("Agno: History disabled via AGNO_DISABLE_HISTORY=true")
            messages = []

        messages_to_send = []
        skipped_count = 0

        if self._disable_tool_filtering:
            logger.warning("⚠️ Agno: Tool filtering DISABLED (bug reproduction mode)")

        # Convert and filter messages
        for msg in messages:
            # Handle both domain Message objects and dicts
            if hasattr(msg, "role"):
                role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                content = getattr(msg, "text", None) or getattr(msg, "content", None)
            elif isinstance(msg, dict):
                role = msg.get("role")
                content = msg.get("content")
            else:
                continue

            # Apply filtering (unless disabled)
            if not self._disable_tool_filtering:
                # Skip messages with no content (tool-only messages)
                if content is None:
                    skipped_count += 1
                    continue

                # Skip empty string content
                if isinstance(content, str) and not content.strip():
                    skipped_count += 1
                    continue

                # Skip messages where content is a list (Bedrock tool blocks)
                # These are toolUse (assistant) or toolResult (user) messages
                if isinstance(content, list):
                    skipped_count += 1
                    logger.debug(f"Agno: Skipping tool-related message (role={role})")
                    continue

            messages_to_send.append({"role": role, "content": content})

        if skipped_count > 0:
            logger.info(f"Agno: Filtered out {skipped_count} tool-related messages from history")

        # Apply validation only if filtering is enabled
        if not self._disable_tool_filtering:
            messages_to_send = self._validate_message_structure(messages_to_send)

        # If a current message is provided, append it
        if current_message:
            # Ensure we don't have consecutive user messages
            if messages_to_send and messages_to_send[-1].get("role") == "user":
                logger.warning(
                    "Agno: Last history message is 'user' - removing to allow current message"
                )
                messages_to_send.pop()

            messages_to_send.append({"role": "user", "content": current_message})

        return messages_to_send

    def _validate_message_structure(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Validate and fix message structure for Bedrock compatibility.

        Bedrock requirements:
        1. First message must be from 'user'
        2. Messages must alternate between user/assistant

        Args:
            messages: List of message dicts

        Returns:
            Validated message list
        """
        # Remove leading assistant messages (Bedrock requires user first)
        while messages and messages[0].get("role") != "user":
            removed = messages.pop(0)
            logger.warning(
                f"Agno: Removed leading {removed.get('role')} message (Bedrock requires user first)"
            )

        # Validate alternation
        validated_messages = []
        last_role = None

        for msg in messages:
            role = msg.get("role")
            if role == last_role:
                # Consecutive same-role messages - skip to maintain alternation
                logger.warning(f"Agno: Skipping consecutive {role} message to maintain alternation")
                continue
            validated_messages.append(msg)
            last_role = role

        if len(validated_messages) != len(messages):
            logger.info(
                f"Agno: Fixed alternation - {len(messages)} -> {len(validated_messages)} messages"
            )

        return validated_messages

    # =========================================================================
    # Agent Creation
    # =========================================================================

    async def _create_agent_async(
        self,
        tools: list[Any],
        system_prompt: str | None = None,
        stream: bool = False,
        platform_context: dict[str, Any] | None = None,
    ) -> AgnoAgent:
        """
        Create an Agno Agent with async session.

        Args:
            tools: List of dcaf Tool objects
            system_prompt: Optional system prompt
            stream: Whether streaming is enabled
            platform_context: Optional platform context to inject into tools

        Returns:
            Configured AgnoAgent
        """
        # Create the model with async session
        model = await self._get_or_create_model_async()

        # Convert tools to Agno format (with context injection for tools that need it)
        agno_tools = self._convert_tools_to_agno(tools, platform_context)

        # WORKAROUND: Prepend instruction to prevent parallel tool calls
        # This is necessary because Agno has a bug handling multiple toolUse blocks
        modified_prompt = self._get_modified_system_prompt(system_prompt)

        logger.info(
            f"Agno: Creating agent with {len(agno_tools)} tools "
            f"(stream={stream}, tool_limit={self._tool_call_limit})"
        )

        # Create the agent
        agent = AgnoAgent(
            model=model,
            instructions=modified_prompt,
            tools=agno_tools if agno_tools else None,
            stream=stream,
            tool_call_limit=self._tool_call_limit,
        )

        return agent

    def _get_modified_system_prompt(self, system_prompt: str | None) -> str:
        """
        Modify system prompt to include single-tool instruction.

        This workaround prevents the model from requesting multiple tool calls
        in a single response, which causes Bedrock validation errors.

        Args:
            system_prompt: Original system prompt

        Returns:
            Modified system prompt with single-tool instruction
        """
        single_tool_instruction = (
            "IMPORTANT: You must call tools ONE AT A TIME. Never request multiple tool calls "
            "in a single response. Wait for each tool result before calling the next tool.\n\n"
        )

        if system_prompt:
            return single_tool_instruction + system_prompt
        return single_tool_instruction

    # =========================================================================
    # Model Creation (delegated to ModelFactory)
    # =========================================================================

    async def _get_or_create_model_async(self) -> Any:
        """
        Get or create the Agno model with async session.

        Delegates to the ModelFactory for provider-specific model creation.
        For Bedrock, this uses aioboto3 for true async AWS calls.

        Returns:
            An Agno model instance
        """
        # Update model factory's caching config with current system prompts
        self._model_factory._config.static_system = self._static_system
        self._model_factory._config.dynamic_system = self._dynamic_system

        return await self._model_factory.create_model()

    # =========================================================================
    # Tool Conversion
    # =========================================================================

    def _convert_tools_to_agno(
        self,
        tools: list[Any],
        platform_context: dict[str, Any] | None = None,
    ) -> list[Any]:
        """
        Convert dcaf Tools to Agno-compatible tool format.

        Uses Agno's @tool decorator with the full JSON schema for proper
        integration. The schema is critical for the LLM to understand
        tool parameters, types, constraints (enums), and descriptions.

        For tools that require platform_context, this method creates wrapper
        functions that automatically inject the context when Agno executes them.
        This bridges the gap between interceptor-set context and tool execution.

        Also handles DCAF MCPTool instances by extracting the underlying
        Agno Toolkit and passing it through directly.

        Args:
            tools: List of dcaf Tool objects or MCPTool instances
            platform_context: Optional platform context to inject into tools
                             that declare a `platform_context` parameter

        Returns:
            List of Agno-compatible tools (decorated functions or Toolkits)
        """
        agno_tools = []

        for tool_obj in tools:
            # Check if this is a DCAF MCPTool instance
            # We check by class name to avoid importing dcaf.mcp in the adapter
            if self._is_dcaf_mcp_tools(tool_obj):
                # Extract the underlying Agno Toolkit and pass it through
                # auto_create=True allows Agno's Agent to handle the connection lifecycle
                # (connect before run, disconnect after run)
                agno_toolkit = tool_obj._get_agno_toolkit(auto_create=True)
                agno_tools.append(agno_toolkit)

                # Log based on whether tools are already loaded
                target = tool_obj._url or tool_obj._command
                if tool_obj.initialized:
                    tool_names = list(agno_toolkit.functions.keys())
                    logger.info(
                        f"🔌 MCP: Added pre-connected MCPTool to agent "
                        f"(target={target}, tools={tool_names})"
                    )
                else:
                    logger.info(
                        f"🔌 MCP: Added MCPTool to agent - will auto-connect "
                        f"(transport={tool_obj._transport}, target={target})"
                    )
                continue

            # Get the full tool schema including input_schema
            # This ensures enums, descriptions, and constraints are passed to the LLM
            tool_schema = self._tool_converter.to_agno(tool_obj)

            # Determine which function to wrap with Agno's decorator
            if tool_obj.requires_platform_context and platform_context is not None:
                # Create a wrapper that injects platform_context
                # IMPORTANT: We must preserve the function signature (minus platform_context)
                # so that Agno can infer the parameter schema correctly.
                import functools
                import inspect

                def create_context_wrapper(original_func: Any, ctx: Any) -> Any:
                    """Create a closure that injects platform_context while preserving signature."""

                    @functools.wraps(original_func)
                    def wrapper(*args: Any, **kwargs: Any) -> Any:
                        kwargs["platform_context"] = ctx
                        return original_func(*args, **kwargs)

                    # Copy the signature but REMOVE platform_context parameter
                    # This is what Agno will see when it inspects the function
                    try:
                        original_sig = inspect.signature(original_func)
                        filtered_params = [
                            param
                            for name, param in original_sig.parameters.items()
                            if name != "platform_context"
                        ]
                        wrapper.__signature__ = original_sig.replace(parameters=filtered_params)  # type: ignore[attr-defined]
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            f"Could not copy signature for {original_func.__name__}: {e}"
                        )

                    return wrapper

                func_to_wrap = create_context_wrapper(tool_obj.func, platform_context)
                logger.debug(f"Tool '{tool_obj.name}' will receive platform_context injection")
            else:
                # No context needed - use the raw function
                func_to_wrap = tool_obj.func

            # Use Agno's @tool decorator
            # Note: Agno infers parameter schema from function signature automatically.
            # We only pass name and description - 'parameters' is NOT a valid Agno arg.
            decorated_tool = agno_tool_decorator(
                name=tool_schema["name"],
                description=tool_schema["description"],
            )(func_to_wrap)

            agno_tools.append(decorated_tool)

            logger.debug(
                f"Converted tool '{tool_obj.name}' with schema: "
                f"{list(tool_schema['input_schema'].get('properties', {}).keys())}"
            )

        return agno_tools

    def _is_dcaf_mcp_tools(self, obj: Any) -> bool:
        """
        Check if an object is a DCAF MCPTool instance.

        Uses the MCPToolLike Protocol for type-safe detection.

        Args:
            obj: The object to check

        Returns:
            True if this is a DCAF MCPTool instance
        """
        return isinstance(obj, MCPToolLike)

    # =========================================================================
    # Tracing Support
    # =========================================================================

    def _extract_tracing_kwargs(
        self,
        platform_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Extract tracing parameters from platform_context for Agno SDK.

        Agno's Agent.arun() accepts these optional tracing parameters:
        - run_id: Unique identifier for this execution run
        - session_id: Session identifier for grouping related runs
        - user_id: User identifier for tracking

        These are extracted from the platform_context dict if present.

        Args:
            platform_context: Platform context dict that may contain tracing fields

        Returns:
            Dict of tracing kwargs to pass to agno_agent.arun()
        """
        if not platform_context:
            return {}

        tracing_kwargs: dict[str, Any] = {}

        # Map platform_context tracing fields to Agno's arun() parameters
        if platform_context.get("run_id"):
            tracing_kwargs["run_id"] = platform_context["run_id"]
        if platform_context.get("session_id"):
            tracing_kwargs["session_id"] = platform_context["session_id"]
        if platform_context.get("user_id"):
            tracing_kwargs["user_id"] = platform_context["user_id"]

        # Agno also supports a metadata dict for additional context
        # We can pass request_id and other custom fields here
        metadata: dict[str, Any] = {}
        if platform_context.get("request_id"):
            metadata["request_id"] = platform_context["request_id"]
        if platform_context.get("tenant_id"):
            metadata["tenant_id"] = platform_context["tenant_id"]
        if platform_context.get("tenant_name"):
            metadata["tenant_name"] = platform_context["tenant_name"]

        if metadata:
            tracing_kwargs["metadata"] = metadata

        return tracing_kwargs

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def cleanup(self) -> None:
        """Clean up cached resources."""
        await self._model_factory.cleanup()
        logger.info("Agno: Cleaned up cached resources")

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def model_id(self) -> str:
        """Get the configured model ID."""
        return self._model_id

    @property
    def provider(self) -> str:
        """Get the configured provider."""
        return self._provider
