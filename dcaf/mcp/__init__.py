"""
DCAF MCP (Model Context Protocol) Integration.

This module provides integration with FastMCP, enabling agents to be served
via FastMCP as the primary server framework. This exposes:

1. MCP protocol at /mcp (for AI assistants like Claude)
2. HTTP REST endpoints at /api/chat (for web frontends like HelpDesk)
3. All on a single port!

Installation:
    pip install dcaf[mcp]

Quick Start - FastMCP as Primary Server:
    from dcaf.core import Agent
    from dcaf.mcp import serve
    from dcaf.tools import tool
    
    @tool(description="Query infrastructure")
    def query_infra(query: str) -> str:
        return f"Results for: {query}"
    
    agent = Agent(tools=[query_infra])
    serve(agent)  # MCP + HTTP on same port!
    # MCP at http://localhost:8000/mcp
    # Chat at http://localhost:8000/api/chat

Programmatic Control:
    from dcaf.mcp import create_server
    
    agent = Agent(tools=[...])
    mcp = create_server(agent, name="my-agent")
    
    # Add custom resources
    @mcp.resource("db://schema")
    async def get_schema() -> str:
        return schema_json
    
    # Add custom tools beyond agent tools
    @mcp.tool()
    def custom_tool(x: int) -> int:
        return x * 2
    
    mcp.run()

Note:
    This module requires the 'mcp' optional dependency:
    pip install dcaf[mcp]
"""

from typing import TYPE_CHECKING, Optional, List, Callable, Any, Union
import logging
import json

if TYPE_CHECKING:
    from ..core.agent import Agent
    from fastmcp import FastMCP as FastMCPType

__all__ = [
    "serve",
    "create_server",
    "MCPIntegrationError",
    # Legacy names for backwards compatibility
    "serve_mcp",
    "create_mcp_server",
    "get_mcp_tool_schemas",
]

logger = logging.getLogger(__name__)


class MCPIntegrationError(Exception):
    """Raised when MCP integration fails."""
    pass


def serve(
    agent: "Agent",
    name: Optional[str] = None,
    port: int = 8000,
    host: str = "0.0.0.0",
    additional_tools: Optional[List[Callable]] = None,
    additional_resources: Optional[List[tuple]] = None,
    additional_routes: Optional[List[tuple]] = None,
) -> None:
    """
    Start a FastMCP server that exposes both MCP protocol AND HTTP REST endpoints.
    
    This is the recommended way to serve a DCAF agent. It provides:
    - MCP protocol at /mcp (for AI assistants like Claude)
    - HTTP REST at /api/chat and /api/chat-stream (for web frontends)
    - Health check at /health
    - All on a single port!
    
    Args:
        agent: The DCAF Agent to serve
        name: Name for the server (defaults to agent.name or "dcaf-agent")
        port: Port to listen on (default: 8000)
        host: Host to bind to (default: 0.0.0.0)
        additional_tools: List of functions to expose as MCP tools
        additional_resources: List of (uri, function) tuples to expose as MCP resources
        additional_routes: List of (path, methods, handler) tuples for custom HTTP routes
        
    Endpoints:
        GET  /health           - Health check
        POST /api/chat         - Synchronous chat (HelpDesk protocol)
        POST /api/chat-stream  - Streaming chat (NDJSON)
        *    /mcp              - MCP protocol (SSE transport)
        
    Example - Simple:
        from dcaf.mcp import serve
        
        agent = Agent(tools=[list_pods])
        serve(agent)
        
    Example - With additional tools:
        def cluster_status() -> str:
            '''Get cluster health'''
            return "healthy"
        
        serve(agent, additional_tools=[cluster_status])
        
    Example - With additional resources:
        def get_config() -> str:
            '''Cluster config'''
            return json.dumps({"region": "us-west-2"})
        
        serve(agent, additional_resources=[
            ("cluster://config", get_config),
        ])
        
    Example - With additional HTTP routes:
        async def custom_status(request):
            return JSONResponse({"custom": "data"})
        
        serve(agent, additional_routes=[
            ("/api/v2/status", ["GET"], custom_status),
        ])
        
    Example - All together:
        serve(
            agent,
            additional_tools=[cluster_status, scale_deployment],
            additional_resources=[("cluster://config", get_config)],
            additional_routes=[("/api/v2/status", ["GET"], custom_status)],
        )
        
    Note:
        This function blocks until the server is stopped (Ctrl+C).
    """
    try:
        from fastmcp import FastMCP
    except ImportError as e:
        raise MCPIntegrationError(
            "FastMCP is not installed. Install with: pip install dcaf[mcp]"
        ) from e
    
    server_name = name or getattr(agent, "name", None) or "dcaf-agent"
    mcp = create_server(agent, name=server_name)
    
    # Add additional tools
    if additional_tools:
        from fastmcp.tools import Tool
        for tool_func in additional_tools:
            tool_obj = Tool.from_function(tool_func)
            mcp.add_tool(tool_obj)
            logger.debug(f"Added additional tool: {tool_func.__name__}")
    
    # Add additional resources
    if additional_resources:
        for uri, resource_func in additional_resources:
            mcp.resource(uri)(resource_func)
            logger.debug(f"Added additional resource: {uri}")
    
    # Add additional HTTP routes
    if additional_routes:
        for path, methods, handler in additional_routes:
            mcp.custom_route(path, methods=methods)(handler)
            logger.debug(f"Added additional route: {methods} {path}")
    
    logger.info(f"Starting DCAF server '{server_name}' at http://{host}:{port}")
    logger.info("Endpoints:")
    logger.info(f"  GET  http://{host}:{port}/health")
    logger.info(f"  POST http://{host}:{port}/api/chat")
    logger.info(f"  POST http://{host}:{port}/api/chat-stream")
    logger.info(f"  MCP  http://{host}:{port}/mcp")
    
    # Run with SSE transport (HTTP-based)
    mcp.run(transport="sse", host=host, port=port)


