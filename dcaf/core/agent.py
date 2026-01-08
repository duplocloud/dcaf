"""
Simple Agent API - The primary entry point for DCAF.

This module provides a dead-simple interface for creating and running agents.
All the Clean Architecture complexity is hidden behind this simple facade.

Example:
    from dcaf.core import Agent, ChatMessage
    
    @tool(description="List Kubernetes pods")
    def list_pods(namespace: str = "default") -> str:
        return kubectl(f"get pods -n {namespace}")
    
    agent = Agent(tools=[list_pods])
    response = agent.run(messages=[
        ChatMessage.user("What pods are running?")
    ])
    print(response.text)

Example with Interceptors:
    from dcaf.core import Agent, LLMRequest, LLMResponse
    
    # Add context before sending to LLM
    def add_tenant_info(request: LLMRequest) -> LLMRequest:
        tenant = request.context.get("tenant_name", "unknown")
        request.add_system_context(f"User's tenant: {tenant}")
        return request
    
    # Clean response before returning to user
    def redact_secrets(response: LLMResponse) -> LLMResponse:
        response.text = response.text.replace("secret123", "[REDACTED]")
        return response
    
    agent = Agent(
        tools=[list_pods],
        request_interceptors=add_tenant_info,
        response_interceptors=redact_secrets,
    )
"""

from dataclasses import dataclass, field
from typing import Callable, Any, Iterator, Union, Optional
import asyncio
import logging

from .models import ChatMessage, normalize_messages
from .domain.entities import Conversation, ToolCall
from .domain.events import DomainEvent
from .application.services import AgentService, ApprovalService
from .application.dto import AgentRequest, AgentResponse
from .adapters.loader import load_adapter, list_frameworks
from .adapters.outbound.persistence import InMemoryConversationRepository

# Import interceptor types and utilities
from .interceptors import (
    LLMRequest,
    LLMResponse,
    InterceptorError,
    InterceptorPipeline,
    RequestInterceptorInput,
    ResponseInterceptorInput,
    normalize_interceptors,
    create_request_from_messages,
    create_response_from_text,
)

# Import stream event types from schemas (server-side types)
from ..schemas.events import (
    StreamEvent as ServerStreamEvent,
    TextDeltaEvent,
    ToolCallsEvent,
    DoneEvent,
    ErrorEvent,
)
from ..schemas.messages import ToolCall as SchemaToolCall


logger = logging.getLogger(__name__)


# Type alias for event handlers
EventHandler = Callable[[DomainEvent], None]

# Type alias for request interceptors (for external use)
RequestInterceptor = Callable[[LLMRequest], LLMRequest]

# Type alias for response interceptors (for external use)  
ResponseInterceptor = Callable[[LLMResponse], LLMResponse]


@dataclass
class PendingToolCall:
    """
    A tool call awaiting user approval.
    
    This is a simplified view of a ToolCall for the user-facing API.
    
    Attributes:
        id: Unique identifier for this tool call
        name: Name of the tool to execute
        input: Parameters that will be passed to the tool
        description: Human-readable description of what this will do
        
    Example:
        if response.needs_approval:
            for pending in response.pending_tools:
                print(f"Tool: {pending.name}")
                print(f"Will execute with: {pending.input}")
                if confirm():
                    pending.approve()
    """
    id: str
    name: str
    input: dict
    description: str = ""
    _tool_call: ToolCall = field(repr=False, default=None)
    _conversation_id: str = field(repr=False, default="")
    _approval_service: ApprovalService = field(repr=False, default=None)
    
    def approve(self) -> None:
        """Approve this tool call for execution."""
        if self._approval_service:
            self._approval_service.approve_single(
                self._conversation_id, 
                self.id
            )
    
    def reject(self, reason: str = "User declined") -> None:
        """Reject this tool call."""
        if self._approval_service:
            self._approval_service.reject_single(
                self._conversation_id,
                self.id,
                reason
            )


