"""
DCAF MCP (Model Context Protocol) Integration.

This module provides integration with FastMCP, enabling agents to expose
their tools to AI assistants like Claude and ChatGPT via the MCP protocol.

MCP (Model Context Protocol) is Anthropic's standard for connecting AI
assistants to external tools, resources, and capabilities. Using this module,
you can expose your DCAF agent's tools to any MCP-compatible client.

Installation:
    pip install dcaf[mcp]

Quick Start - MCP Server:
    from dcaf.core import Agent
    from dcaf.mcp import serve_mcp
    from dcaf.tools import tool
    
    @tool(description="Query infrastructure")
    def query_infra(query: str) -> str:
        return f"Results for: {query}"
    
    agent = Agent(tools=[query_infra])
    serve_mcp(agent, name="infrastructure-agent")

Quick Start - Both HTTP and MCP:
    from dcaf.core import Agent, serve
    
    agent = Agent(tools=[query_infra])
    serve(agent, mcp=True)  # Runs HTTP on 8000, MCP on 8001

Programmatic Control:
    from dcaf.mcp import create_mcp_server
    
    agent = Agent(tools=[...])
    mcp = create_mcp_server(agent, name="my-agent")
    
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

from typing import TYPE_CHECKING, Optional, List, Any
import logging

if TYPE_CHECKING:
    from ..core.agent import Agent

__all__ = [
    "create_mcp_server",
    "serve_mcp",
    "MCPIntegrationError",
]

logger = logging.getLogger(__name__)


class MCPIntegrationError(Exception):
    """Raised when MCP integration fails."""
    pass


def serve_mcp(
    agent: "Agent",
    name: Optional[str] = None,
    version: str = "1.0.0",
    transport: str = "stdio",
    host: str = "0.0.0.0",
    port: int = 8001,
) -> None:
    """
    Start an MCP server for the agent.
    
    This is the simplest way to expose an agent's tools via MCP. It creates
    a FastMCP server and runs it with the specified transport.
    
    Args:
        agent: The DCAF Agent whose tools should be exposed
        name: Name for the MCP server (defaults to agent.name or "dcaf-agent")
        version: Version string for the server
        transport: Transport mode - "stdio" (default) or "sse"
                  - stdio: Standard input/output (for Claude Desktop, etc.)
                  - sse: Server-Sent Events over HTTP (for web clients)
        host: Host to bind to for SSE transport (default: 0.0.0.0)
        port: Port for SSE transport (default: 8001)
        
    Example - stdio transport (for Claude Desktop):
        from dcaf.core import Agent
        from dcaf.mcp import serve_mcp
        
        agent = Agent(tools=[list_pods, delete_pod])
        serve_mcp(agent, name="k8s-assistant")
        
    Example - SSE transport (for web clients):
        serve_mcp(agent, transport="sse", port=8001)
        
    Note:
        This function blocks until the server is stopped.
        For programmatic control, use create_mcp_server() instead.
    """
    server_name = name or getattr(agent, "name", None) or "dcaf-agent"
    mcp = create_mcp_server(agent, name=server_name, version=version)
    
    logger.info(f"Starting MCP server '{server_name}' with {transport} transport")
    
    if transport == "stdio":
        logger.info("MCP server running (stdio mode)")
        logger.info("Connect via Claude Desktop or other MCP clients")
        mcp.run()
    elif transport == "sse":
        logger.info(f"MCP server running at http://{host}:{port}")
        mcp.run(transport="sse", host=host, port=port)
    else:
        raise ValueError(f"Unknown transport: {transport}. Use 'stdio' or 'sse'.")


def create_mcp_server(
    agent: "Agent",
    name: str = "dcaf-agent",
    version: str = "1.0.0",
    include_agent_tool: bool = True,
):
    """
    Create a FastMCP server from a DCAF Agent.
    
    This function creates an MCP server that exposes the agent's tools
    via the Model Context Protocol, making them discoverable and callable
    by AI assistants.
    
    Args:
        agent: The DCAF Agent whose tools should be exposed
        name: Name for the MCP server (shown to AI assistants)
        version: Version string for the server
        include_agent_tool: If True, adds a special "chat" tool that invokes
                           the full agent (with LLM reasoning). Default: True.
        
    Returns:
        A FastMCP server instance ready to customize or run
        
    Raises:
        MCPIntegrationError: If FastMCP is not installed
        
    Example - Basic usage:
        from dcaf.core import Agent
        from dcaf.mcp import create_mcp_server
        
        agent = Agent(tools=[my_tool, other_tool])
        mcp = create_mcp_server(agent, name="my-agent")
        mcp.run()
        
    Example - Add custom resources:
        mcp = create_mcp_server(agent, name="my-agent")
        
        @mcp.resource("config://settings")
        def get_settings() -> str:
            return json.dumps(settings)
        
        @mcp.resource("db://schema")
        async def get_schema() -> str:
            return await fetch_schema()
        
        mcp.run()
        
    Example - Add custom tools:
        mcp = create_mcp_server(agent, name="my-agent")
        
        @mcp.tool()
        def calculate(expression: str) -> str:
            \"\"\"Evaluate a math expression.\"\"\"
            return str(eval(expression))
        
        mcp.run()
        
    Example - Without the "chat" agent tool:
        # Only expose individual tools, not the full agent
        mcp = create_mcp_server(agent, include_agent_tool=False)
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
    
    # Optionally add a "chat" tool that invokes the full agent
    if include_agent_tool:
        _add_agent_chat_tool(mcp, agent, name)
    
    # Add agent info as a resource
    _add_agent_info_resource(mcp, agent, name, version)
    
    logger.info(f"Created MCP server '{name}' with {len(agent.tools)} tools")
    
    return mcp


def _register_tool(mcp, tool) -> None:
    """Register a single DCAF tool with FastMCP."""
    tool_name = tool.name
    tool_description = tool.description
    tool_func = tool.func
    
    # FastMCP's @tool decorator handles schema inference from the function
    # We wrap it to handle any platform_context injection if needed
    if tool.requires_platform_context:
        # Create wrapper that provides empty context (MCP doesn't have platform context)
        import functools
        
        @functools.wraps(tool_func)
        def wrapper(*args, **kwargs):
            # Inject empty platform context for MCP calls
            kwargs['platform_context'] = {}
            return tool_func(*args, **kwargs)
        
        # Copy signature without platform_context
        import inspect
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
    agent_description = getattr(agent, "description", None) or f"Chat with {server_name}"
    
    def chat(message: str) -> str:
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
    
    chat.__doc__ = f"""Chat with the {server_name} agent.

This tool invokes the full agent with LLM reasoning. The agent can:
- Use any of its available tools
- Reason about which tools to use
- Combine multiple tool calls if needed

Use this for complex queries. For simple, direct tool calls, use the
individual tool functions instead.

{agent_description}
"""
    
    mcp.tool(name="chat", description=f"Chat with {server_name} (full agent with LLM)")(chat)
    logger.debug("Added 'chat' tool for full agent invocation")


def _add_agent_info_resource(mcp, agent: "Agent", name: str, version: str) -> None:
    """Add a resource with agent information."""
    import json
    
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
# Utility functions for advanced use cases
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
