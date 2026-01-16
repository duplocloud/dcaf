# MCP Tools Guide

This guide covers how to use external MCP (Model Context Protocol) servers with DCAF agents, allowing you to connect to and use tools exposed by MCP-compatible services.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Quick Start](#quick-start)
3. [Transport Protocols](#transport-protocols)
4. [Tool Filtering](#tool-filtering)
5. [Using with Agents](#using-with-agents)
6. [Connection Management](#connection-management)
7. [Error Handling](#error-handling)
8. [Best Practices](#best-practices)

---

## Introduction

The Model Context Protocol (MCP) is an open standard for connecting AI assistants to external data sources and tools. DCAF provides `MCPTools` - a framework-agnostic wrapper that lets you connect to any MCP server and use its tools alongside your local DCAF tools.

### What is MCP?

MCP servers expose:

- **Tools**: Functions that can be called by AI agents
- **Resources**: Data that can be read by AI agents
- **Prompts**: Pre-defined prompt templates

DCAF's `MCPTools` focuses on **consuming tools** from external MCP servers.

### Why Use MCPTools?

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

DCAF automatically manages the MCP connection lifecycle - just pass `MCPTools` to your agent:

```python
from dcaf.core import Agent
from dcaf.mcp import MCPTools
from dcaf.tools import tool

# Define a local tool
@tool(description="Get current time")
def get_time() -> str:
    from datetime import datetime
    return datetime.now().isoformat()

# Configure MCP server connection
mcp_tools = MCPTools(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
)

# Just pass it to the agent - DCAF handles connect/disconnect automatically!
async def main():
    agent = Agent(tools=[get_time, mcp_tools])
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
    async with mcp_tools:
        # Connection is established here
        agent = Agent(tools=[mcp_tools])
        result = await agent.arun("Search for something")
    # Connection is closed here
```

---

## Transport Protocols

DCAF's `MCPTools` supports three transport protocols for connecting to MCP servers.

### Streamable HTTP (Recommended)

For HTTP-based MCP servers. This is the recommended protocol for production use.

```python
from dcaf.mcp import MCPTools

mcp_tools = MCPTools(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    timeout_seconds=30,
)
```

### Server-Sent Events (SSE)

For servers using SSE transport (deprecated in favor of streamable-http):

```python
mcp_tools = MCPTools(
    url="http://localhost:8000/mcp",
    transport="sse",
)
```

!!! warning "Deprecation Notice"
    SSE transport is deprecated. Use `streamable-http` for new integrations.

### Standard I/O (stdio)

For running a local MCP server process. The server communicates via stdin/stdout.

```python
mcp_tools = MCPTools(
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
mcp_tools = MCPTools(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    include_tools=["search", "query", "get_document"],
)
```

### Exclude Specific Tools

Exclude tools you don't want:

```python
mcp_tools = MCPTools(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    exclude_tools=["dangerous_delete", "admin_reset"],
)
```

### Add Tool Name Prefix

Prevent name collisions by prefixing tool names:

```python
mcp_tools = MCPTools(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    tool_name_prefix="search",  # Tools become: search_query, search_fetch, etc.
)
```

This is useful when combining multiple MCP servers:

```python
# Two MCP servers with potentially conflicting tool names
search_mcp = MCPTools(
    url="http://search-service:8000/mcp",
    transport="streamable-http",
    tool_name_prefix="search",
)

db_mcp = MCPTools(
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

## Using with Agents

### Automatic Lifecycle (Recommended)

Just pass `MCPTools` to your agent - DCAF handles the rest:

```python
from dcaf.core import Agent
from dcaf.mcp import MCPTools

mcp_tools = MCPTools(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
)

async def main():
    # No context manager needed - DCAF manages connection automatically
    agent = Agent(tools=[mcp_tools])
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
    async with mcp_tools:
        # Connection established - you can inspect tools
        print(f"Available tools: {mcp_tools.get_tool_names()}")

        agent = Agent(tools=[mcp_tools])

        # Multiple runs share the same connection
        result1 = await agent.arun("Search for X")
        result2 = await agent.arun("Now search for Y")

    # Connection explicitly closed here
```

### Manual Connection Management

For fine-grained control:

```python
async def main():
    await mcp_tools.connect()

    try:
        agent = Agent(tools=[mcp_tools])
        result = await agent.arun("Search for something")
    finally:
        await mcp_tools.close()
```

### Combining with Local Tools

MCP tools work seamlessly with native DCAF tools:

```python
from dcaf.core import Agent
from dcaf.mcp import MCPTools
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
mcp_tools = MCPTools(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
)

async def main():
    async with mcp_tools:
        # Agent has access to both local and MCP tools
        agent = Agent(
            tools=[add, send_email, mcp_tools],
            system_prompt="You are a helpful assistant with math, email, and search capabilities."
        )

        result = await agent.arun(
            "Search for the population of Tokyo, add 1000 to it, and email the result to bob@example.com"
        )
```

### Checking Available Tools

After connecting, you can inspect which tools are available:

```python
async with mcp_tools:
    # Get list of tool names
    tool_names = mcp_tools.get_tool_names()
    print(f"Available MCP tools: {tool_names}")

    # Output: ['search', 'query', 'fetch_document', ...]
```

---

## Connection Management

### Connection State

Check if the connection is established:

```python
mcp_tools = MCPTools(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
)

print(mcp_tools.initialized)  # False - not connected yet

async with mcp_tools:
    print(mcp_tools.initialized)  # True - connected

print(mcp_tools.initialized)  # False - connection closed
```

### Connection Health Check

Check if an existing connection is still alive:

```python
async with mcp_tools:
    is_alive = await mcp_tools.is_alive()
    if not is_alive:
        # Reconnect if needed
        await mcp_tools.connect(force=True)
```

### Force Reconnection

Force a fresh connection, even if already connected:

```python
await mcp_tools.connect(force=True)
```

### Refresh on Each Run

For long-running applications, refresh the connection and tools on each agent run:

```python
mcp_tools = MCPTools(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    refresh_connection=True,  # Refresh on each agent run
)
```

---

## Error Handling

### Connection Errors

Handle connection failures gracefully:

```python
from dcaf.mcp import MCPTools

mcp_tools = MCPTools(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    timeout_seconds=10,
)

async def main():
    try:
        async with mcp_tools:
            agent = Agent(tools=[mcp_tools])
            result = await agent.arun("Search for something")
    except ConnectionError as e:
        print(f"Failed to connect to MCP server: {e}")
        # Fallback to local-only tools
        agent = Agent(tools=[local_tool])
        result = await agent.arun("Search for something")
```

### Not Connected Errors

Operations on an unconnected `MCPTools` raise `RuntimeError`:

```python
mcp_tools = MCPTools(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
)

# This raises RuntimeError - not connected yet
try:
    tool_names = mcp_tools.get_tool_names()
except RuntimeError as e:
    print(e)  # "MCPTools not connected. Use 'async with mcp_tools:' or call 'await mcp_tools.connect()' first."
```

### Timeout Configuration

Configure connection and read timeouts:

```python
mcp_tools = MCPTools(
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
async with mcp_tools:
    agent = Agent(tools=[mcp_tools])
    result = await agent.arun("...")

# ❌ Bad - connection may leak
await mcp_tools.connect()
agent = Agent(tools=[mcp_tools])
result = await agent.arun("...")
# Forgot to close!
```

### 2. Filter Tools for Security

Only expose necessary tools to the agent:

```python
# ✅ Good - explicit allowlist
mcp_tools = MCPTools(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    include_tools=["search", "read"],  # Only safe, read-only tools
)

# ❌ Risky - all tools exposed
mcp_tools = MCPTools(
    url="http://localhost:8000/mcp",
    transport="streamable-http",
    # No filtering - agent can use any tool
)
```

### 3. Use Tool Name Prefixes for Multiple Servers

Prevent name collisions:

```python
# ✅ Good - clear namespacing
search_mcp = MCPTools(url="...", tool_name_prefix="search")
db_mcp = MCPTools(url="...", tool_name_prefix="db")

# ❌ Bad - potential name collision
search_mcp = MCPTools(url="...")  # Has "query" tool
db_mcp = MCPTools(url="...")      # Also has "query" tool - collision!
```

### 4. Handle Connection Failures

Always have a fallback strategy:

```python
async def run_with_fallback(message: str):
    try:
        async with mcp_tools:
            agent = Agent(tools=[local_tools, mcp_tools])
            return await agent.arun(message)
    except Exception as e:
        logger.warning(f"MCP unavailable: {e}, falling back to local tools")
        agent = Agent(tools=[local_tools])
        return await agent.arun(message)
```

### 5. Log Available Tools

For debugging, log what tools are available:

```python
async with mcp_tools:
    tools = mcp_tools.get_tool_names()
    logger.info(f"Connected to MCP server with tools: {tools}")
```

---

## API Reference

### MCPTools Class

```python
class MCPTools:
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

### Context Manager

```python
async with mcp_tools:
    # Connection established
    ...
# Connection automatically closed
```

---

## See Also

- [Building Tools Guide](./building-tools.md) - Creating native DCAF tools
- [Framework Adapters](./framework-adapters.md) - How DCAF abstracts LLM frameworks
- [Custom Agents Guide](./custom-agents.md) - Building complex agent workflows