@dataclass
class AgentResponse:
    """
    Response from an agent execution.
    
    Attributes:
        text: The agent's text response (if any)
        needs_approval: Whether there are pending tool calls needing approval
        pending_tools: List of tool calls awaiting approval
        conversation_id: ID of the conversation (for continuing later)
        is_complete: Whether the agent has finished (no pending approvals)
        
    Example:
        response = agent.run("Delete the failing pods")
        
        if response.needs_approval:
            print("The following actions need your approval:")
            for tool in response.pending_tools:
                print(f"  - {tool.name}: {tool.input}")
        else:
            print(response.text)
    """
    text: str | None = None
    needs_approval: bool = False
    pending_tools: list[PendingToolCall] = field(default_factory=list)
    conversation_id: str = ""
    is_complete: bool = True
    
    # Internal reference for continuing
    _agent: "Agent" = field(repr=False, default=None)
    
    def approve_all(self) -> "AgentResponse":
        """Approve all pending tool calls and continue execution."""
        if self._agent and self.pending_tools:
            return self._agent._approve_all_and_continue(self.conversation_id)
        return self
    
    def reject_all(self, reason: str = "User declined") -> "AgentResponse":
        """Reject all pending tool calls."""
        if self._agent and self.pending_tools:
            return self._agent._reject_all(self.conversation_id, reason)
        return self


