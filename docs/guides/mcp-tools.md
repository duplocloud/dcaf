# MCP Tools Guide

This guide covers how to use external MCP (Model Context Protocol) servers with DCAF agents, allowing you to connect to and use tools exposed by MCP-compatible services.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Quick Start](#quick-start)
3. [Transport Protocols](#transport-protocols)
4. [Tool Filtering](#tool-filtering)
5. [Tool Hooks](#tool-hooks)
6. [Using with Agents](#using-with-agents)
7. [Connection Management](#connection-management)
8. [Logging and Monitoring](#logging-and-monitoring)
9. [Error Handling](#error-handling)
10. [Best Practices](#best-practices)

---

## Introduction

The Model Context Protocol (MCP) is an open standard for connecting AI assistants to external data sources and tools. DCAF provides `MCPTool` - a framework-agnostic wrapper that lets you connect to any MCP server and use its tools alongside your local DCAF tools.

### What is MCP?

MCP servers expose:

- **Tools**: Functions that can be called by AI agents
- **Resources**: Data that can be read by AI agents
- **Prompts**: Pre-defined prompt templates

DCAF's `MCPTool` focuses on **consuming tools** from external MCP servers.

### Why Use MCPTool?

- **Extend your agent's capabilities** with tools from external services
- **Reuse existing MCP servers** (databases, APIs, file systems, etc.)
- **Framework-agnostic** - no direct dependency on underlying LLM framework
- **Seamless integration** - MCP tools work alongside native DCAF tools

---

## Quick Start

### Installation

MCP tools require the `mcp` package:

```bash
pip install mcp
```

### Basic Usage (Automatic Lifecycle)

DCAF automatically manages the MCP connection lifecycle - just pass `MCPTool` to your agent:

```python
from dcaf.core import Agent
from dcaf.mcp import MCPTool
from dcaf.tools import tool

# Define a local tool
@tool(description="Get current time")
def get_time() -> str:
    from datetime import datetime
    return datetime.now().isoformat()

# Configure MCP server connection
mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
)

# Just pass it to the agent - DCAF handles connect/disconnect automatically!
async def main():
    agent = Agent(tools=[get_time, mcp_tool])
    result = await agent.arun("Search for Python tutorials and tell me the time")
    print(result.text)
```

The framework automatically:
1. Connects to the MCP server when the agent runs
2. Makes tools available to the LLM
3. Disconnects and cleans up after the run completes

### Manual Connection (Optional)

If you need explicit control over the connection lifecycle, you can still use the async context manager:

```python
async def main():
    async with mcp_tool:
        # Connection is established here
        agent = Agent(tools=[mcp_tool])
        result = await agent.arun("Search for something")
    # Connection is closed here
```

---

## Transport Protocols

DCAF's `MCPTool` supports three transport protocols for connecting to MCP servers.

### Streamable HTTP (Recommended)

For HTTP-based MCP servers. This is the recommended protocol for production use.

```python
from dcaf.mcp import MCPTool

mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    timeout_seconds=30,
)
```

### Server-Sent Events (SSE)

For servers using SSE transport (deprecated in favor of streamable-http):

```python
mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="sse",
)
```

!!! warning "Deprecation Notice"
    SSE transport is deprecated. Use `streamable-http` for new integrations.

### Standard I/O (stdio)

For running a local MCP server process. The server communicates via stdin/stdout.

```python
mcp_tool = MCPTool(
    command="python my_mcp_server.py",
    transport="stdio",
    env={"API_KEY": "secret"},  # Optional environment variables
)
```

Use stdio when:

- Running a local MCP server script
- The MCP server is packaged as a CLI tool
- You need process isolation

### Choosing a Transport

| Transport | Use Case | Example |
|-----------|----------|---------|
| `streamable-http` | Remote HTTP servers | Cloud APIs, microservices |
| `sse` | Legacy SSE servers | Older MCP implementations |
| `stdio` | Local processes | CLI tools, scripts |

---

## Tool Filtering

When an MCP server exposes many tools, you can filter which ones to use.

### Include Specific Tools

Only include the tools you need:

```python
mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    include_tools=["search", "query", "get_document"],
)
```

### Exclude Specific Tools

Exclude tools you don't want:

```python
mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    exclude_tools=["dangerous_delete", "admin_reset"],
)
```

### Add Tool Name Prefix

Prevent name collisions by prefixing tool names:

```python
mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    tool_name_prefix="search",  # Tools become: search_query, search_fetch, etc.
)
```

This is useful when combining multiple MCP servers:

```python
# Two MCP servers with potentially conflicting tool names
search_mcp = MCPTool(
    url="http://search-service:8000/mcp",
    transport="streamable-http",
    tool_name_prefix="search",
)

db_mcp = MCPTool(
    url="http://db-service:8000/mcp",
    transport="streamable-http",
    tool_name_prefix="db",
)

# Multiple MCP servers - DCAF manages both automatically
agent = Agent(tools=[search_mcp, db_mcp])
result = await agent.arun("Search and query")
# Agent sees: search_query, search_fetch, db_query, db_insert, etc.
```

---

## Tool Hooks

DCAF allows you to intercept MCP tool calls using **pre-hooks** and **post-hooks**. This is useful for logging, validation, transformation, telemetry, or modifying tool results.

### MCPToolCall Context Object

Both hooks receive an `MCPToolCall` object containing information about the tool call:

```python
from dcaf.mcp import MCPToolCall

# MCPToolCall attributes:
# - tool_name: str           - Name of the MCP tool being called
# - arguments: dict          - Arguments passed to the tool
# - result: Any              - Tool result (only in post-hook)
# - duration: float | None   - Execution time in seconds (only in post-hook)
# - error: Exception | None  - Exception if tool failed (only in post-hook)
# - metadata: dict           - Additional info (target URL/command, transport)
```

### Pre-Hook

A pre-hook runs **before** each MCP tool execution. Use it for:

- Logging tool calls
- Validating arguments
- Modifying arguments (though the object is informational; modify kwargs in advanced use)
- Access control checks

```python
from dcaf.mcp import MCPTool, MCPToolCall

async def log_tool_calls(call: MCPToolCall) -> None:
    """Log every MCP tool call before execution."""
    print(f"Calling tool: {call.tool_name}")
    print(f"Arguments: {call.arguments}")
    print(f"Target: {call.metadata.get('target')}")

mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    pre_hook=log_tool_calls,
)
```

Pre-hooks can be sync or async:

```python
# Sync pre-hook
def sync_pre_hook(call: MCPToolCall) -> None:
    print(f"Tool: {call.tool_name}")

# Async pre-hook
async def async_pre_hook(call: MCPToolCall) -> None:
    await log_to_external_service(call.tool_name, call.arguments)
```

### Post-Hook

A post-hook runs **after** each MCP tool execution. Use it for:

- Logging results
- Transforming or filtering results
- Recording metrics/telemetry
- Error handling

#### What is `call.result`?

The `call.result` attribute contains **whatever the MCP tool returned** - it's the raw result from the MCP server's tool execution. The type is `Any` because different MCP tools return different types:

| Result Type | Example |
|-------------|---------|
| `str` | `"Found 5 results for 'python tutorials'"` (most common) |
| `dict` | `{"status": "success", "count": 5, "items": [...]}` |
| `list` | `["result1", "result2", "result3"]` |
| `None` | Tools with side effects that don't return data |

In practice, most MCP tools return **strings** containing the tool's text output. If the tool returns structured data, it's often a JSON string that you'd parse if needed.

```python
from dcaf.mcp import MCPTool, MCPToolCall

async def process_results(call: MCPToolCall):
    """Process and optionally transform tool results."""
    print(f"Tool {call.tool_name} completed in {call.duration:.3f}s")

    if call.error:
        print(f"Tool failed with: {call.error}")
        # You can return a fallback value
        return "Tool execution failed, please try again"

    print(f"Result: {call.result}")

    # Return the result (or a transformed version)
    return call.result

mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    post_hook=process_results,
)
```

**Important**: The post-hook's return value replaces the tool's result. Return `call.result` to keep the original, or return a modified value to transform it.

### Transforming Results

Post-hooks can transform tool results before they reach the agent:

```python
async def sanitize_results(call: MCPToolCall):
    """Remove sensitive data from tool results."""
    result = call.result

    if isinstance(result, str):
        # Redact API keys or sensitive patterns
        result = re.sub(r'api_key=\w+', 'api_key=REDACTED', result)

    return result

mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    post_hook=sanitize_results,
)
```

### Error Handling in Hooks

Post-hooks are called even when tools fail, with `call.error` populated:

```python
async def handle_errors(call: MCPToolCall):
    """Handle tool errors gracefully."""
    if call.error:
        # Log the error
        logger.error(f"Tool {call.tool_name} failed: {call.error}")

        # Return a user-friendly message instead of raising
        return f"The {call.tool_name} operation failed. Please try again."

    return call.result

mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    post_hook=handle_errors,
)
```

### Complete Example: Logging and Metrics

Here's a complete example combining pre and post hooks for observability:

```python
import time
from dcaf.core import Agent
from dcaf.mcp import MCPTool, MCPToolCall

# Track metrics
tool_metrics = {"calls": 0, "errors": 0, "total_duration": 0.0}

async def pre_hook(call: MCPToolCall) -> None:
    """Log before each tool call."""
    print(f">>> Calling {call.tool_name}")
    print(f"    Args: {call.arguments}")
    tool_metrics["calls"] += 1

async def post_hook(call: MCPToolCall):
    """Log after each tool call and collect metrics."""
    if call.error:
        print(f"<<< {call.tool_name} FAILED: {call.error}")
        tool_metrics["errors"] += 1
    else:
        print(f"<<< {call.tool_name} completed in {call.duration:.3f}s")
        tool_metrics["total_duration"] += call.duration or 0

    return call.result

# Create MCP tool with hooks
mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    pre_hook=pre_hook,
    post_hook=post_hook,
)

async def main():
    agent = Agent(tools=[mcp_tool])
    result = await agent.arun("Search for Python tutorials")

    print(f"\nMetrics: {tool_metrics}")
    # Output: Metrics: {'calls': 2, 'errors': 0, 'total_duration': 0.456}
```

### Hook Type Signatures

For type checking, use these signatures:

```python
from typing import Any, Awaitable, Callable
from dcaf.mcp import MCPToolCall

# Pre-hook: receives MCPToolCall, returns None
PreHookFunc = Callable[[MCPToolCall], Awaitable[None] | None]

# Post-hook: receives MCPToolCall, returns transformed result (or original)
PostHookFunc = Callable[[MCPToolCall], Awaitable[Any] | Any]
```

---

## Using with Agents

### Automatic Lifecycle (Recommended)

Just pass `MCPTool` to your agent - DCAF handles the rest:

```python
from dcaf.core import Agent
from dcaf.mcp import MCPTool

mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
)

async def main():
    # No context manager needed - DCAF manages connection automatically
    agent = Agent(tools=[mcp_tool])
    result = await agent.arun("Search for something")
    # Connection is automatically established and cleaned up
```

This is the simplest and recommended approach. The framework:
- Connects when the agent runs
- Disconnects after the run completes
- Handles errors and cleanup automatically

### Explicit Context Manager (Optional)

Use the context manager when you need to:
- Reuse a connection across multiple agent runs
- Inspect available tools before running
- Have explicit control over connection timing

```python
async def main():
    async with mcp_tool:
        # Connection established - you can inspect tools
        print(f"Available tools: {mcp_tool.get_tool_names()}")

        agent = Agent(tools=[mcp_tool])

        # Multiple runs share the same connection
        result1 = await agent.arun("Search for X")
        result2 = await agent.arun("Now search for Y")

    # Connection explicitly closed here
```

### Manual Connection Management

For fine-grained control:

```python
async def main():
    await mcp_tool.connect()

    try:
        agent = Agent(tools=[mcp_tool])
        result = await agent.arun("Search for something")
    finally:
        await mcp_tool.close()
```

### Combining with Local Tools

MCP tools work seamlessly with native DCAF tools:

```python
from dcaf.core import Agent
from dcaf.mcp import MCPTool
from dcaf.tools import tool

# Local DCAF tool
@tool(description="Calculate the sum of two numbers")
def add(a: int, b: int) -> str:
    return str(a + b)

# Local tool requiring approval
@tool(requires_approval=True, description="Send an email")
def send_email(to: str, subject: str, body: str) -> str:
    # Send email logic
    return f"Email sent to {to}"

# External MCP tools
mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
)

async def main():
    async with mcp_tool:
        # Agent has access to both local and MCP tools
        agent = Agent(
            tools=[add, send_email, mcp_tool],
            system_prompt="You are a helpful assistant with math, email, and search capabilities."
        )

        result = await agent.arun(
            "Search for the population of Tokyo, add 1000 to it, and email the result to bob@example.com"
        )
```

### Checking Available Tools

After connecting, you can inspect which tools are available:

```python
async with mcp_tool:
    # Get list of tool names
    tool_names = mcp_tool.get_tool_names()
    print(f"Available MCP tools: {tool_names}")

    # Output: ['search', 'query', 'fetch_document', ...]
```

---

## Connection Management

### Connection State

Check if the connection is established:

```python
mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
)

print(mcp_tool.initialized)  # False - not connected yet

async with mcp_tool:
    print(mcp_tool.initialized)  # True - connected

print(mcp_tool.initialized)  # False - connection closed
```

### Connection Health Check

Check if an existing connection is still alive:

```python
async with mcp_tool:
    is_alive = await mcp_tool.is_alive()
    if not is_alive:
        # Reconnect if needed
        await mcp_tool.connect(force=True)
```

### Force Reconnection

Force a fresh connection, even if already connected:

```python
await mcp_tool.connect(force=True)
```

### Refresh on Each Run

For long-running applications, refresh the connection and tools on each agent run:

```python
mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    refresh_connection=True,  # Refresh on each agent run
)
```

---

## Logging and Monitoring

DCAF provides comprehensive logging for MCP tools to help you monitor connections, track tool usage, and debug issues.

### Log Levels

MCP logging uses Python's standard logging module under `dcaf.mcp.tools`:

| Level | What's Logged |
|-------|---------------|
| `INFO` | Connection lifecycle events, tool discovery, tool execution |
| `DEBUG` | Detailed state changes, tool result previews |
| `WARNING` | Connection issues, exceptions during cleanup |
| `ERROR` | Failed connections, tool execution errors |

### Enabling MCP Logging

```python
import logging

# Enable INFO level to see connection and tool events
logging.basicConfig(level=logging.INFO)

# Or enable DEBUG for more detail
logging.getLogger("dcaf.mcp.tools").setLevel(logging.DEBUG)
```

### Lifecycle Events

When using MCPTool, you'll see logs for:

**Configuration:**
```
INFO - 🔌 MCP: Configured MCPTool (transport=streamable-http, target=http://localhost:8000/mcp)
INFO - 🔌 MCP: Tool filter - include: ['search', 'query']
INFO - 🔌 MCP: Tool name prefix: docs
```

**Connection:**
```
INFO - 🔌 MCP: Connecting to MCP server (target=http://localhost:8000/mcp, force=False)...
INFO - 🔌 MCP: ✅ Connected successfully - 3 tools available
INFO - 🔌 MCP: Available tools: ['search', 'query', 'fetch']
```

**Disconnection:**
```
INFO - 🔌 MCP: Closing connection (target=http://localhost:8000/mcp)...
INFO - 🔌 MCP: ✅ Connection closed successfully
```

### Tool Execution Logging

When the LLM calls an MCP tool, you'll see:

```
INFO - 🔧 MCP Tool Call: searchDocumentation (target=http://localhost:8000/mcp)
INFO - 🔧 MCP Tool Args: {'query': 'kubernetes deployment'}
INFO - 🔧 MCP Tool Result: searchDocumentation completed in 0.234s
```

If a tool fails:
```
ERROR - 🔧 MCP Tool Error: searchDocumentation failed after 5.012s - TimeoutError: Connection timed out
```

### Agent Integration Logging

When adding MCPTool to an agent, you'll see:

```
INFO - 🔌 MCP: Added MCPTool to agent - will auto-connect (transport=streamable-http, target=http://localhost:8000/mcp)
```

Or if pre-connected:
```
INFO - 🔌 MCP: Added pre-connected MCPTool to agent (target=http://localhost:8000/mcp, tools=['search', 'query'])
```

### Production Logging Configuration

For production, configure logging to capture MCP events:

```python
import logging

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Optionally increase verbosity for debugging
# logging.getLogger("dcaf.mcp.tools").setLevel(logging.DEBUG)
```

### Log Message Reference

| Prefix | Category | Example |
|--------|----------|---------|
| `🔌 MCP:` | Connection lifecycle | Connecting, connected, closing, closed |
| `🔧 MCP Tool` | Tool execution | Tool calls, arguments, results, errors |

---

## Error Handling

### Connection Errors

Handle connection failures gracefully:

```python
from dcaf.mcp import MCPTool

mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    timeout_seconds=10,
)

async def main():
    try:
        async with mcp_tool:
            agent = Agent(tools=[mcp_tool])
            result = await agent.arun("Search for something")
    except ConnectionError as e:
        print(f"Failed to connect to MCP server: {e}")
        # Fallback to local-only tools
        agent = Agent(tools=[local_tool])
        result = await agent.arun("Search for something")
```

### Not Connected Errors

Operations on an unconnected `MCPTool` raise `RuntimeError`:

```python
mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
)

# This raises RuntimeError - not connected yet
try:
    tool_names = mcp_tool.get_tool_names()
except RuntimeError as e:
    print(e)  # "MCPTool not connected. Use 'async with mcp_tool:' or call 'await mcp_tool.connect()' first."
```

### Timeout Configuration

Configure connection and read timeouts:

```python
mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    timeout_seconds=30,  # 30 second timeout
)
```

---

## Best Practices

### 1. Always Use Context Managers

Ensure connections are properly closed:

```python
# ✅ Good - automatic cleanup
async with mcp_tool:
    agent = Agent(tools=[mcp_tool])
    result = await agent.arun("...")

# ❌ Bad - connection may leak
await mcp_tool.connect()
agent = Agent(tools=[mcp_tool])
result = await agent.arun("...")
# Forgot to close!
```

### 2. Filter Tools for Security

Only expose necessary tools to the agent:

```python
# ✅ Good - explicit allowlist
mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    include_tools=["search", "read"],  # Only safe, read-only tools
)

# ❌ Risky - all tools exposed
mcp_tool = MCPTool(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    # No filtering - agent can use any tool
)
```

### 3. Use Tool Name Prefixes for Multiple Servers

Prevent name collisions:

```python
# ✅ Good - clear namespacing
search_mcp = MCPTool(url="...", tool_name_prefix="search")
db_mcp = MCPTool(url="...", tool_name_prefix="db")

# ❌ Bad - potential name collision
search_mcp = MCPTool(url="...")  # Has "query" tool
db_mcp = MCPTool(url="...")      # Also has "query" tool - collision!
```

### 4. Handle Connection Failures

Always have a fallback strategy:

```python
async def run_with_fallback(message: str):
    try:
        async with mcp_tool:
            agent = Agent(tools=[local_tools, mcp_tool])
            return await agent.arun(message)
    except Exception as e:
        logger.warning(f"MCP unavailable: {e}, falling back to local tools")
        agent = Agent(tools=[local_tools])
        return await agent.arun(message)
```

### 5. Enable Logging in Production

Enable MCP logging to track connections and tool usage:

```python
import logging

# Enable INFO level for MCP events
logging.getLogger("dcaf.mcp.tools").setLevel(logging.INFO)

# You'll see:
# INFO - 🔌 MCP: ✅ Connected successfully - 3 tools available
# INFO - 🔧 MCP Tool Call: search (target=http://...)
# INFO - 🔧 MCP Tool Result: search completed in 0.234s
```

### 6. Inspect Tools After Connection

For debugging, verify which tools are available:

```python
async with mcp_tool:
    tools = mcp_tool.get_tool_names()
    logger.info(f"Connected to MCP server with tools: {tools}")
```

---

## API Reference

### MCPTool Class

```python
class MCPTool:
    def __init__(
        self,
        command: Optional[str] = None,        # For stdio transport
        *,
        url: Optional[str] = None,            # For HTTP transports
        env: Optional[Dict[str, str]] = None, # Environment for stdio
        transport: Literal["stdio", "sse", "streamable-http"] = "stdio",
        timeout_seconds: int = 10,
        include_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
        tool_name_prefix: Optional[str] = None,
        refresh_connection: bool = False,
        pre_hook: Optional[Callable[[MCPToolCall], Awaitable[None] | None]] = None,
        post_hook: Optional[Callable[[MCPToolCall], Awaitable[Any] | Any]] = None,
    ): ...
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `initialized` | `bool` | Whether connected to the MCP server |
| `refresh_connection` | `bool` | Whether to refresh on each agent run |

### Methods

| Method | Description |
|--------|-------------|
| `async connect(force=False)` | Connect to the MCP server |
| `async close()` | Close the connection |
| `async is_alive()` | Check if connection is healthy |
| `get_tool_names()` | Get list of available tool names |

### MCPToolCall Class

```python
@dataclass
class MCPToolCall:
    tool_name: str                    # Name of the MCP tool
    arguments: dict[str, Any]         # Arguments passed to the tool
    result: Any = None                # Tool result (post-hook only)
    duration: float | None = None     # Execution time in seconds (post-hook only)
    error: Exception | None = None    # Exception if failed (post-hook only)
    metadata: dict[str, Any]          # Additional info (target, transport)
```

### Context Manager

```python
async with mcp_tool:
    # Connection established
    ...
# Connection automatically closed
```

---

## See Also

- [Building Tools Guide](./building-tools.md) - Creating native DCAF tools
- [Framework Adapters](./framework-adapters.md) - How DCAF abstracts LLM frameworks
- [Custom Agents Guide](./custom-agents.md) - Building complex agent workflows
