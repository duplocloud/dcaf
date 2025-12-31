"""
DCAF MCP (Model Context Protocol) Integration.

This module provides integration with FastMCP, enabling agents to expose
their tools to AI assistants like Claude and ChatGPT via the MCP protocol.

Installation:
    pip install dcaf[mcp]

Quick Start:
    from dcaf.core import Agent
    from dcaf.mcp import create_mcp_server
    from dcaf.tools import tool
    
    @tool(description="Query infrastructure")
    def query_infra(query: str) -> str:
        return f"Results for: {query}"
    
    agent = Agent(tools=[query_infra])
    
    # Create MCP server from agent (auto-exposes tools)
    mcp = create_mcp_server(agent, name="infrastructure-agent")
    mcp.run()  # Starts MCP server

Advanced Usage:
    from dcaf.mcp import create_mcp_server
    
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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.agent import Agent

__all__ = ["create_mcp_server", "MCPIntegrationError"]


class MCPIntegrationError(Exception):
    """Raised when MCP integration fails."""
    pass


def create_mcp_server(
    agent: "Agent",
    name: str = "dcaf-agent",
    version: str = "1.0.0",
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
        
    Returns:
        A FastMCP server instance ready to run
        
    Raises:
        MCPIntegrationError: If FastMCP is not installed
        
    Example:
        from dcaf.core import Agent
        from dcaf.mcp import create_mcp_server
        
        agent = Agent(tools=[my_tool, other_tool])
        mcp = create_mcp_server(agent, name="my-agent")
        
        # Optionally add resources
        @mcp.resource("config://settings")
        def get_settings() -> str:
            return json.dumps(settings)
        
        # Run the server
        mcp.run()
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
        # Get tool metadata
        tool_name = tool.name
        tool_description = tool.description
        tool_func = tool.func
        
        # Register with FastMCP
        # FastMCP's @tool decorator handles schema inference
        mcp.tool(name=tool_name, description=tool_description)(tool_func)
    
    return mcp
