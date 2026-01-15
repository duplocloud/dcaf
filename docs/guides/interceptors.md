# Interceptors Guide

Interceptors let you hook into the LLM request/response pipeline. Think of them as checkpoints where you can inspect, modify, or block data before it goes to the AI and after you receive a response.

---

## Table of Contents

1. [What Are Interceptors?](#what-are-interceptors)
2. [Quick Start](#quick-start)
3. [Request Interceptors](#request-interceptors)
4. [Response Interceptors](#response-interceptors)
5. [Session Access](#session-access)
6. [Error Handling](#error-handling)
7. [Async Interceptors](#async-interceptors)
8. [Common Use Cases](#common-use-cases)
9. [Best Practices](#best-practices)
10. [API Reference](#api-reference)

---

## What Are Interceptors?

Interceptors are functions that run at specific points in the request/response flow:

```
Your Message
     │
     ▼
┌─────────────────────────────┐
│   REQUEST INTERCEPTORS      │  ◄── Runs BEFORE the LLM call
│   • Add context             │
│   • Validate input          │
│   • Block bad requests      │
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│         LLM                 │  ◄── AI processes your request
│   (Claude, GPT, etc.)       │
└─────────────────────────────┘
     │
     ▼
┌─────────────────────────────┐
│   RESPONSE INTERCEPTORS     │  ◄── Runs AFTER the LLM call
│   • Clean output            │
│   • Redact secrets          │
│   • Add formatting          │
└─────────────────────────────┘
     │
     ▼
Final Response
```

### Why Use Interceptors?

| Use Case | Example |
|----------|---------|
| **Add Context** | Tell the AI which tenant/environment the user is in |
| **Security** | Block prompt injection attacks |
| **Validation** | Ensure required data is present |
| **Clean Output** | Remove thinking tags or sensitive data |
| **Logging** | Track what's being sent and received |
| **Enrichment** | Look up user preferences from a database |

---

## Quick Start

Here's a simple example that adds tenant context to every request:

```python
from dcaf.core import Agent, LLMRequest
from dcaf.tools import tool

# Define a tool
@tool(description="List pods in the current namespace")
def list_pods(namespace: str = "default") -> str:
    return f"Pods in {namespace}: nginx, redis, api"

# Define a request interceptor
def add_tenant_context(request: LLMRequest) -> LLMRequest:
    """
    Add information about the user's tenant to help the AI
    understand which environment they're working in.
    """
    # Get the tenant name from the context (passed by the caller)
    tenant_name = request.context.get("tenant_name", "unknown")
    
    # Add it to the system prompt so the AI knows about it
    request.add_system_context(f"The user is working in tenant: {tenant_name}")
    
    # Return the modified request
    return request

# Create the agent with the interceptor
agent = Agent(
    tools=[list_pods],
    request_interceptors=add_tenant_context,  # Single interceptor
)

# Use the agent
response = agent.run(
    messages=[{"role": "user", "content": "What pods are running?"}],
    context={"tenant_name": "production"},
)

print(response.text)
```

---

## Request Interceptors

Request interceptors run **before** your request is sent to the LLM. They receive an `LLMRequest` object and must return an `LLMRequest` object.

### The LLMRequest Object

```python
from dcaf.core import LLMRequest

# What a request looks like
request = LLMRequest(
    messages=[
        {"role": "user", "content": "What pods are running?"},
    ],
    tools=[list_pods, delete_pod],
    system="You are a helpful Kubernetes assistant.",
    context={
        "tenant_name": "production",
        "user_id": "alice",
        "k8s_namespace": "default",
    },
)
```

### LLMRequest Fields

| Field | Type | Description |
|-------|------|-------------|
| `messages` | `list[dict]` | Conversation history. Each dict has `role` and `content`. |
| `tools` | `list` | Tools the AI can use. |
| `system` | `str \| None` | System prompt (instructions for the AI). |
| `context` | `dict` | Platform context (tenant, user, etc.). |
| `session` | `Session` | Persistent state across conversation turns. |

### LLMRequest Methods

| Method | Description |
|--------|-------------|
| `get_latest_user_message()` | Returns the content of the most recent user message. |
| `add_system_context(text)` | Appends text to the system prompt. |

### Example: Adding Context

```python
def add_user_preferences(request: LLMRequest) -> LLMRequest:
    """
    Add the user's language preference to help the AI respond
    in the correct language.
    """
    # Get user ID from context
    user_id = request.context.get("user_id")
    
    if user_id:
        # Look up user's preferred language (simplified example)
        preferred_language = "Spanish"  # Would come from a database
        
        # Tell the AI about the preference
        request.add_system_context(
            f"Please respond in {preferred_language} if possible."
        )
    
    return request

agent = Agent(
    tools=[...],
    request_interceptors=add_user_preferences,
)
```

### Example: Modifying Messages

```python
def shorten_long_messages(request: LLMRequest) -> LLMRequest:
    """
    Truncate very long messages to save tokens.
    """
    max_message_length = 5000
    
    # Go through each message
    for message in request.messages:
        content = message.get("content", "")
        
        if len(content) > max_message_length:
            # Truncate and add indicator
            message["content"] = content[:max_message_length] + "\n[Message truncated...]"
    
    return request

agent = Agent(
    tools=[...],
    request_interceptors=shorten_long_messages,
)
```

---

## Response Interceptors

Response interceptors run **after** you receive a response from the LLM. They receive an `LLMResponse` object and must return an `LLMResponse` object.

### The LLMResponse Object

```python
from dcaf.core import LLMResponse

# What a response looks like
response = LLMResponse(
    text="There are 3 pods running: nginx, redis, and api.",
    tool_calls=[],  # Empty if no tools were called
    usage={"input_tokens": 150, "output_tokens": 25},
)
```

### LLMResponse Fields

| Field | Type | Description |
|-------|------|-------------|
| `text` | `str` | The AI's text response. |
| `tool_calls` | `list[dict]` | Tools the AI wants to use. |
| `usage` | `dict \| None` | Token usage statistics. |
| `raw` | `Any` | Original provider response (for debugging). |
| `session` | `Session` | Persistent state across conversation turns. |

### LLMResponse Methods

| Method | Description |
|--------|-------------|
| `has_tool_calls()` | Returns `True` if the AI wants to call tools. |
| `get_text_length()` | Returns the length of the text response. |

### Example: Cleaning Output

```python
import re

def remove_thinking_tags(response: LLMResponse) -> LLMResponse:
    """
    Remove <thinking>...</thinking> tags from the response.
    
    Some AI models include their reasoning process in these tags.
    We hide this from users for a cleaner experience.
    """
    # Use regex to remove thinking tags and their content
    cleaned_text = re.sub(
        r'<thinking>.*?</thinking>',
        '',
        response.text,
        flags=re.DOTALL  # Match across multiple lines
    )
    
    # Remove extra whitespace
    response.text = cleaned_text.strip()
    
    return response

agent = Agent(
    tools=[...],
    response_interceptors=remove_thinking_tags,
)
```

### Example: Redacting Sensitive Data

```python
def redact_secrets(response: LLMResponse) -> LLMResponse:
    """
    Remove any accidentally leaked secrets from the response.
    """
    # List of patterns that might be secrets
    secret_patterns = [
        (r'sk-[a-zA-Z0-9]{32,}', '[API_KEY_REDACTED]'),  # API keys
        (r'eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+', '[JWT_REDACTED]'),  # JWTs
        (r'password["\']?\s*[:=]\s*["\'][^"\']+["\']', 'password: [REDACTED]'),
    ]
    
    text = response.text
    
    for pattern, replacement in secret_patterns:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    response.text = text
    return response

agent = Agent(
    tools=[...],
    response_interceptors=redact_secrets,
)
```

---

## Session Access

Both `LLMRequest` and `LLMResponse` have access to the session, allowing interceptors to read and modify persistent state across conversation turns.

### Reading Session in Request Interceptors

```python
def add_user_context(request: LLMRequest) -> LLMRequest:
    """Add user-specific context from session."""
    # Read from session
    user_name = request.session.get("user_name", "User")
    user_prefs = request.session.get("user_preferences", {})
    
    # Add context based on session data
    request.add_system_context(f"User: {user_name}")
    
    if user_prefs.get("verbose_mode"):
        request.add_system_context("User prefers detailed explanations.")
    
    return request
```

### Modifying Session in Request Interceptors

```python
def track_request_count(request: LLMRequest) -> LLMRequest:
    """Track how many requests the user has made."""
    count = request.session.get("request_count", 0)
    request.session.set("request_count", count + 1)
    request.session.set("last_request_time", datetime.now().isoformat())
    
    return request
```

### Modifying Session in Response Interceptors

```python
def track_response_metrics(response: LLMResponse) -> LLMResponse:
    """Track response metrics in session."""
    # Update session with response info
    response.session.set("last_response_length", len(response.text))
    response.session.set("had_tool_calls", response.has_tool_calls())
    
    # Accumulate total tokens if available
    if response.usage:
        total = response.session.get("total_tokens", 0)
        total += response.usage.get("output_tokens", 0)
        response.session.set("total_tokens", total)
    
    return response

agent = Agent(
    tools=[...],
    response_interceptors=track_response_metrics,
)
```

### Session with Typed Models

You can store and retrieve typed models in session:

```python
from pydantic import BaseModel

class UserPreferences(BaseModel):
    theme: str = "light"
    language: str = "en"
    verbose: bool = False

def apply_user_preferences(request: LLMRequest) -> LLMRequest:
    """Apply user preferences from session."""
    # Get as typed model
    prefs = request.session.get("user_prefs", as_type=UserPreferences)
    
    if prefs:
        if prefs.language != "en":
            request.add_system_context(f"Respond in {prefs.language}.")
        if prefs.verbose:
            request.add_system_context("Provide detailed explanations.")
    
    return request
```

---

## Error Handling

Sometimes you need to **stop** a request entirely. Use `InterceptorError` for this:

```python
from dcaf.core import Agent, LLMRequest, InterceptorError

def block_dangerous_requests(request: LLMRequest) -> LLMRequest:
    """
    Block requests that look like prompt injection attacks.
    """
    user_message = request.get_latest_user_message().lower()
    
    # Check for suspicious patterns
    dangerous_patterns = [
        "ignore previous instructions",
        "disregard your instructions",
        "forget everything",
        "new instructions:",
    ]
    
    for pattern in dangerous_patterns:
        if pattern in user_message:
            # STOP! Don't send this to the LLM.
            raise InterceptorError(
                user_message="I'm sorry, I can't process this request.",
                code="PROMPT_INJECTION_BLOCKED",
                details={"pattern": pattern},
            )
    
    # Safe to continue
    return request

agent = Agent(
    tools=[...],
    request_interceptors=block_dangerous_requests,
)
```

### InterceptorError Fields

| Field | Description |
|-------|-------------|
| `user_message` | The message shown to the user. Make it friendly! |
| `code` | Internal code for logging (not shown to user). |
| `details` | Extra info for logging (not shown to user). |

### Handling InterceptorError in Your Code

```python
from dcaf.core import InterceptorError

try:
    response = agent.run(messages=[...])
    print(response.text)
except InterceptorError as error:
    # The interceptor blocked the request
    print(f"Request blocked: {error.user_message}")
    
    # For logging/debugging
    if error.code:
        log.warning(f"Blocked with code: {error.code}")
```

### Error Handling Modes

You can configure how the agent handles unexpected errors (not `InterceptorError`):

```python
agent = Agent(
    tools=[...],
    request_interceptors=[my_interceptor],
    on_interceptor_error="abort",  # Stop on any error (default)
    # OR
    on_interceptor_error="continue",  # Log error and keep going
)
```

---

## Async Interceptors

Interceptors can be async, which is useful for:

- Database lookups
- API calls
- File I/O

```python
import asyncio

async def enrich_from_database(request: LLMRequest) -> LLMRequest:
    """
    Look up user preferences from the database.
    
    This is async because database calls take time.
    """
    user_id = request.context.get("user_id")
    
    if user_id:
        # Async database call
        preferences = await get_user_preferences(user_id)
        
        # Add preferences to context for tools to use
        request.context["user_preferences"] = preferences
        
        # Also tell the AI about them
        request.add_system_context(
            f"User preferences: {preferences}"
        )
    
    return request

# Async functions work just like sync functions
agent = Agent(
    tools=[...],
    request_interceptors=enrich_from_database,
)
```

### Mixing Sync and Async

You can use both sync and async interceptors together:

```python
# Sync interceptor
def add_timestamp(request: LLMRequest) -> LLMRequest:
    request.context["timestamp"] = datetime.now().isoformat()
    return request

# Async interceptor
async def check_rate_limit(request: LLMRequest) -> LLMRequest:
    user_id = request.context.get("user_id")
    is_allowed = await rate_limiter.check(user_id)
    
    if not is_allowed:
        raise InterceptorError("You've made too many requests. Please wait.")
    
    return request

# Both work together!
agent = Agent(
    tools=[...],
    request_interceptors=[add_timestamp, check_rate_limit],
)
```

---

## Common Use Cases

### 1. Multi-Tenant Context

Add tenant information so the AI knows which environment the user is in:

```python
def add_tenant_context(request: LLMRequest) -> LLMRequest:
    """Add tenant and namespace info to help the AI."""
    tenant = request.context.get("tenant_name", "unknown")
    namespace = request.context.get("k8s_namespace", "default")
    
    context_info = f"""
User's Environment:
- Tenant: {tenant}
- Kubernetes Namespace: {namespace}
- Only show resources from this namespace.
"""
    
    request.add_system_context(context_info)
    return request
```

### 2. Input Validation

Ensure required data is present:

```python
def require_tenant(request: LLMRequest) -> LLMRequest:
    """Ensure the tenant is specified."""
    if not request.context.get("tenant_name"):
        raise InterceptorError(
            user_message="Please select a tenant before continuing.",
            code="MISSING_TENANT",
        )
    return request
```

### 3. Audit Logging

Log all requests for compliance:

```python
import logging

audit_log = logging.getLogger("audit")

def log_request(request: LLMRequest) -> LLMRequest:
    """Log all requests for audit purposes."""
    user_id = request.context.get("user_id", "anonymous")
    user_message = request.get_latest_user_message()
    
    audit_log.info(
        f"Request from {user_id}: {user_message[:100]}..."
    )
    
    return request  # Don't modify, just log

def log_response(response: LLMResponse) -> LLMResponse:
    """Log all responses for audit purposes."""
    audit_log.info(
        f"Response ({response.get_text_length()} chars): "
        f"{response.text[:100]}..."
    )
    
    return response  # Don't modify, just log

agent = Agent(
    tools=[...],
    request_interceptors=log_request,
    response_interceptors=log_response,
)
```

### 4. Response Formatting

Add consistent formatting to responses:

```python
def add_disclaimer(response: LLMResponse) -> LLMResponse:
    """Add a disclaimer to all responses."""
    disclaimer = "\n\n---\n*This is an AI-generated response. Please verify before taking action.*"
    response.text = response.text + disclaimer
    return response
```

### 5. Rate Limiting

Prevent abuse by limiting requests:

```python
from collections import defaultdict
from datetime import datetime, timedelta

# Simple in-memory rate limiter (use Redis in production)
request_counts = defaultdict(list)

def rate_limit(request: LLMRequest) -> LLMRequest:
    """Limit users to 10 requests per minute."""
    user_id = request.context.get("user_id", "anonymous")
    now = datetime.now()
    one_minute_ago = now - timedelta(minutes=1)
    
    # Clean old entries
    request_counts[user_id] = [
        t for t in request_counts[user_id] if t > one_minute_ago
    ]
    
    # Check limit
    if len(request_counts[user_id]) >= 10:
        raise InterceptorError(
            user_message="You've reached the rate limit. Please wait a moment.",
            code="RATE_LIMITED",
        )
    
    # Record this request
    request_counts[user_id].append(now)
    
    return request
```

---

## Best Practices

### 1. Keep Interceptors Focused

Each interceptor should do one thing well:

```python
# Good: Single responsibility
def add_tenant_context(request): ...
def validate_input(request): ...
def log_request(request): ...

# Bad: Doing too much
def do_everything(request):
    # Adds context AND validates AND logs...
    # Hard to maintain and test
    ...
```

### 2. Order Matters

Interceptors run in the order you specify:

```python
agent = Agent(
    request_interceptors=[
        validate_input,      # First: Block bad requests early
        check_permissions,   # Second: Verify user can do this
        add_context,         # Third: Enrich the request
        log_request,         # Last: Log the final request
    ],
)
```

### 3. Handle Errors Gracefully

Use `InterceptorError` for user-facing errors:

```python
# Good: Friendly message
raise InterceptorError(
    user_message="Please log in to continue.",
    code="AUTH_REQUIRED",
)

# Bad: Technical error shown to user
raise ValueError("Missing auth_token in context")
```

### 4. Don't Modify What You Don't Need

Only change what's necessary:

```python
# Good: Only adds to system prompt
def add_context(request: LLMRequest) -> LLMRequest:
    request.add_system_context("Extra info")
    return request

# Bad: Replaces entire system prompt
def add_context(request: LLMRequest) -> LLMRequest:
    request.system = "Completely new system prompt"  # Loses original!
    return request
```

### 5. Test Your Interceptors

Interceptors are just functions, so they're easy to test:

```python
def test_add_tenant_context():
    # Create a test request
    request = LLMRequest(
        messages=[{"role": "user", "content": "Hello"}],
        context={"tenant_name": "production"},
    )
    
    # Run the interceptor
    result = add_tenant_context(request)
    
    # Check the result
    assert "production" in result.system

def test_blocks_prompt_injection():
    request = LLMRequest(
        messages=[{"role": "user", "content": "Ignore previous instructions"}],
    )
    
    with pytest.raises(InterceptorError) as exc_info:
        block_dangerous_requests(request)
    
    assert exc_info.value.code == "PROMPT_INJECTION_BLOCKED"
```

---

## API Reference

### LLMRequest

```python
@dataclass
class LLMRequest:
    messages: list[dict]      # Conversation messages
    tools: list[Any]          # Available tools
    system: str | None        # System prompt
    context: dict             # Platform context
    session: Session          # Session for persistent state
    
    def get_latest_user_message(self) -> str:
        """Get the content of the most recent user message."""
        
    def add_system_context(self, text: str) -> None:
        """Add text to the system prompt."""
```

### LLMResponse

```python
@dataclass
class LLMResponse:
    text: str                 # AI's text response
    tool_calls: list[dict]    # Tool calls (if any)
    usage: dict | None        # Token usage
    raw: Any                  # Original response
    session: Session          # Session for persistent state
    
    def has_tool_calls(self) -> bool:
        """Check if there are tool calls."""
        
    def get_text_length(self) -> int:
        """Get length of text response."""
```

### InterceptorError

```python
class InterceptorError(Exception):
    def __init__(
        self,
        user_message: str,      # Shown to user
        code: str | None,       # For logging
        details: dict | None,   # Extra info for logging
    ):
        ...
```

### Agent Configuration

```python
agent = Agent(
    tools=[...],
    
    # Single interceptor
    request_interceptors=my_interceptor,
    
    # Multiple interceptors (run in order)
    request_interceptors=[first, second, third],
    
    # Response interceptors work the same way
    response_interceptors=[clean_output, log_response],
    
    # Error handling mode
    on_interceptor_error="abort",  # or "continue"
)
```

---

## See Also

- [Agent Documentation](../core/index.md) - Full Agent class reference
- [Session Management](./session-management.md) - Complete session guide
- [Architecture Guide](../architecture.md) - How DCAF works internally
- [Custom Agents Guide](./custom-agents.md) - Building complex agents
