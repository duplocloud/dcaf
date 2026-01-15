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

from typing import List, Optional, Iterator, Any, Dict, Callable, AsyncIterator
import logging
import os
from dataclasses import dataclass, field

# Agno SDK imports
from agno.agent import Agent as AgnoAgent
from agno.models.aws import AwsBedrock
from agno.models.message import Message as AgnoMessage
from agno.tools import tool as agno_tool_decorator
from agno.run.agent import RunStatus

from .tool_converter import AgnoToolConverter
from .message_converter import AgnoMessageConverter
from .types import DEFAULT_MODEL_ID, DEFAULT_PROVIDER, DEFAULT_MAX_TOKENS
from .caching_bedrock import CachingAwsBedrock
from ....domain.entities import Message
from ....application.dto.responses import AgentResponse, ToolCallDTO, StreamEvent, DataDTO

logger = logging.getLogger(__name__)

# Cache for GCP metadata (fetched once per process)
_gcp_metadata_cache: dict = {}
_GCP_METADATA_FETCH_ATTEMPTED = False


def _fetch_gcp_metadata() -> None:
    """
    Fetch GCP project and location from metadata service (once per process).
    
    Stores results in _gcp_metadata_cache and sets GOOGLE_CLOUD_PROJECT env var.
    Called once, caches results for subsequent calls.
    """
    global _GCP_METADATA_FETCH_ATTEMPTED, _gcp_metadata_cache
    
    if _GCP_METADATA_FETCH_ATTEMPTED:
        return
    
    _GCP_METADATA_FETCH_ATTEMPTED = True
    logger.info("GCP auto-detect: Starting GCP metadata detection for Vertex AI")
    
    # Try google.auth.default() first for project ID
    logger.info("GCP auto-detect: Attempting google.auth.default() for project ID...")
    try:
        import google.auth
        credentials, detected_project = google.auth.default()
        logger.info(f"GCP auto-detect: google.auth.default() returned project={detected_project}, credentials={type(credentials).__name__}")
        if detected_project:
            _gcp_metadata_cache["project_id"] = detected_project
            os.environ["GOOGLE_CLOUD_PROJECT"] = detected_project
            logger.info(f"GCP auto-detect: SUCCESS - Set GOOGLE_CLOUD_PROJECT={detected_project} (from ADC)")
        else:
            logger.warning("GCP auto-detect: google.auth.default() returned credentials but no project ID")
    except ImportError:
        logger.warning("GCP auto-detect: google-auth package not installed, skipping ADC detection")
    except Exception as e:
        logger.warning(f"GCP auto-detect: google.auth.default() failed: {type(e).__name__}: {e}")
    
    # Try metadata service for project (if not found via ADC) and location
    logger.info("GCP auto-detect: Attempting GCP metadata service...")
    try:
        import requests
        headers = {"Metadata-Flavor": "Google"}
        timeout = 2
        base_url = "http://metadata.google.internal/computeMetadata/v1"
        
        # Fetch project ID if not already found
        if "project_id" not in _gcp_metadata_cache:
            url = f"{base_url}/project/project-id"
            logger.info(f"GCP auto-detect: Fetching project ID from {url}")
            try:
                resp = requests.get(url, headers=headers, timeout=timeout)
                logger.info(f"GCP auto-detect: Project metadata response status={resp.status_code}")
                if resp.ok:
                    project_id = resp.text.strip()
                    _gcp_metadata_cache["project_id"] = project_id
                    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
                    logger.info(f"GCP auto-detect: SUCCESS - Set GOOGLE_CLOUD_PROJECT={project_id} (from metadata)")
                else:
                    logger.warning(f"GCP auto-detect: Project metadata returned {resp.status_code}")
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"GCP auto-detect: Cannot connect to metadata service (not on GCP?): {e}")
            except requests.exceptions.Timeout:
                logger.warning("GCP auto-detect: Metadata service timed out for project")
        
        # Fetch zone/location
        url = f"{base_url}/instance/zone"
        logger.info(f"GCP auto-detect: Fetching zone from {url}")
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            logger.info(f"GCP auto-detect: Zone metadata response status={resp.status_code}")
            if resp.ok:
                # Zone format: "projects/123456/zones/us-central1-a"
                zone_raw = resp.text.strip()
                zone = zone_raw.split("/")[-1]
                location = "-".join(zone.split("-")[:-1])
                _gcp_metadata_cache["location"] = location
                logger.info(f"GCP auto-detect: Detected location={location} (from zone={zone})")
            else:
                logger.warning(f"GCP auto-detect: Zone metadata returned {resp.status_code}")
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"GCP auto-detect: Cannot connect to metadata service for zone: {e}")
        except requests.exceptions.Timeout:
            logger.warning("GCP auto-detect: Metadata service timed out for zone")
                    
    except ImportError:
        logger.warning("GCP auto-detect: requests package not installed, skipping metadata detection")
    except Exception as e:
        logger.warning(f"GCP auto-detect: Metadata service error: {type(e).__name__}: {e}")
    
    # Log summary
    project = _gcp_metadata_cache.get("project_id")
    location = _gcp_metadata_cache.get("location")
    if project and location:
        logger.info(f"GCP auto-detect: Complete - project={project}, location={location}")
    elif project:
        logger.info(f"GCP auto-detect: Partial - project={project}, location=not detected")
    else:
        logger.error("GCP auto-detect: FAILED - Could not detect project ID. Set GOOGLE_CLOUD_PROJECT env var.")