def create_server(
    agent: "Agent",
    name: str = "dcaf-agent",
    version: str = "1.0.0",
    include_chat_endpoints: bool = True,
):
    """
    Create a FastMCP server from a DCAF Agent.
    
    This creates a server that exposes:
    - All agent tools via MCP protocol
    - Optionally, HTTP REST endpoints for chat
    
    Args:
        agent: The DCAF Agent whose tools should be exposed
        name: Name for the server (shown to AI assistants)
        version: Version string for the server
        include_chat_endpoints: If True (default), adds /api/chat endpoints
                               for HelpDesk compatibility
        
    Returns:
        A FastMCP server instance ready to customize or run
        
    Raises:
        MCPIntegrationError: If FastMCP is not installed
        
    Example - Basic usage:
        from dcaf.core import Agent
        from dcaf.mcp import create_server
        
        agent = Agent(tools=[my_tool])
        mcp = create_server(agent, name="my-agent")
        mcp.run()
        
    Example - Add custom resources:
        mcp = create_server(agent, name="my-agent")
        
        @mcp.resource("config://settings")
        def get_settings() -> str:
            return json.dumps(settings)
        
        mcp.run()
        
    Example - Add custom HTTP routes:
        mcp = create_server(agent, name="my-agent")
        
        @mcp.custom_route("/api/custom/status", methods=["GET"])
        async def custom_status(request):
            from starlette.responses import JSONResponse
            return JSONResponse({"custom": "data"})
        
        mcp.run()
        
    Example - MCP only (no chat endpoints):
        mcp = create_server(agent, include_chat_endpoints=False)
        mcp.run()  # Only exposes MCP protocol at /mcp
    """
    try:
        from fastmcp import FastMCP
    except ImportError as e:
        raise MCPIntegrationError(
            "FastMCP is not installed. Install with: pip install dcaf[mcp]"
        ) from e
    
    # Create the FastMCP server
    mcp = FastMCP(name, version=version)
    
    # Register each tool from the agent
    for tool in agent.tools:
        _register_tool(mcp, tool)
        logger.debug(f"Registered MCP tool: {tool.name}")
    
    # Add a "chat" tool for full agent invocation
    _add_agent_chat_tool(mcp, agent, name)
    
    # Add agent info resource
    _add_agent_info_resource(mcp, agent, name, version)
    
    # Add HTTP chat endpoints for HelpDesk compatibility
    if include_chat_endpoints:
        _add_chat_endpoints(mcp, agent)
    
    logger.info(f"Created FastMCP server '{name}' with {len(agent.tools)} tools")
    
    return mcp


