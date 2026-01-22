"""
Interceptors - Hook into the LLM request/response pipeline.

Interceptors let you modify, validate, or enhance data before it goes to
the LLM and after you receive a response. They're like checkpoints in a
pipeline where you can inspect and transform the data.

WHAT ARE INTERCEPTORS?
======================

Think of interceptors like airport security checkpoints:

    Your Message → [Request Interceptor] → LLM → [Response Interceptor] → Final Response
                          ↑                              ↑
                    Check & modify              Check & modify
                    before sending              before returning

You can use interceptors to:
- Add context to messages (like user preferences or tenant info)
- Validate input (block suspicious prompts)
- Clean up responses (remove sensitive data)
- Log or audit what's happening
- Transform data formats

HOW TO USE:
===========

1. Create a function that takes and returns the right type:

    # Request interceptor: takes LLMRequest, returns LLMRequest
    def add_context(request: LLMRequest) -> LLMRequest:
        request.context["extra_info"] = "Hello!"
        return request

    # Response interceptor: takes LLMResponse, returns LLMResponse
    def clean_response(response: LLMResponse) -> LLMResponse:
        response.text = response.text.replace("bad_word", "***")
        return response

2. Pass your interceptors to the Agent:

    agent = Agent(
        tools=[...],
        request_interceptors=add_context,      # Single function
        response_interceptors=[clean_response], # Or a list
    )

3. That's it! Your functions will be called automatically.

ASYNC SUPPORT:
==============

Interceptors can be async (for database lookups, API calls, etc.):

    async def get_user_preferences(request: LLMRequest) -> LLMRequest:
        user_id = request.context.get("user_id")
        preferences = await database.get_preferences(user_id)
        request.context["preferences"] = preferences
        return request

ERROR HANDLING:
===============

If something is wrong and you want to STOP the request, raise InterceptorError:

    def validate_input(request: LLMRequest) -> LLMRequest:
        if "hack" in request.messages[-1].get("content", "").lower():
            raise InterceptorError(
                user_message="Sorry, I can't process this request.",
                code="BLOCKED_CONTENT"
            )
        return request

The user will see "Sorry, I can't process this request." and the LLM
will NOT be called.

EXAMPLE - Security Validation:
==============================

    from dcaf.core import Agent, LLMRequest, InterceptorError

    def block_prompt_injection(request: LLMRequest) -> LLMRequest:
        '''
        Check for prompt injection attacks.

        This interceptor looks for common patterns that attackers use
        to try to manipulate the AI into ignoring its instructions.
        '''
        # Get the latest user message
        user_content = ""
        if request.messages:
            user_content = request.messages[-1].get("content", "")

        # List of suspicious phrases
        suspicious_patterns = [
            "ignore previous instructions",
            "disregard your instructions",
            "new instructions:",
            "forget everything",
        ]

        # Check each pattern
        for pattern in suspicious_patterns:
            if pattern.lower() in user_content.lower():
                # This looks suspicious! Block it.
                raise InterceptorError(
                    user_message="I'm sorry, I can't process this request.",
                    code="PROMPT_INJECTION_BLOCKED",
                    details={"blocked_pattern": pattern}
                )

        # All checks passed, continue normally
        return request

    # Use it
    agent = Agent(
        tools=[...],
        request_interceptors=block_prompt_injection,
    )

EXAMPLE - Adding Context:
=========================

    from dcaf.core import Agent, LLMRequest

    def add_tenant_context(request: LLMRequest) -> LLMRequest:
        '''
        Add information about the user's tenant to help the AI understand
        which environment the user is working in.
        '''
        # Get tenant name from platform context
        tenant_name = request.context.get("tenant_name", "unknown")

        # Add it to the system message so the AI knows about it
        current_system_message = request.system or ""
        additional_context = f"\\n\\nUser's tenant: {tenant_name}"
        request.system = current_system_message + additional_context

        return request

    agent = Agent(
        tools=[...],
        request_interceptors=add_tenant_context,
    )

EXAMPLE - Cleaning Response:
============================

    from dcaf.core import Agent, LLMResponse

    def remove_thinking_tags(response: LLMResponse) -> LLMResponse:
        '''
        Remove any <thinking> tags that the AI might have included.

        Some AI models include their reasoning in <thinking> tags.
        We want to hide this from the user for a cleaner experience.
        '''
        import re

        # Remove <thinking>...</thinking> tags and their content
        cleaned_text = re.sub(
            r'<thinking>.*?</thinking>',
            '',
            response.text,
            flags=re.DOTALL  # Match across multiple lines
        )

        response.text = cleaned_text.strip()
        return response

    agent = Agent(
        tools=[...],
        response_interceptors=remove_thinking_tags,
    )

EXAMPLE - Multiple Interceptors:
================================

You can chain multiple interceptors. They run in order:

    agent = Agent(
        tools=[...],
        request_interceptors=[
            validate_input,      # First: check if input is safe
            add_tenant_context,  # Second: add context
            log_request,         # Third: log for debugging
        ],
        response_interceptors=[
            remove_thinking_tags,  # First: clean up response
            redact_secrets,        # Second: hide sensitive data
            log_response,          # Third: log for debugging
        ],
    )

"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .session import Session

# Set up logging for this module
logger = logging.getLogger(__name__)


# =============================================================================
# LLM REQUEST - The data going TO the LLM
# =============================================================================


@dataclass
class LLMRequest:
    """
    The request being sent to the Large Language Model (LLM).

    This is a "normalized" format that works the same regardless of which
    LLM provider you're using (Bedrock, OpenAI, Anthropic, etc.).

    WHAT'S IN A REQUEST?
    ====================

    - messages: The conversation so far (user questions, AI responses)
    - tools: What actions the AI can take (like "list_pods", "delete_pod")
    - system: Special instructions for how the AI should behave
    - context: Extra info like which tenant/environment the user is in
    - session: Persistent state across conversation turns

    EXAMPLE:
    ========

        # What a request might look like
        request = LLMRequest(
            messages=[
                {"role": "user", "content": "What pods are running?"},
                {"role": "assistant", "content": "There are 3 pods..."},
                {"role": "user", "content": "Delete the nginx pod"},
            ],
            tools=[list_pods_tool, delete_pod_tool],
            system="You are a helpful Kubernetes assistant.",
            context={"tenant_name": "production", "user_id": "alice"},
        )

        # Access session in interceptor
        user_prefs = request.session.get("user_preferences", {})
        request.session.set("last_action", "list_pods")

    FIELDS EXPLAINED:
    =================

    messages: list[dict]
        The conversation history. Each message is a dict with:
        - "role": Who said it ("user", "assistant", or "system")
        - "content": What they said

    tools: list[Any]
        The tools/functions the AI can use. These are Tool objects
        created with the @tool decorator.

    system: str | None
        The system prompt - instructions for how the AI should behave.
        Example: "You are a helpful assistant. Be concise."

    context: dict
        Platform/environment information. Common fields:
        - "tenant_name": Which DuploCloud tenant
        - "k8s_namespace": Which Kubernetes namespace
        - "user_id": Who is making the request
        - "duplo_token": Auth token (be careful with this!)

    session: Session
        Persistent state that travels with each request/response.
        Use this to store data across conversation turns.
    """

    # The conversation messages (list of dicts with "role" and "content")
    messages: list[dict]

    # The tools the AI can use (list of Tool objects)
    tools: list[Any] = field(default_factory=list)

    # The system prompt (instructions for the AI)
    system: str | None = None

    # Platform context (tenant, namespace, credentials, etc.)
    context: dict = field(default_factory=dict)

    # Session for persistent state across conversation turns
    session: Session | None = field(default=None)

    def __post_init__(self) -> None:
        """
        Called automatically after the object is created.
        Ensures context is never None (always a dict).
        Ensures session is never None (always a Session).
        """
        # Make sure context is always a dict, never None
        if self.context is None:
            self.context = {}

        # Make sure session is always a Session instance
        if self.session is None:
            from .session import Session

            self.session = Session()

    def get_latest_user_message(self) -> str:
        """
        Get the content of the most recent user message.

        This is useful for interceptors that need to check what the
        user just said (like for validation or logging).

        Returns:
            The content of the last user message, or empty string if none.

        Example:
            user_said = request.get_latest_user_message()
            if "delete" in user_said.lower():
                # User is asking to delete something
                ...
        """
        # Go through messages in reverse to find the last user message
        for message in reversed(self.messages):
            if message.get("role") == "user":
                content = message.get("content", "")
                return str(content) if content else ""

        # No user message found
        return ""

    def add_system_context(self, additional_context: str) -> None:
        """
        Add additional text to the system prompt.

        This is useful for interceptors that want to give the AI
        extra context without replacing the entire system prompt.

        Args:
            additional_context: Text to add to the system prompt

        Example:
            # Add tenant info to system prompt
            request.add_system_context(f"User is in tenant: {tenant_name}")
        """
        if self.system:
            # Append to existing system prompt
            self.system = self.system + "\n\n" + additional_context
        else:
            # Create new system prompt
            self.system = additional_context


# =============================================================================
# LLM RESPONSE - The data coming FROM the LLM
# =============================================================================


@dataclass
class LLMResponse:
    """
    The response received from the Large Language Model (LLM).

    This is a "normalized" format that works the same regardless of which
    LLM provider you're using (Bedrock, OpenAI, Anthropic, etc.).

    WHAT'S IN A RESPONSE?
    =====================

    - text: What the AI said (the main response)
    - tool_calls: Actions the AI wants to take (like calling a function)
    - usage: Token counts (how much of the AI's "attention" was used)
    - raw: The original, unmodified response from the provider
    - session: Persistent state across conversation turns

    EXAMPLE:
    ========

        # What a response might look like
        response = LLMResponse(
            text="I found 3 pods running. Would you like me to delete one?",
            tool_calls=[
                {
                    "id": "call_123",
                    "name": "list_pods",
                    "input": {"namespace": "default"},
                }
            ],
            usage={"input_tokens": 150, "output_tokens": 45},
        )

        # Modify session in response interceptor
        response.session.set("last_response_length", len(response.text))

    FIELDS EXPLAINED:
    =================

    text: str
        The AI's text response. This is what the user sees.
        May be empty if the AI only wants to call tools.

    tool_calls: list[dict]
        Actions the AI wants to take. Each tool call has:
        - "id": Unique identifier for this call
        - "name": Which tool to use (like "delete_pod")
        - "input": Arguments to pass to the tool

    usage: dict | None
        Token usage statistics (optional):
        - "input_tokens": How many tokens in the input
        - "output_tokens": How many tokens in the output
        Useful for cost tracking and debugging.

    raw: Any
        The original, unmodified response from the LLM provider.
        Useful for debugging or accessing provider-specific fields.

    session: Session
        Persistent state that travels with each request/response.
        Modify this to update session data in the response.
    """

    # The AI's text response
    text: str

    # Tool calls the AI wants to make (list of dicts)
    tool_calls: list[dict] = field(default_factory=list)

    # Token usage statistics (optional)
    usage: dict | None = None

    # Original provider response (for debugging)
    raw: Any = None

    # Session for persistent state across conversation turns
    session: Session | None = field(default=None)

    def __post_init__(self) -> None:
        """Ensure session is never None."""
        if self.session is None:
            from .session import Session

            self.session = Session()

    def has_tool_calls(self) -> bool:
        """
        Check if the AI wants to call any tools.

        Returns:
            True if there are tool calls, False otherwise.

        Example:
            if response.has_tool_calls():
                print("AI wants to use tools!")
        """
        return len(self.tool_calls) > 0

    def get_text_length(self) -> int:
        """
        Get the length of the text response.

        Returns:
            Number of characters in the text response.

        Example:
            if response.get_text_length() > 1000:
                print("That's a long response!")
        """
        return len(self.text) if self.text else 0


# =============================================================================
# INTERCEPTOR ERROR - When something goes wrong
# =============================================================================


class InterceptorError(Exception):
    """
    Raise this error to stop processing and return a message to the user.

    When you raise this error, the LLM will NOT be called. Instead, the
    user will see the message you provide. Use this for:

    - Input validation failures
    - Security blocks (like prompt injection detection)
    - Missing required data
    - Permission checks

    WHEN TO USE:
    ============

    Use InterceptorError when you need to STOP and tell the user something
    is wrong. The request will not reach the LLM.

    WHEN NOT TO USE:
    ================

    Don't use this for minor issues you can fix. For example, if you can
    clean up bad input and continue, just modify the request and return it.

    EXAMPLE - Basic Usage:
    ======================

        def validate_request(request: LLMRequest) -> LLMRequest:
            if not request.messages:
                raise InterceptorError(
                    user_message="Please provide a message to process."
                )
            return request

    EXAMPLE - Security Block:
    =========================

        def block_dangerous_content(request: LLMRequest) -> LLMRequest:
            user_message = request.get_latest_user_message()

            if "DROP TABLE" in user_message.upper():
                raise InterceptorError(
                    user_message="I can't help with that request.",
                    code="DANGEROUS_SQL_BLOCKED",
                    details={
                        "reason": "SQL injection attempt detected",
                        "pattern": "DROP TABLE"
                    }
                )

            return request

    EXAMPLE - Missing Permissions:
    ==============================

        def check_permissions(request: LLMRequest) -> LLMRequest:
            user_role = request.context.get("user_role", "guest")

            if user_role == "guest":
                raise InterceptorError(
                    user_message="You need to log in to use this feature.",
                    code="AUTH_REQUIRED"
                )

            return request

    FIELDS:
    =======

    user_message: str
        The message shown to the user. Make it helpful!
        Good: "Please provide a valid email address."
        Bad:  "Error 42: INVALID_INPUT_EXCEPTION"

    code: str | None
        An internal code for logging and debugging.
        Example: "PROMPT_INJECTION_BLOCKED", "MISSING_TENANT"

    details: dict
        Extra information for logging.
        Example: {"blocked_pattern": "ignore instructions", "user_id": "123"}
    """

    def __init__(
        self,
        user_message: str,
        code: str | None = None,
        details: dict | None = None,
    ) -> None:
        """
        Create an InterceptorError.

        Args:
            user_message: The message to show to the user. Keep it friendly
                         and helpful. The user will see this exact text.

            code: An optional internal code for logging and debugging.
                  Examples: "BLOCKED", "AUTH_REQUIRED", "INVALID_INPUT"

            details: Optional dict with extra information for logging.
                    This is NOT shown to the user.
        """
        # The message the user will see
        self.user_message = user_message

        # Internal code for logging/debugging
        self.code = code

        # Extra details for logging (not shown to user)
        self.details = details or {}

        # Call parent Exception with the user message
        super().__init__(user_message)

    def __str__(self) -> str:
        """Return a string representation for logging."""
        if self.code:
            return f"[{self.code}] {self.user_message}"
        return self.user_message


# =============================================================================
# TYPE DEFINITIONS - What types interceptors can be
# =============================================================================

# A request interceptor can be sync or async
# It takes an LLMRequest and returns an LLMRequest
RequestInterceptor = Callable[[LLMRequest], LLMRequest | Awaitable[LLMRequest]]

# A response interceptor can be sync or async
# It takes an LLMResponse and returns an LLMResponse
ResponseInterceptor = Callable[[LLMResponse], LLMResponse | Awaitable[LLMResponse]]

# Interceptors can be a single function or a list of functions
RequestInterceptorInput = (
    RequestInterceptor  # Single function
    | list[RequestInterceptor]  # List of functions
    | None  # Not provided
)

ResponseInterceptorInput = (
    ResponseInterceptor  # Single function
    | list[ResponseInterceptor]  # List of functions
    | None  # Not provided
)


# =============================================================================
# INTERCEPTOR PIPELINE - Runs interceptors in order
# =============================================================================


class InterceptorPipeline:
    """
    Runs a series of interceptors in order.

    This class handles:
    - Running interceptors in the correct order
    - Supporting both sync and async interceptors
    - Error handling and propagation
    - Logging for debugging

    You don't usually need to use this class directly. The Agent class
    uses it internally to run your interceptors.

    HOW IT WORKS:
    =============

    1. You provide a list of interceptors
    2. Each interceptor receives the output of the previous one
    3. If any interceptor raises InterceptorError, processing stops
    4. The final result is returned

    EXAMPLE:
    ========

        # Usually you don't create this directly, but here's how it works:

        pipeline = InterceptorPipeline(
            interceptors=[step1, step2, step3],
            name="request"  # For logging
        )

        # Run the pipeline
        result = await pipeline.run(initial_data)
    """

    def __init__(
        self,
        interceptors: list[Callable],
        pipeline_name: str = "unnamed",
    ) -> None:
        """
        Create an interceptor pipeline.

        Args:
            interceptors: List of interceptor functions to run in order.
                         Each function should take one argument and return
                         a value of the same type.

            pipeline_name: A name for this pipeline (used in logs).
                          Example: "request" or "response"
        """
        # Store the list of interceptors
        self.interceptors = interceptors

        # Name for logging purposes
        self.pipeline_name = pipeline_name

        # Log that we created the pipeline
        logger.debug(
            f"Created {pipeline_name} interceptor pipeline with {len(interceptors)} interceptor(s)"
        )

    async def run(self, data: Any) -> Any:
        """
        Run all interceptors in order.

        Each interceptor receives the output of the previous one.
        If any interceptor raises InterceptorError, processing stops
        and the error is propagated.

        Args:
            data: The initial data to process (LLMRequest or LLMResponse)

        Returns:
            The final processed data after all interceptors have run.

        Raises:
            InterceptorError: If any interceptor raises this error.
            Exception: If any interceptor raises an unexpected error.
        """
        # Start with the initial data
        current_data = data

        # Run each interceptor in order
        for interceptor_index, interceptor_function in enumerate(self.interceptors):
            # Get the name of the interceptor for logging
            interceptor_name = getattr(
                interceptor_function, "__name__", f"interceptor_{interceptor_index}"
            )

            logger.debug(f"Running {self.pipeline_name} interceptor: {interceptor_name}")

            try:
                # Call the interceptor function
                result = interceptor_function(current_data)

                # If the interceptor is async, await it
                if asyncio.iscoroutine(result):
                    current_data = await result
                else:
                    current_data = result

            except InterceptorError:
                # InterceptorError is intentional - let it propagate
                logger.info(
                    f"{self.pipeline_name} interceptor '{interceptor_name}' "
                    f"raised InterceptorError - stopping pipeline"
                )
                raise

            except Exception as unexpected_error:
                # Unexpected error - log it and re-raise
                logger.error(
                    f"{self.pipeline_name} interceptor '{interceptor_name}' "
                    f"raised unexpected error: {unexpected_error}"
                )
                raise

        logger.debug(f"Completed {self.pipeline_name} interceptor pipeline successfully")

        return current_data


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def normalize_interceptors(
    interceptors_input: RequestInterceptorInput | ResponseInterceptorInput,
) -> list[Callable]:
    """
    Convert interceptor input to a list of functions.

    This helper handles the different ways interceptors can be provided:
    - None → empty list
    - Single function → list with one function
    - List of functions → list as-is

    Args:
        interceptors_input: The interceptors as provided by the user.
                           Can be None, a function, or a list of functions.

    Returns:
        A list of interceptor functions (may be empty).

    Example:
        # These all work:
        normalize_interceptors(None)           # → []
        normalize_interceptors(my_func)        # → [my_func]
        normalize_interceptors([a, b, c])      # → [a, b, c]
    """
    # Handle None - return empty list
    if interceptors_input is None:
        return []

    # Handle single function - wrap in a list
    if callable(interceptors_input):
        return [interceptors_input]

    # Handle list - return as-is
    if isinstance(interceptors_input, list):
        return list(interceptors_input)

    # Unknown type - log warning and return empty
    logger.warning(
        f"Unknown interceptor type: {type(interceptors_input)}. "
        f"Expected callable or list of callables."
    )
    return []


def create_request_from_messages(
    messages: list[dict],
    tools: list[Any] | None = None,
    system_prompt: str | None = None,
    context: dict | None = None,
    session: Session | None = None,
) -> LLMRequest:
    """
    Create an LLMRequest from raw components.

    This is a convenience function for creating LLMRequest objects
    from the typical inputs you have available.

    Args:
        messages: List of message dicts with "role" and "content"
        tools: List of tool objects (optional)
        system_prompt: System prompt string (optional)
        context: Platform context dict (optional)
        session: Session instance for persistent state (optional)

    Returns:
        A new LLMRequest object

    Example:
        request = create_request_from_messages(
            messages=[{"role": "user", "content": "Hello!"}],
            system_prompt="You are a helpful assistant.",
            context={"tenant_name": "prod"},
        )
    """
    return LLMRequest(
        messages=messages,
        tools=tools or [],
        system=system_prompt,
        context=context or {},
        session=session,
    )


def create_response_from_text(
    text: str,
    tool_calls: list[dict] | None = None,
    usage: dict | None = None,
    raw: Any = None,
    session: Session | None = None,
) -> LLMResponse:
    """
    Create an LLMResponse from raw components.

    This is a convenience function for creating LLMResponse objects
    from the typical outputs you get from an LLM.

    Args:
        text: The AI's text response
        tool_calls: List of tool call dicts (optional)
        usage: Token usage dict (optional)
        raw: Original provider response (optional)
        session: Session instance for persistent state (optional)

    Returns:
        A new LLMResponse object

    Example:
        response = create_response_from_text(
            text="Hello! How can I help you?",
            usage={"input_tokens": 10, "output_tokens": 8},
        )
    """
    return LLMResponse(
        text=text,
        tool_calls=tool_calls or [],
        usage=usage,
        raw=raw,
        session=session,
    )