class Agent:
    """
    A simple, batteries-included agent.
    
    This is the primary entry point for DCAF. It provides a clean,
    Pythonic API for creating agents with tool calling and 
    human-in-the-loop approval.
    
    BASIC USAGE:
    ============
    
        from dcaf.core import Agent
        from dcaf.tools import tool
        
        @tool(requires_approval=True)
        def delete_pod(name: str) -> str:
            '''Delete a Kubernetes pod.'''
            return kubectl(f"delete pod {name}")
        
        agent = Agent(tools=[delete_pod])
        response = agent.run(messages=[
            {"role": "user", "content": "Delete pod nginx-abc123"}
        ])
        
        if response.needs_approval:
            print("Approve deletion?")
            response = response.approve_all()
        
        print(response.text)
    
    WITH INTERCEPTORS:
    ==================
    
    Interceptors let you modify data before it goes to the LLM and
    after you receive a response. See the interceptors module for details.
    
        from dcaf.core import Agent, LLMRequest, LLMResponse
        
        def add_context(request: LLMRequest) -> LLMRequest:
            '''Add tenant info to help the AI understand the environment.'''
            tenant = request.context.get("tenant_name", "unknown")
            request.add_system_context(f"User's tenant: {tenant}")
            return request
        
        def clean_output(response: LLMResponse) -> LLMResponse:
            '''Remove any sensitive data from the response.'''
            response.text = response.text.replace("secret", "[HIDDEN]")
            return response
        
        agent = Agent(
            tools=[delete_pod],
            request_interceptors=add_context,
            response_interceptors=clean_output,
        )
    
    Args:
        tools: List of tools the agent can use. Create tools with @tool decorator.
        
        model: Model ID to use. Default is Claude 3 Sonnet on Bedrock.
               Examples:
               - Bedrock: "anthropic.claude-3-sonnet-20240229-v1:0"
               - Anthropic: "claude-3-sonnet-20240229"
               - OpenAI: "gpt-4", "gpt-4-turbo"
               - Ollama: "llama2", "mistral"
        
        provider: LLM provider to use (within the framework). Supported values
                 depend on the framework. For Agno:
                 - "bedrock": AWS Bedrock (Claude via AWS) - default
                 - "anthropic": Direct Anthropic API
                 - "openai": OpenAI API
                 - "azure": Azure OpenAI
                 - "google": Google AI (Gemini)
                 - "ollama": Local Ollama server
        
        framework: LLM orchestration framework to use. Default is "agno".
                  Frameworks are auto-discovered from dcaf/core/adapters/outbound/.
                  Available frameworks:
                  - "agno": Agno SDK (default) - supports many providers
                  - "strands": AWS Strands Agent (future)
                  - "langchain": LangChain (future)
                  
                  Adding a new framework:
                  1. Create folder: dcaf/core/adapters/outbound/{name}/
                  2. Add __init__.py with: def create_adapter(**kwargs) -> Adapter
                  3. Use: Agent(framework="{name}")
        
        system_prompt: Instructions for how the AI should behave.
                      Example: "You are a helpful Kubernetes assistant."
                      
                      Note: When using prompt caching (model_config={'cache_system_prompt': True}),
                      this static system prompt is cached for reuse across requests.
        
        system_context: Dynamic context appended to system prompt. Can be:
                       - A string: Used as-is
                       - A callable: Called with platform_context dict, returns string
                       
                       This content is NOT cached and is evaluated fresh each request.
                       This is useful for separating static instructions from runtime context
                       (tenant, namespace, user, etc.) when using prompt caching.
                       
                       Example:
                           system_context=lambda ctx: f"Tenant: {ctx.get('tenant_name')}"
        
        model_config: Configuration passed to the model adapter. Options:
                     - cache_system_prompt (bool): Enable Bedrock prompt caching.
                       Requires static system prompt ≥1024 tokens.
                       Example: model_config={'cache_system_prompt': True}
        
        high_risk_tools: Names of tools that always require approval, even if
                        the tool itself doesn't have requires_approval=True.
                        Example: ["delete_pod", "drop_database"]
        
        on_event: Callback function(s) for domain events. Useful for logging,
                 notifications, or audit trails.
                 Example: on_event=my_logger or on_event=[logger1, logger2]
        
        request_interceptors: Function(s) to run BEFORE sending to the LLM.
                             Use for adding context, validation, or logging.
                             Can be a single function or a list of functions.
                             Functions run in order (first to last).
        
        response_interceptors: Function(s) to run AFTER receiving from the LLM.
                              Use for cleaning output, redacting secrets, etc.
                              Can be a single function or a list of functions.
                              Functions run in order (first to last).
        
        on_interceptor_error: What to do if an interceptor fails unexpectedly.
                             "abort" (default): Stop and return error to user.
                             "continue": Log the error and keep going.
                             Note: InterceptorError always stops processing.
        
        aws_profile: AWS profile name from ~/.aws/credentials.
                    Only used when provider="bedrock".
                    Example: aws_profile="production"
        
        aws_region: AWS region to use (e.g., "us-east-1", "us-west-2").
                   Only used when provider="bedrock".
                   Falls back to AWS_REGION env var.
        
        aws_access_key: AWS access key ID (optional).
                       Prefer using aws_profile instead for better security.
        
        aws_secret_key: AWS secret access key (optional).
                       Prefer using aws_profile instead for better security.
        
        api_key: API key for non-AWS providers.
                Falls back to provider-specific environment variables:
                - ANTHROPIC_API_KEY for provider="anthropic"
                - OPENAI_API_KEY for provider="openai"
                - GOOGLE_API_KEY for provider="google"
        
        name: Agent name for A2A (Agent-to-Agent) protocol.
             Used as the agent's identity when exposed via A2A.
             Default: "dcaf-agent"
             Example: name="k8s-assistant"
        
        description: Agent description for A2A protocol.
                    Human-readable description of what the agent does.
                    Falls back to system_prompt if not provided.
                    Example: description="Manages Kubernetes clusters"
    
    PROVIDER EXAMPLES:
    ==================
    
        # AWS Bedrock with profile
        agent = Agent(
            provider="bedrock",
            model="anthropic.claude-3-sonnet-20240229-v1:0",
            aws_profile="production",
            aws_region="us-west-2",
        )
        
        # Direct Anthropic API
        agent = Agent(
            provider="anthropic",
            model="claude-3-sonnet-20240229",
            api_key="sk-ant-...",  # or set ANTHROPIC_API_KEY
        )
        
        # OpenAI
        agent = Agent(
            provider="openai",
            model="gpt-4",
            api_key="sk-...",  # or set OPENAI_API_KEY
        )
        
        # Local Ollama
        agent = Agent(
            provider="ollama",
            model="llama2",
        )
    """
    
    def __init__(
        self,
        tools: list | None = None,
        model: str = "anthropic.claude-3-sonnet-20240229-v1:0",
        provider: str = "bedrock",
        framework: str = "agno",  # LLM framework: "agno", "strands", "langchain"
        system_prompt: str | None = None,
        system_context: Union[str, Callable[[dict], str]] | None = None,
        model_config: dict | None = None,
        high_risk_tools: list[str] | None = None,
        on_event: EventHandler | list[EventHandler] | None = None,
        # Interceptor configuration
        request_interceptors: RequestInterceptorInput = None,
        response_interceptors: ResponseInterceptorInput = None,
        on_interceptor_error: str = "abort",
        # AWS configuration (for provider="bedrock")
        aws_profile: str | None = None,
        aws_region: str | None = None,
        aws_access_key: str | None = None,
        aws_secret_key: str | None = None,
        # API key (for provider="anthropic", "openai", etc.)
        api_key: str | None = None,
        # A2A configuration
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        """
        Create a new Agent.
        
        See class docstring for detailed parameter descriptions and examples.
        """
        # Store the basic configuration
        self.tools = tools or []
        self.model = model
        self.provider = provider
        self.framework = framework
        self.system_prompt = system_prompt
        self._system_context = system_context
        self._model_config = model_config or {}
        self.high_risk_tools = set(high_risk_tools or [])
        
        # A2A identity
        self.name = name or "dcaf-agent"
        self.description = description or system_prompt or "A DCAF agent"
        
        # Store provider-specific configuration
        self._aws_profile = aws_profile
        self._aws_region = aws_region
        self._aws_access_key = aws_access_key
        self._aws_secret_key = aws_secret_key
        self._api_key = api_key
        
        # Store interceptor error handling mode
        # "abort" = stop on any error
        # "continue" = log and keep going (except InterceptorError)
        self._on_interceptor_error = on_interceptor_error
        
        # Normalize interceptors to lists
        # This converts: None → [], single_func → [single_func], [a, b] → [a, b]
        self._request_interceptors = normalize_interceptors(request_interceptors)
        self._response_interceptors = normalize_interceptors(response_interceptors)
        
        # Log interceptor configuration for debugging
        if self._request_interceptors:
            interceptor_names = [
                getattr(f, "__name__", "anonymous") 
                for f in self._request_interceptors
            ]
            logger.debug(f"Request interceptors configured: {interceptor_names}")
        
        if self._response_interceptors:
            interceptor_names = [
                getattr(f, "__name__", "anonymous") 
                for f in self._response_interceptors
            ]
            logger.debug(f"Response interceptors configured: {interceptor_names}")
        
        # Normalize event handlers to a list
        if on_event is None:
            self._event_handlers: list[EventHandler] = []
        elif callable(on_event):
            self._event_handlers = [on_event]
        else:
            self._event_handlers = list(on_event)
        
        # Create internal services using dynamic adapter loading
        # This enables plugin-style framework support without if-statements
        self._runtime = load_adapter(
            framework=framework,
            model_id=model,
            provider=provider,
            aws_profile=aws_profile,
            aws_region=aws_region,
            aws_access_key=aws_access_key,
            aws_secret_key=aws_secret_key,
            api_key=api_key,
            model_config=self._model_config,
        )
        self._conversations = InMemoryConversationRepository()
        self._agent_service = AgentService(
            runtime=self._runtime,
            conversations=self._conversations,
            events=self._create_event_publisher(),
        )
        self._approval_service = ApprovalService(
            conversations=self._conversations,
            events=self._create_event_publisher(),
        )
    
    def _build_system_parts(self, platform_context: dict | None = None) -> tuple[str | None, str | None]:
        """
        Build static and dynamic system prompt parts separately.
        
        This separation is useful even without caching - it keeps static
        instructions separate from runtime context. When caching is enabled,
        adapters can place a cache checkpoint between these parts.
        
        Args:
            platform_context: Runtime context (tenant, namespace, etc.)
            
        Returns:
            (static_part, dynamic_part) where either can be None
        """
        static = self.system_prompt
        
        dynamic = None
        if self._system_context:
            if callable(self._system_context):
                # Call the function with platform_context
                dynamic = self._system_context(platform_context or {})
            else:
                # Use the string directly
                dynamic = self._system_context
        
        return static, dynamic
    
    def run(
        self, 
        messages: list[ChatMessage | dict],
        context: dict | None = None,
    ) -> AgentResponse:
        """
        Run the agent with a conversation.
        
        This method:
        1. Runs request interceptors (if any) to modify/validate input
        2. Sends the request to the LLM
        3. Runs response interceptors (if any) to modify/clean output
        4. Returns the final response
        
        Args:
            messages: The conversation messages. Can be ChatMessage instances
                     or plain dicts with 'role' and 'content' keys.
                     
                     Roles: 'user', 'assistant', 'system'
                     
                     **IMPORTANT**: The last message in the list is assumed to be
                     the current user message. All previous messages are treated
                     as conversation history.
                     
            context: Optional platform context (tenant, namespace, etc.)
                     This is merged with any context in individual messages.
                     Common fields: tenant_name, k8s_namespace, user_id
            
        Returns:
            AgentResponse with the result
            
        Raises:
            InterceptorError: If a request interceptor blocks the request.
                            The error's user_message will be returned to the user.
            ValueError: If messages is empty.
            
        Example - Basic usage:
            response = agent.run(messages=[
                {"role": "user", "content": "What pods are running?"}
            ])
            print(response.text)
            
        Example - With context:
            response = agent.run(
                messages=[{"role": "user", "content": "List my pods"}],
                context={"tenant_name": "production", "k8s_namespace": "web"},
            )
            
        Example - Handling interceptor errors:
            try:
                response = agent.run(messages=[...])
            except InterceptorError as error:
                # The interceptor blocked the request
                print(f"Blocked: {error.user_message}")
        """
        # Validate input
        if not messages:
            raise ValueError("messages cannot be empty")
        
        # Normalize to ChatMessage instances (accepts both dicts and ChatMessage)
        normalized_messages = normalize_messages(messages)
        
        # Extract the current message (last one) - this is the user's latest message
        current_user_message = normalized_messages[-1].content
        
        # Convert to dict format for processing
        messages_as_dicts = [msg.to_dict() for msg in normalized_messages]
        
        # === RUN REQUEST INTERCEPTORS ===
        # These can modify the request or block it entirely
        
        if self._request_interceptors:
            # Create the normalized LLMRequest for interceptors
            llm_request = create_request_from_messages(
                messages=messages_as_dicts,
                tools=self.tools,
                system_prompt=self.system_prompt,
                context=context or {},
            )
            
            # Run the request interceptor pipeline
            try:
                llm_request = self._run_request_interceptors(llm_request)
            except InterceptorError:
                # InterceptorError is intentional - let it propagate to caller
                raise
            except Exception as unexpected_error:
                # Handle unexpected errors based on configuration
                if self._on_interceptor_error == "abort":
                    raise
                else:
                    # Log and continue with original request
                    logger.warning(
                        f"Request interceptor error (continuing): {unexpected_error}"
                    )
            
            # Use the potentially modified values from interceptors
            messages_as_dicts = llm_request.messages
            current_user_message = llm_request.get_latest_user_message()
            # Update system prompt if interceptors modified it
            effective_system_prompt = llm_request.system
            effective_context = llm_request.context
        else:
            # No interceptors - use original values
            effective_system_prompt = self.system_prompt
            effective_context = context
        
        # === CALL THE LLM ===
        
        # Build system prompt parts for caching
        static_system, dynamic_system = self._build_system_parts(effective_context)
        
        # If we have separate parts, use them; otherwise use effective_system_prompt
        if static_system or dynamic_system:
            final_system_prompt = None  # Will be built by adapter from parts
        else:
            final_system_prompt = effective_system_prompt
        
        # Create the internal request
        internal_request = AgentRequest(
            content=current_user_message,
            messages=messages_as_dicts,
            tools=self.tools,
            system_prompt=final_system_prompt,
            static_system=static_system,
            dynamic_system=dynamic_system,
            context=effective_context,
        )
        
        # Execute the agent service (calls the LLM)
        internal_response = self._agent_service.execute(internal_request)
        
        # === RUN RESPONSE INTERCEPTORS ===
        # These can modify the response before returning to the user
        
        if self._response_interceptors and internal_response.text:
            # Create the normalized LLMResponse for interceptors
            llm_response = create_response_from_text(
                text=internal_response.text or "",
                tool_calls=[],  # Tool calls are handled separately
                raw=internal_response,
            )
            
            # Run the response interceptor pipeline
            try:
                llm_response = self._run_response_interceptors(llm_response)
            except InterceptorError as interceptor_error:
                # Response interceptor blocked - return the error message
                return AgentResponse(
                    text=interceptor_error.user_message,
                    needs_approval=False,
                    pending_tools=[],
                    is_complete=True,
                    _agent=self,
                )
            except Exception as unexpected_error:
                # Handle unexpected errors based on configuration
                if self._on_interceptor_error == "abort":
                    raise
                else:
                    # Log and continue with original response
                    logger.warning(
                        f"Response interceptor error (continuing): {unexpected_error}"
                    )
            else:
                # Update the internal response with the modified text
                # We create a modified version since the original may be immutable
                internal_response.text = llm_response.text
        
        # Convert to the user-facing response format
        return self._convert_response(internal_response)
    
    def _run_request_interceptors(self, llm_request: LLMRequest) -> LLMRequest:
        """
        Run all request interceptors on the LLM request.
        
        This method runs each request interceptor in order. Each interceptor
        receives the output of the previous one, allowing them to be chained.
        
        Args:
            llm_request: The initial LLM request to process
            
        Returns:
            The processed LLM request (may be modified by interceptors)
            
        Raises:
            InterceptorError: If any interceptor intentionally blocks the request
            Exception: If any interceptor fails unexpectedly
        """
        # Create a pipeline to run interceptors in order
        request_pipeline = InterceptorPipeline(
            interceptors=self._request_interceptors,
            pipeline_name="request",
        )
        
        # Run the pipeline (handles both sync and async interceptors)
        # We need to run this in an event loop since interceptors can be async
        try:
            # Try to get the current event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context - this shouldn't normally happen
                # in the sync run() method, but handle it gracefully
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run, 
                        request_pipeline.run(llm_request)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(request_pipeline.run(llm_request))
        except RuntimeError:
            # No event loop exists, create one
            return asyncio.run(request_pipeline.run(llm_request))
    
    def _run_response_interceptors(self, llm_response: LLMResponse) -> LLMResponse:
        """
        Run all response interceptors on the LLM response.
        
        This method runs each response interceptor in order. Each interceptor
        receives the output of the previous one, allowing them to be chained.
        
        Args:
            llm_response: The initial LLM response to process
            
        Returns:
            The processed LLM response (may be modified by interceptors)
            
        Raises:
            InterceptorError: If any interceptor intentionally blocks the response
            Exception: If any interceptor fails unexpectedly
        """
        # Create a pipeline to run interceptors in order
        response_pipeline = InterceptorPipeline(
            interceptors=self._response_interceptors,
            pipeline_name="response",
        )
        
        # Run the pipeline (handles both sync and async interceptors)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run, 
                        response_pipeline.run(llm_response)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(response_pipeline.run(llm_response))
        except RuntimeError:
            return asyncio.run(response_pipeline.run(llm_response))
    
    def resume(self, conversation_id: str) -> AgentResponse:
        """
        Resume a conversation after approving/rejecting tool calls.
        
        Use this method after manually handling tool approvals to continue
        the agent's execution with the approved tools.
        
        Args:
            conversation_id: The conversation to resume
            
        Returns:
            AgentResponse with the continued result
            
        Example:
            response = agent.run(messages)
            
            if response.needs_approval:
                for tool in response.pending_tools:
                    if should_approve(tool):
                        tool.approve()
                    else:
                        tool.reject("Not allowed")
                
                # Resume execution with the approval decisions
                response = agent.resume(response.conversation_id)
            
            print(response.text)
        """
        internal_response = self._agent_service.resume(
            conversation_id=conversation_id,
            tools=self.tools,
        )
        return self._convert_response(internal_response)
    
    def run_stream(
        self,
        messages: list[ChatMessage | dict],
        context: dict | None = None,
    ) -> Iterator[ServerStreamEvent]:
        """
        Run the agent with streaming response.
        
        This method yields stream events as they are generated,
        providing real-time feedback to the user. Events include
        text deltas (token-by-token text), tool calls, and completion.
        
        Args:
            messages: The conversation messages (same format as run())
            context: Optional platform context (tenant, namespace, etc.)
            
        Yields:
            StreamEvent objects for NDJSON streaming:
            - TextDeltaEvent: Text token(s) from the LLM
            - ToolCallsEvent: Tool calls needing approval
            - DoneEvent: Stream finished successfully
            - ErrorEvent: An error occurred
            
        Example - Basic streaming:
            for event in agent.run_stream(messages=[
                ChatMessage.user("Tell me about Kubernetes")
            ]):
                if isinstance(event, TextDeltaEvent):
                    print(event.text, end="", flush=True)
                elif isinstance(event, DoneEvent):
                    print("\\nDone!")
                    
        Example - Handling tool approvals:
            for event in agent.run_stream(messages=[...]):
                if isinstance(event, ToolCallsEvent):
                    for tool_call in event.tool_calls:
                        print(f"Approve {tool_call.name}?")
                elif isinstance(event, TextDeltaEvent):
                    print(event.text, end="")
                    
        Note:
            The last message in the messages list is the current user
            message. All previous messages are conversation history.
        """
        if not messages:
            yield ErrorEvent(error="messages cannot be empty")
            return
        
        try:
            # Normalize to ChatMessage instances
            normalized = normalize_messages(messages)
            
            # Extract the current message (last one)
            current_message = normalized[-1].content
            
            # Convert to dict format for the internal request
            messages_as_dicts = [m.to_dict() for m in normalized]
            
            request = AgentRequest(
                content=current_message,
                messages=messages_as_dicts,
                tools=self.tools,
                system_prompt=self.system_prompt,
                context=context,
            )
            
            # Use the streaming version of the agent service
            # For now, we'll use the runtime's stream capability directly
            # and handle the event conversion here
            
            # Get or create conversation for this request
            # (Similar logic to AgentService.execute but for streaming)
            from .domain.value_objects import PlatformContext
            
            platform_context = PlatformContext.from_dict(context or {})
            
            # Create conversation from message history
            conversation = Conversation.create(context=platform_context)
            if self.system_prompt:
                conversation = conversation.with_system_prompt(self.system_prompt)
            
            # Add messages from history
            for msg in messages_as_dicts[:-1]:  # All except last
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "user":
                    conversation.add_user_message(content)
                elif role == "assistant":
                    conversation.add_assistant_message(content)
            
            # Add current message
            conversation.add_user_message(current_message)
            
            # Stream from the runtime
            pending_tool_calls = []
            
            for event in self._runtime.invoke_stream(
                messages=conversation.messages,
                tools=self.tools,
                system_prompt=self.system_prompt,
            ):
                # Convert internal stream events to server stream events
                server_event = self._convert_stream_event(event, pending_tool_calls)
                if server_event:
                    yield server_event
            
            # If there are pending tool calls that need approval, yield them
            if pending_tool_calls:
                yield ToolCallsEvent(tool_calls=pending_tool_calls)
            
            # Always end with a done event
            yield DoneEvent()
            
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield ErrorEvent(error=str(e))
    
    def _convert_stream_event(
        self, 
        internal_event, 
        pending_tool_calls: list,
    ) -> ServerStreamEvent | None:
        """Convert internal stream event to server stream event."""
        from .application.dto.responses import StreamEvent as CoreStreamEvent, StreamEventType
        
        if isinstance(internal_event, CoreStreamEvent):
            if internal_event.event_type == StreamEventType.TEXT_DELTA:
                text = internal_event.data.get("text", "")
                return TextDeltaEvent(text=text)
            elif internal_event.event_type == StreamEventType.TOOL_USE_START:
                # Accumulate tool calls for later
                tool_call_id = internal_event.data.get("tool_call_id", "")
                tool_name = internal_event.data.get("tool_name", "")
                pending_tool_calls.append(SchemaToolCall(
                    id=tool_call_id,
                    name=tool_name,
                    input={},
                    tool_description="",
                    input_description={},
                ))
                return None  # Don't yield yet, wait for complete tool call
            elif internal_event.event_type == StreamEventType.ERROR:
                return ErrorEvent(error=internal_event.data.get("message", "Unknown error"))
        
        # Handle dict events from mock/Bedrock
        if isinstance(internal_event, dict):
            event_type = internal_event.get("type")
            
            if event_type == "content_block_delta":
                delta = internal_event.get("delta", {})
                if delta.get("type") == "text_delta":
                    return TextDeltaEvent(text=delta.get("text", ""))
            
            # message_start and message_stop don't need to be forwarded
            
        return None
    
    # Private methods
    
    def _convert_response(self, internal: Any) -> AgentResponse:
        """Convert internal response to simple AgentResponse."""
        pending_tools = []
        
        for tc in getattr(internal, 'tool_calls', []):
            if getattr(tc, 'requires_approval', False) and getattr(tc, 'status', '') == 'pending':
                pending_tools.append(PendingToolCall(
                    id=tc.id,
                    name=tc.name,
                    input=tc.input,
                    description=getattr(tc, 'description', ''),
                    _conversation_id=internal.conversation_id,
                    _approval_service=self._approval_service,
                ))
        
        return AgentResponse(
            text=internal.text,
            needs_approval=getattr(internal, 'has_pending_approvals', False),
            pending_tools=pending_tools,
            conversation_id=internal.conversation_id,
            is_complete=getattr(internal, 'is_complete', True),
            _agent=self,
        )
    
    def _approve_all_and_continue(self, conversation_id: str) -> AgentResponse:
        """Approve all pending and continue."""
        self._approval_service.approve_all(conversation_id)
        return self.resume(conversation_id)
    
    def _reject_all(self, conversation_id: str, reason: str) -> AgentResponse:
        """Reject all pending tool calls."""
        internal = self._approval_service.reject_all(conversation_id, reason)
        return self._convert_response(internal)
    
    def _create_event_publisher(self):
        """Create an event publisher that calls our handlers."""
        if not self._event_handlers:
            return None
        
        class CallbackEventPublisher:
            def __init__(self, handlers: list[EventHandler]):
                self.handlers = handlers
            
            def publish(self, event: DomainEvent) -> None:
                for handler in self.handlers:
                    try:
                        handler(event)
                    except Exception as e:
                        logger.warning(f"Event handler error: {e}")
            
            def publish_all(self, events: list[DomainEvent]) -> None:
                for event in events:
                    self.publish(event)
        
        return CallbackEventPublisher(self._event_handlers)
    
    def _check_requires_approval(self, tool_name: str, tool_requires: bool) -> bool:
        """
        Check if a tool requires approval.
        
        Rule: If EITHER the tool flag OR the policy says risky, require approval.
        """
        # Tool says it needs approval
        if tool_requires:
            return True
        
        # Policy says it's high-risk
        if tool_name in self.high_risk_tools:
            return True
        
        # Both agree it's safe
        return False