# =============================================================================
# Internal: Tool Registration
# =============================================================================

def _register_tool(mcp, tool) -> None:
    """Register a single DCAF tool with FastMCP."""
    tool_name = tool.name
    tool_description = tool.description
    tool_func = tool.func
    
    # Handle tools that need platform_context
    if tool.requires_platform_context:
        import functools
        import inspect
        
        @functools.wraps(tool_func)
        def wrapper(*args, **kwargs):
            # Inject empty platform context for MCP calls
            kwargs['platform_context'] = {}
            return tool_func(*args, **kwargs)
        
        # Copy signature without platform_context
        try:
            sig = inspect.signature(tool_func)
            filtered_params = [
                p for name, p in sig.parameters.items()
                if name != 'platform_context'
            ]
            wrapper.__signature__ = sig.replace(parameters=filtered_params)
        except (ValueError, TypeError):
            pass
        
        mcp.tool(name=tool_name, description=tool_description)(wrapper)
    else:
        mcp.tool(name=tool_name, description=tool_description)(tool_func)


def _add_agent_chat_tool(mcp, agent: "Agent", server_name: str) -> None:
    """Add a 'chat' tool that invokes the full agent with LLM reasoning."""
    
    def chat_with_agent(message: str) -> str:
        """
        Send a message to the agent and get a response.
        
        This invokes the full agent including LLM reasoning, not just
        individual tools. Use this for complex queries that need the
        agent to decide which tools to use.
        
        Args:
            message: The message to send to the agent
            
        Returns:
            The agent's response text
        """
        try:
            result = agent.run(
                messages=[{"role": "user", "content": message}],
                context={},
            )
            return result.text or "No response"
        except Exception as e:
            logger.exception(f"Agent chat error: {e}")
            return f"Error: {str(e)}"
    
    mcp.tool(
        name="chat",
        description=f"Chat with {server_name} (full agent with LLM reasoning)"
    )(chat_with_agent)
    
    logger.debug("Added 'chat' tool for full agent invocation")


def _add_agent_info_resource(mcp, agent: "Agent", name: str, version: str) -> None:
    """Add a resource with agent information."""
    
    @mcp.resource(f"agent://{name}/info")
    def agent_info() -> str:
        """Get information about this agent."""
        tools_info = []
        for tool in agent.tools:
            tools_info.append({
                "name": tool.name,
                "description": tool.description,
                "requires_approval": tool.requires_approval,
            })
        
        info = {
            "name": name,
            "version": version,
            "description": getattr(agent, "description", None) or getattr(agent, "system_prompt", ""),
            "model": getattr(agent, "model", "unknown"),
            "provider": getattr(agent, "provider", "unknown"),
            "tools": tools_info,
            "tool_count": len(agent.tools),
        }
        return json.dumps(info, indent=2)
    
    logger.debug(f"Added agent info resource: agent://{name}/info")


# =============================================================================
# Internal: HTTP Chat Endpoints
# =============================================================================