def _get_gcp_project() -> Optional[str]:
    """Get GCP project ID from cache or env var."""
    # Check env var first (may have been set externally)
    existing = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if existing:
        return existing
    
    # Ensure metadata has been fetched
    _fetch_gcp_metadata()
    
    return _gcp_metadata_cache.get("project_id")


def _get_gcp_location() -> Optional[str]:
    """Get GCP location from cache (auto-detected from zone)."""
    # Ensure metadata has been fetched
    _fetch_gcp_metadata()
    
    return _gcp_metadata_cache.get("location")


@dataclass
class AgnoMetrics:
    """Metrics from an Agno run."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    duration: float = 0.0
    time_to_first_token: Optional[float] = None
    response_timer: Optional[float] = None


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
        
        # Async invocation (preferred)
        response = await adapter.ainvoke(
            messages=conversation.messages,
            tools=[kubectl_tool, aws_tool],
            system_prompt="You are a helpful assistant.",
        )
        
        # Or sync invocation
        response = adapter.invoke(
            messages=conversation.messages,
            tools=[kubectl_tool, aws_tool],
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
        aws_profile: Optional[str] = None,
        aws_region: Optional[str] = None,
        aws_access_key: Optional[str] = None,
        aws_secret_key: Optional[str] = None,
        # Generic API key (for non-AWS providers like OpenAI, Anthropic)
        api_key: Optional[str] = None,
        # Google Vertex AI configuration
        google_project_id: Optional[str] = None,
        google_location: Optional[str] = None,
        # Model configuration (for caching, etc.)
        model_config: Optional[Dict[str, Any]] = None,
        # Behavior flags
        tool_call_limit: Optional[int] = None,
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
        
        # Converters for messages and tools
        self._tool_converter = AgnoToolConverter()
        self._message_converter = AgnoMessageConverter()
        
        # Cached model and session (created lazily)
        self._model = None
        self._async_session = None
        
        # System prompt parts for caching
        self._static_system = None
        self._dynamic_system = None
        
        logger.info(
            f"AgnoAdapter initialized: model={model_id}, provider={provider}, "
            f"region={self._aws_region}, tool_limit={self._tool_call_limit}, "
            f"cache_enabled={self._model_config.get('cache_system_prompt', False)}"
        )
    
    # =========================================================================
    # Synchronous Interface
    # =========================================================================
    
    def invoke(
        self,
        messages: List[Any],
        tools: List[Any],
        system_prompt: Optional[str] = None,
        static_system: Optional[str] = None,
        dynamic_system: Optional[str] = None,
        platform_context: Optional[Dict[str, Any]] = None,
    ) -> AgentResponse:
        """
        Invoke the agent synchronously.
        
        Note: For async contexts (FastAPI, etc.), use ainvoke() instead.
        
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
        import asyncio
        
        # Run the async version in an event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're already in an async context - this shouldn't happen
                # but we'll handle it gracefully
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.ainvoke(messages, tools, system_prompt, static_system, dynamic_system, platform_context)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.ainvoke(messages, tools, system_prompt, static_system, dynamic_system, platform_context)
                )
        except RuntimeError:
            # No event loop - create one
            return asyncio.run(self.ainvoke(messages, tools, system_prompt, static_system, dynamic_system, platform_context))
    
    def invoke_stream(
        self,
        messages: List[Any],
        tools: List[Any],
        system_prompt: Optional[str] = None,
        static_system: Optional[str] = None,
        dynamic_system: Optional[str] = None,
        platform_context: Optional[Dict[str, Any]] = None,
    ) -> Iterator[StreamEvent]:
        """
        Invoke with synchronous streaming.
        
        Note: For async contexts, use ainvoke_stream() instead.
        
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
        import asyncio
        
        async def collect_events():
            events = []
            async for event in self.ainvoke_stream(messages, tools, system_prompt, static_system, dynamic_system, platform_context):
                events.append(event)
            return events
        
        # Run async and yield collected events
        try:
            events = asyncio.run(collect_events())
            for event in events:
                yield event
        except Exception as e:
            logger.error(f"Streaming failed: {e}", exc_info=True)
            yield StreamEvent.error(str(e))
    
    # =========================================================================
    # Async Interface (Preferred)
    # =========================================================================
    
    async def ainvoke(
        self,
        messages: List[Any],
        tools: List[Any],
        system_prompt: Optional[str] = None,
        static_system: Optional[str] = None,
        dynamic_system: Optional[str] = None,
        platform_context: Optional[Dict[str, Any]] = None,
    ) -> AgentResponse:
        """
        Invoke the agent asynchronously.
        
        This is the preferred method for async contexts (FastAPI, etc.)
        as it doesn't block the event loop.
        
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
        # Store system prompt parts for model creation (if using caching)
        self._static_system = static_system
        self._dynamic_system = dynamic_system
        
        # Create the Agno agent with tools (context injected into tool wrappers)
        agno_agent = await self._create_agent_async(tools, system_prompt, platform_context=platform_context)
        
        # Build the message list for Agno
        messages_to_send = self._build_message_list(messages)
        
        try:
            logger.info(f"Agno: Sending {len(messages_to_send)} messages to arun()")
            
            # Run the Agno agent asynchronously
            run_output = await agno_agent.arun(messages_to_send)
            
            # Generate a conversation ID
            conversation_id = getattr(run_output, 'run_id', None) or ""
            
            # Extract and log metrics
            metrics = self._extract_metrics(run_output)
            if metrics:
                logger.info(
                    f"📊 Agno Metrics: tokens={metrics.total_tokens} "
                    f"(in={metrics.input_tokens}, out={metrics.output_tokens}), "
                    f"duration={metrics.duration:.3f}s"
                )
            
            # Convert the RunOutput to our AgentResponse
            return self._convert_run_output_to_response(
                run_output=run_output,
                conversation_id=conversation_id,
                metrics=metrics,
            )
            
        except Exception as e:
            logger.error(f"Agno invocation failed: {e}", exc_info=True)
            raise
    
    async def ainvoke_stream(
        self,
        messages: List[Any],
        tools: List[Any],
        system_prompt: Optional[str] = None,
        static_system: Optional[str] = None,
        dynamic_system: Optional[str] = None,
        platform_context: Optional[Dict[str, Any]] = None,
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
        # Store system prompt parts for model creation (if using caching)
        self._static_system = static_system
        self._dynamic_system = dynamic_system
        
        # Create the Agno agent with tools and streaming enabled (context injected)
        agno_agent = await self._create_agent_async(tools, system_prompt, stream=True, platform_context=platform_context)
        
        # Build the message list for Agno
        messages_to_send = self._build_message_list(messages)
        
        try:
            yield StreamEvent.message_start()
            
            # Run with streaming
            async for event in agno_agent.arun(messages_to_send, stream=True):
                stream_event = self._convert_agno_stream_event(event)
                if stream_event:
                    yield stream_event
                
                # Capture final output if available
                if hasattr(event, 'run_output') and event.run_output:
                    response = self._convert_run_output_to_response(
                        run_output=event.run_output,
                        conversation_id=getattr(event.run_output, 'run_id', '') or "",
                    )
                    yield StreamEvent.message_end(response)
                    return
            
            # If we got here without a final response, yield a basic end
            yield StreamEvent.message_end(AgentResponse(
                conversation_id="",
                text="",
                is_complete=True,
            ))
            
        except Exception as e:
            logger.error(f"Agno streaming failed: {e}", exc_info=True)
            yield StreamEvent.error(str(e))
    
    # =========================================================================
    # Message Building (Bedrock-Compatible)
    # =========================================================================
    
    def _build_message_list(
        self,
        messages: List[Any],
        current_message: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
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
            if hasattr(msg, 'role'):
                role = msg.role.value if hasattr(msg.role, 'value') else str(msg.role)
                content = getattr(msg, 'text', None) or getattr(msg, 'content', None)
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
                logger.warning("Agno: Last history message is 'user' - removing to allow current message")
                messages_to_send.pop()
            
            messages_to_send.append({"role": "user", "content": current_message})
        
        return messages_to_send
    
    def _validate_message_structure(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
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
                f"Agno: Removed leading {removed.get('role')} message "
                "(Bedrock requires user first)"
            )
        
        # Validate alternation
        validated_messages = []
        last_role = None
        
        for msg in messages:
            role = msg.get("role")
            if role == last_role:
                # Consecutive same-role messages - skip to maintain alternation
                logger.warning(
                    f"Agno: Skipping consecutive {role} message to maintain alternation"
                )
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
        tools: List[Any],
        system_prompt: Optional[str] = None,
        stream: bool = False,
        platform_context: Optional[Dict[str, Any]] = None,
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
    
    def _get_modified_system_prompt(self, system_prompt: Optional[str]) -> str:
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
    # Model Creation
    # =========================================================================
    
    async def _get_or_create_model_async(self):
        """
        Get or create the Agno model with async session.
        
        For Bedrock, this uses aioboto3 for true async AWS calls.
        
        Returns:
            An Agno model instance
        """
        if self._model is not None:
            return self._model
        
        # Route to the appropriate provider
        if self._provider == "bedrock":
            self._model = await self._create_bedrock_model_async()
        elif self._provider == "anthropic":
            self._model = self._create_anthropic_model()
        elif self._provider == "openai":
            self._model = self._create_openai_model()
        elif self._provider == "azure":
            self._model = self._create_azure_model()
        elif self._provider == "google":
            self._model = self._create_google_model()
        elif self._provider == "ollama":
            self._model = self._create_ollama_model()
        else:
            raise ValueError(
                f"Unsupported provider: '{self._provider}'. "
                f"Supported providers: bedrock, anthropic, openai, azure, google, ollama"
            )
        
        return self._model
    
    async def _create_bedrock_model_async(self):
        """
        Create an AWS Bedrock model with async session.
        
        Uses aioboto3 for true async AWS calls, which is critical for
        non-blocking operation in async contexts like FastAPI.
        
        Returns:
            Agno AwsBedrock model configured with async session
        """
        import aioboto3
        
        # Infer region from model ID if it's an ARN
        region = self._infer_region_from_model_id(self._model_id, self._aws_region)
        
        # Create async session with profile if specified
        if self._aws_profile:
            logger.info(f"Agno: Using AWS profile '{self._aws_profile}' (region: {region})")
            async_session = aioboto3.Session(
                region_name=region,
                profile_name=self._aws_profile,
            )
        else:
            # Use default credential chain (env vars, instance profile, etc.)
            logger.info(f"Agno: Using default AWS credentials (region: {region})")
            async_session = aioboto3.Session(region_name=region)
        
        # Cache the session
        self._async_session = async_session
        
        # Check if caching is enabled via model_config
        cache_enabled = self._model_config.get("cache_system_prompt", False)
        
        # Log configuration
        logger.info(
            f"Agno: Initialized Bedrock model {self._model_id} "
            f"(temperature={self._temperature}, max_tokens={self._max_tokens}, "
            f"cache_system_prompt={cache_enabled})"
        )
        
        # Create the appropriate model
        if cache_enabled:
            logger.info("Using CachingAwsBedrock (temporary until Agno adds native support)")
            return CachingAwsBedrock(
                id=self._model_id,
                aws_region=region,
                async_session=async_session,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                cache_system_prompt=True,
                static_system=self._static_system,
                dynamic_system=self._dynamic_system,
            )
        else:
            return AwsBedrock(
                id=self._model_id,
                aws_region=region,
                async_session=async_session,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
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
    
    def _create_anthropic_model(self):
        """Create a direct Anthropic API model."""
        from agno.models.anthropic import Claude as DirectClaude
        
        model_kwargs = {
            "id": self._model_id,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        
        if self._api_key:
            model_kwargs["api_key"] = self._api_key
        
        logger.info(f"Creating Anthropic model: {self._model_id}")
        return DirectClaude(**model_kwargs)
    
    def _create_openai_model(self):
        """Create an OpenAI model."""
        try:
            from agno.models.openai import OpenAIChat
        except ImportError as e:
            raise ImportError(
                "OpenAI provider requires the 'openai' package. "
                "Install it with: pip install openai"
            ) from e
        
        model_kwargs = {
            "id": self._model_id,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        
        if self._api_key:
            model_kwargs["api_key"] = self._api_key
        
        logger.info(f"Creating OpenAI model: {self._model_id}")
        return OpenAIChat(**model_kwargs)
    
    def _create_azure_model(self):
        """Create an Azure OpenAI model."""
        try:
            from agno.models.azure import AzureOpenAI
        except ImportError as e:
            raise ImportError(
                "Azure provider requires the 'openai' package. "
                "Install it with: pip install openai"
            ) from e
        
        model_kwargs = {
            "id": self._model_id,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        
        if self._api_key:
            model_kwargs["api_key"] = self._api_key
        
        logger.info(f"Creating Azure OpenAI model: {self._model_id}")
        return AzureOpenAI(**model_kwargs)
    
    def _create_google_model(self):
        """
        Create a Google Vertex AI (Gemini) model.
        
        Always uses Vertex AI with Application Default Credentials (ADC):
        - Works with GKE Workload Identity
        - Auto-detects project_id from ADC or metadata service
        - Auto-detects location from zone, with override option
        
        Location sources:
        1. DCAF_GOOGLE_MODEL_LOCATION env var (override for when zone doesn't have Gemini)
        2. Auto-detected from instance zone
        
        Raises ValueError if location cannot be determined.
        
        Note: Your cluster might be in a region (e.g., us-west2) where Gemini
        isn't available. Set DCAF_GOOGLE_MODEL_LOCATION to override.
        """
        try:
            from agno.models.google import Gemini
        except ImportError as e:
            raise ImportError(
                "Google provider requires the 'google-generativeai' package. "
                "Install it with: pip install google-generativeai"
            ) from e
        
        # Auto-detect GCP project
        project_id = self._google_project_id or _get_gcp_project()
        
        if not project_id:
            raise ValueError(
                "Google provider requires a project ID. "
                "Set GOOGLE_CLOUD_PROJECT environment variable."
            )
        
        # Location sources:
        # 1. DCAF_GOOGLE_MODEL_LOCATION env var (override)
        # 2. Auto-detect from zone
        # No fallback - fail if we can't determine location
        location = None
        location_source = None
        
        if os.environ.get("DCAF_GOOGLE_MODEL_LOCATION"):
            location = os.environ.get("DCAF_GOOGLE_MODEL_LOCATION")
            location_source = "DCAF_GOOGLE_MODEL_LOCATION env var"
        else:
            # Try auto-detect from zone (uses cached metadata)
            detected = _get_gcp_location()
            if detected:
                location = detected
                location_source = "auto-detected from zone"
        
        if not location:
            raise ValueError(
                "Google provider requires a model location. "
                "Set DCAF_GOOGLE_MODEL_LOCATION environment variable. "
                "See https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations "
                "for regions where Gemini is available (e.g., us-central1, us-west1)."
            )
        
        logger.info(f"GCP model location: {location} ({location_source})")
        
        model_kwargs = {
            "id": self._model_id,
            "max_output_tokens": self._max_tokens,
            "temperature": self._temperature,
            "vertexai": True,
            "project_id": project_id,
            "location": location,
        }
        
        logger.info(
            f"Creating Vertex AI Gemini model: {self._model_id} "
            f"(project={project_id}, location={location})"
        )
        
        return Gemini(**model_kwargs)
    
    def _create_ollama_model(self):
        """Create a local Ollama model."""
        try:
            from agno.models.ollama import Ollama
        except ImportError as e:
            raise ImportError(
                "Ollama provider requires the 'ollama' package. "
                "Install it with: pip install ollama\n"
                "Also ensure Ollama is running: https://ollama.ai/"
            ) from e
        
        model_kwargs = {"id": self._model_id}
        
        if self._temperature is not None:
            model_kwargs["options"] = {"temperature": self._temperature}
        
        logger.info(f"Creating Ollama model: {self._model_id}")
        return Ollama(**model_kwargs)
    
    # =========================================================================
    # Tool Conversion
    # =========================================================================
    
    def _convert_tools_to_agno(
        self, 
        tools: List[Any],
        platform_context: Optional[Dict[str, Any]] = None,
    ) -> List[Callable]:
        """
        Convert dcaf Tools to Agno-compatible tool format.
        
        Uses Agno's @tool decorator with the full JSON schema for proper
        integration. The schema is critical for the LLM to understand
        tool parameters, types, constraints (enums), and descriptions.
        
        For tools that require platform_context, this method creates wrapper
        functions that automatically inject the context when Agno executes them.
        This bridges the gap between interceptor-set context and tool execution.
        
        Args:
            tools: List of dcaf Tool objects
            platform_context: Optional platform context to inject into tools
                             that declare a `platform_context` parameter
            
        Returns:
            List of Agno-decorated tool functions with proper schemas
        """
        agno_tools = []
        
        for tool_obj in tools:
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
                
                def create_context_wrapper(original_func, ctx):
                    """Create a closure that injects platform_context while preserving signature."""
                    @functools.wraps(original_func)
                    def wrapper(*args, **kwargs):
                        kwargs['platform_context'] = ctx
                        return original_func(*args, **kwargs)
                    
                    # Copy the signature but REMOVE platform_context parameter
                    # This is what Agno will see when it inspects the function
                    try:
                        original_sig = inspect.signature(original_func)
                        filtered_params = [
                            param for name, param in original_sig.parameters.items()
                            if name != 'platform_context'
                        ]
                        wrapper.__signature__ = original_sig.replace(parameters=filtered_params)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not copy signature for {original_func.__name__}: {e}")
                    
                    return wrapper
                
                func_to_wrap = create_context_wrapper(tool_obj.func, platform_context)
                logger.debug(
                    f"Tool '{tool_obj.name}' will receive platform_context injection"
                )
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
    
    # =========================================================================
    # Response Conversion
    # =========================================================================
    
    def _extract_metrics(self, run_output: Any) -> Optional[AgnoMetrics]:
        """
        Extract metrics from Agno's RunOutput.
        
        Args:
            run_output: The RunOutput from Agno
            
        Returns:
            AgnoMetrics or None if no metrics available
        """
        if not hasattr(run_output, 'metrics') or not run_output.metrics:
            return None
        
        m = run_output.metrics
        return AgnoMetrics(
            input_tokens=getattr(m, 'input_tokens', 0) or 0,
            output_tokens=getattr(m, 'output_tokens', 0) or 0,
            total_tokens=getattr(m, 'total_tokens', 0) or 0,
            duration=getattr(m, 'duration', 0.0) or 0.0,
            time_to_first_token=getattr(m, 'time_to_first_token', None),
            response_timer=getattr(m, 'response_timer', None),
        )
    
    def _convert_run_output_to_response(
        self,
        run_output: Any,
        conversation_id: str,
        metrics: Optional[AgnoMetrics] = None,
    ) -> AgentResponse:
        """
        Convert Agno's RunOutput to our AgentResponse.
        
        Args:
            run_output: The RunOutput from Agno
            conversation_id: ID for this conversation
            metrics: Optional extracted metrics
            
        Returns:
            AgentResponse with appropriate fields set
        """
        # Extract text content using Agno's built-in method if available
        text = None
        if hasattr(run_output, 'get_content_as_string'):
            # Use Agno's official method to get string content
            try:
                raw_content = run_output.get_content_as_string()
                logger.debug(f"Agno get_content_as_string() returned: {repr(raw_content)[:200]}")
                
                # Check if the result looks like JSON (list/dict) and extract text
                if raw_content:
                    # If it starts with [ or {, it's JSON-serialized structured content
                    if raw_content.startswith('[') or raw_content.startswith('{'):
                        # Try to parse and extract text
                        import json
                        try:
                            parsed = json.loads(raw_content)
                            if isinstance(parsed, list):
                                # Extract text from content blocks
                                text_parts = []
                                for block in parsed:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        text_parts.append(block.get("text", ""))
                                    elif isinstance(block, str):
                                        text_parts.append(block)
                                text = " ".join(text_parts) if text_parts else None
                            elif isinstance(parsed, dict) and "text" in parsed:
                                text = parsed["text"]
                            else:
                                # Not a recognized format, use as-is if it looks like text
                                text = None
                        except json.JSONDecodeError:
                            # Not valid JSON, use as-is
                            text = raw_content
                    else:
                        # Plain text content
                        text = raw_content
            except Exception as e:
                logger.warning(f"Agno get_content_as_string() failed: {e}")
                text = None
        
        # Fallback: direct content access if get_content_as_string didn't work
        if text is None and hasattr(run_output, 'content') and run_output.content:
            logger.debug(f"Agno: Falling back to direct content access")
            if isinstance(run_output.content, str):
                text = run_output.content
            elif isinstance(run_output.content, list):
                # Content is a list of content blocks
                text_parts = []
                for block in run_output.content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif "text" in block:
                            text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                    elif hasattr(block, 'text'):
                        text_parts.append(str(block.text))
                text = " ".join(text_parts) if text_parts else None
            elif hasattr(run_output.content, 'text'):
                text = str(run_output.content.text)
        
        # Debug: Check if text has [] appended (bug tracing)
        if text and '[]' in text:
            logger.warning(f"🚨 Extracted text contains '[]': {repr(text)[:200]}")
        
        # Extract tool calls
        tool_calls = []
        has_pending = False
        
        if hasattr(run_output, 'tools') and run_output.tools:
            for tool_exec in run_output.tools:
                needs_confirmation = (
                    getattr(tool_exec, 'requires_confirmation', False) and
                    not getattr(tool_exec, 'confirmed', False)
                )
                
                tool_call_dto = ToolCallDTO(
                    id=getattr(tool_exec, 'tool_call_id', '') or "",
                    name=getattr(tool_exec, 'tool_name', '') or "",
                    input=getattr(tool_exec, 'tool_args', {}) or {},
                    requires_approval=needs_confirmation,
                    status="pending" if needs_confirmation else "executed",
                )
                tool_calls.append(tool_call_dto)
                
                if needs_confirmation:
                    has_pending = True
            
            # Log tool execution
            logger.info(f"🔧 Agno Tools: Executed {len(tool_calls)} tool call(s)")
            for i, tc in enumerate(tool_calls, 1):
                logger.debug(f"  Tool {i}: {tc.name}")
        
        # Check if run is paused
        is_paused = getattr(run_output, 'status', None) == RunStatus.paused
        if is_paused:
            has_pending = True
        
        # Determine completeness
        is_complete = (
            getattr(run_output, 'status', None) == RunStatus.completed 
            and not has_pending
        )
        
        # Wrap tool calls in DataDTO (AgentResponse expects data, not tool_calls)
        data = DataDTO(tool_calls=tool_calls)
        
        return AgentResponse(
            conversation_id=conversation_id,
            text=text,
            data=data,
            has_pending_approvals=has_pending,
            is_complete=is_complete,
        )
    
    def _convert_agno_stream_event(self, agno_event: Any) -> Optional[StreamEvent]:
        """
        Convert an Agno streaming event to our StreamEvent format.
        
        Args:
            agno_event: An event from Agno's streaming run
            
        Returns:
            StreamEvent or None if event should be skipped
        """
        event_type = type(agno_event).__name__
        
        if event_type in ("RunContentEvent", "RunContent"):
            content = getattr(agno_event, 'content', '')
            if content:
                return StreamEvent.text_delta(str(content))
            return None
        
        elif event_type in ("RunStartedEvent", "RunStarted"):
            return None  # Already sent message_start
        
        elif event_type in ("RunCompletedEvent", "RunCompleted"):
            return None  # Handled via run_output
        
        elif event_type in ("RunErrorEvent", "RunError"):
            error_msg = getattr(agno_event, 'error', 'Unknown error')
            return StreamEvent.error(str(error_msg))
        
        elif event_type in ("ToolCallStartedEvent", "ToolCallStarted"):
            tool_name = getattr(agno_event, 'tool_name', '')
            tool_id = getattr(agno_event, 'tool_call_id', '')
            return StreamEvent.tool_use_start(
                tool_call_id=tool_id,
                tool_name=tool_name,
            )
        
        elif event_type in ("ToolCallCompletedEvent", "ToolCallCompleted"):
            return StreamEvent(
                event_type=StreamEvent.StreamEventType.TOOL_USE_END,
                index=0,
            )
        
        return None
    
    # =========================================================================
    # Cleanup
    # =========================================================================
    
    async def cleanup(self):
        """Clean up cached resources."""
        self._async_session = None
        self._model = None
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