def _add_chat_endpoints(mcp, agent: "Agent") -> None:
    """Add HTTP REST endpoints for HelpDesk chat compatibility."""
    from starlette.requests import Request
    from starlette.responses import JSONResponse, StreamingResponse
    
    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request):
        """Health check endpoint."""
        return JSONResponse({"status": "healthy"})
    
    @mcp.custom_route("/api/chat", methods=["POST"])
    async def chat_endpoint(request: Request):
        """
        Synchronous chat endpoint (HelpDesk protocol).
        
        Accepts: {"messages": [{"role": "user", "content": "..."}]}
        Returns: {"role": "assistant", "content": "...", "data": {...}}
        """
        try:
            body = await request.json()
            messages = body.get("messages", [])
            
            # Extract platform context from last user message
            context = {}
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    ctx = msg.get("platform_context", {})
                    if ctx:
                        context = dict(ctx) if not hasattr(ctx, "model_dump") else ctx.model_dump()
                    break
            
            # Run the agent
            result = agent.run(messages=messages, context=context)
            
            # Convert to HelpDesk protocol format
            response = _to_helpdesk_response(result)
            return JSONResponse(response)
            
        except Exception as e:
            logger.exception(f"Chat endpoint error: {e}")
            return JSONResponse(
                {"role": "assistant", "content": f"Error: {str(e)}", "data": {}},
                status_code=500
            )
    
    @mcp.custom_route("/api/chat-stream", methods=["POST"])
    async def chat_stream_endpoint(request: Request):
        """
        Streaming chat endpoint (NDJSON).
        
        Accepts: {"messages": [{"role": "user", "content": "..."}]}
        Streams: {"type": "text_delta", "text": "..."} per line
        """
        try:
            body = await request.json()
            messages = body.get("messages", [])
            
            # Extract platform context
            context = {}
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    ctx = msg.get("platform_context", {})
                    if ctx:
                        context = dict(ctx) if not hasattr(ctx, "model_dump") else ctx.model_dump()
                    break
            
            async def generate():
                try:
                    # For now, wrap sync call (full streaming support coming)
                    result = agent.run(messages=messages, context=context)
                    
                    # Emit text content
                    if result.text:
                        yield json.dumps({"type": "text_delta", "text": result.text}) + "\n"
                    
                    # Emit tool calls if any
                    if result.pending_tools:
                        tool_calls = [
                            {
                                "id": t.id,
                                "name": t.name,
                                "input": t.input,
                                "execute": False,
                            }
                            for t in result.pending_tools
                        ]
                        yield json.dumps({"type": "tool_calls", "tool_calls": tool_calls}) + "\n"
                    
                    yield json.dumps({"type": "done"}) + "\n"
                    
                except Exception as e:
                    yield json.dumps({"type": "error", "error": str(e)}) + "\n"
            
            return StreamingResponse(
                generate(),
                media_type="application/x-ndjson"
            )
            
        except Exception as e:
            logger.exception(f"Stream endpoint error: {e}")
            return JSONResponse(
                {"error": str(e)},
                status_code=500
            )
    
    logger.debug("Added HTTP chat endpoints: /health, /api/chat, /api/chat-stream")


def _to_helpdesk_response(result) -> dict:
    """Convert AgentResponse to HelpDesk protocol format."""
    response = {
        "role": "assistant",
        "content": result.text or "",
        "data": {
            "tool_calls": [],
            "executed_tool_calls": [],
            "cmds": [],
            "executed_cmds": [],
        }
    }
    
    # Add pending tool calls
    for pending in result.pending_tools:
        response["data"]["tool_calls"].append({
            "id": pending.id,
            "name": pending.name,
            "input": pending.input,
            "execute": False,
            "tool_description": pending.description or "",
        })
    
    # Add executed tool calls
    for executed in result.executed_tools:
        response["data"]["executed_tool_calls"].append({
            "id": executed.id,
            "name": executed.name,
            "input": executed.input,
            "output": executed.output,
        })
    
    return response


# =============================================================================
# Utility Functions
# =============================================================================

def get_mcp_tool_schemas(agent: "Agent") -> List[dict]:
    """
    Get MCP-compatible tool schemas from an agent.
    
    This is useful for inspecting what tools would be exposed via MCP
    without actually creating a server.
    
    Args:
        agent: The DCAF Agent
        
    Returns:
        List of tool schemas in MCP format
    """
    schemas = []
    for tool in agent.tools:
        schema = {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.schema.get("input_schema", {}),
        }
        schemas.append(schema)
    return schemas


# =============================================================================
# Legacy Aliases (for backwards compatibility)
# =============================================================================

def serve_mcp(
    agent: "Agent",
    name: Optional[str] = None,
    version: str = "1.0.0",
    transport: str = "sse",
    host: str = "0.0.0.0",
    port: int = 8000,
) -> None:
    """
    Legacy function - use serve() instead.
    
    This function is kept for backwards compatibility.
    """
    logger.warning("serve_mcp() is deprecated. Use serve() instead.")
    serve(agent, name=name, port=port, host=host)


def create_mcp_server(
    agent: "Agent",
    name: str = "dcaf-agent",
    version: str = "1.0.0",
    include_agent_tool: bool = True,
):
    """
    Legacy function - use create_server() instead.
    
    This function is kept for backwards compatibility.
    """
    logger.warning("create_mcp_server() is deprecated. Use create_server() instead.")
    return create_server(agent, name=name, version=version)
